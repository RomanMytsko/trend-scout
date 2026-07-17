"""Graph nodes (agents) and conditional routing functions."""

import functools
import logging

import langchain_openai

from trend_scout import prompts, sanitize, tools
from trend_scout.config import settings
from trend_scout.schemas import (
    CurationResult,
    DigestState,
    JudgeVerdict,
    RawItem,
    ResearchPlan,
)

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=1)
def _llm() -> langchain_openai.ChatOpenAI:
    return langchain_openai.ChatOpenAI(model=settings.openai_model, temperature=0)


def _structured(schema: type):
    return _llm().with_structured_output(schema)


# --- agents -----------------------------------------------------------------


def planner(state: DigestState) -> DigestState:
    """LLM agent: decompose topics into concrete search queries."""
    replan = state.get("replans", 0) > 0
    plan: ResearchPlan = _structured(ResearchPlan).invoke(
        [
            ("system", prompts.PLANNER_SYSTEM),
            (
                "user",
                prompts.PLANNER_USER.format(
                    topics="; ".join(state["topics"]),
                    audience=settings.audience,
                    replan="yes" if replan else "no",
                ),
            ),
        ]
    )
    return {"plan": plan, "events": [f"planner: {len(plan.queries)} queries"]}


def researcher(state: DigestState) -> DigestState:
    """Deterministic worker: execute RSS + web-search tools, dedupe."""
    items: list[RawItem] = tools.fetch_rss()
    rss_count = len(items)
    for query in state["plan"].queries:
        items.extend(tools.web_search(query))
    items = tools.dedupe(items)
    return {
        "items": items,
        "events": [f"researcher: {rss_count} rss + search -> {len(items)} unique items"],
    }


def curator(state: DigestState) -> DigestState:
    """LLM agent: rank and filter candidates for the audience."""
    curation: CurationResult = _structured(CurationResult).invoke(
        [
            (
                "system",
                prompts.CURATOR_SYSTEM.format(
                    top_n=settings.top_n,
                    audience=settings.audience,
                    topics="; ".join(state["topics"]),
                ),
            ),
            ("user", sanitize.render_items_block(state["items"])),
        ]
    )
    valid = [p for p in curation.picks if 0 <= p.index < len(state["items"])]
    curation = CurationResult(picks=valid[: settings.top_n])
    return {"curation": curation, "events": [f"curator: picked {len(curation.picks)} items"]}


def writer(state: DigestState) -> DigestState:
    """LLM agent: compose the digest; on revision, address judge feedback."""
    picked = [state["items"][p.index] for p in state["curation"].picks]
    reasons = "\n".join(
        f"item {i}: {p.why_it_matters}" for i, p in enumerate(state["curation"].picks)
    )
    user_msg = (
        f"{sanitize.render_items_block(picked)}\n\nCurator notes (trusted):\n{reasons}"
    )
    revision = state.get("revisions", 0)
    if revision > 0 and "verdict" in state:
        user_msg += prompts.WRITER_REVISION_NOTE.format(
            revision=revision,
            feedback=state["verdict"].feedback,
            previous=state["digest"],
        )
    digest = _llm().invoke(
        [
            (
                "system",
                prompts.WRITER_SYSTEM.format(
                    language=settings.language, audience=settings.audience
                ),
            ),
            ("user", user_msg),
        ]
    ).content
    return {"digest": digest, "events": [f"writer: draft #{revision} ready"]}


def judge(state: DigestState) -> DigestState:
    """Deterministic guardrail + LLM-as-a-judge rubric scoring."""
    picked = [state["items"][p.index] for p in state["curation"].picks]
    bad_urls = sanitize.extract_violating_urls(state["digest"], {i.url for i in picked})
    if bad_urls:
        verdict = JudgeVerdict(
            relevance=1,
            grounding=1,
            format_score=1,
            feedback=(
                "Digest links to URLs that are not in the source items "
                f"(possible hallucination): {bad_urls}. Use only exact source URLs."
            ),
        )
        return {"verdict": verdict, "events": ["judge: FAILED url allowlist guardrail"]}

    verdict = _structured(JudgeVerdict).invoke(
        [
            (
                "system",
                prompts.JUDGE_SYSTEM.format(
                    topics="; ".join(state["topics"]),
                    audience=settings.audience,
                    language=settings.language,
                ),
            ),
            (
                "user",
                f"Source items:\n{sanitize.render_items_block(picked)}\n\n"
                f"Draft digest:\n{state['digest']}",
            ),
        ]
    )
    return {
        "verdict": verdict,
        "events": [
            f"judge: relevance={verdict.relevance} grounding={verdict.grounding} "
            f"format={verdict.format_score} avg={verdict.average:.2f}"
        ],
    }


# --- conditional routing ----------------------------------------------------


def route_after_research(state: DigestState) -> str:
    """Not enough material -> one replan with broader queries, else curate."""
    if len(state.get("items", [])) >= settings.min_items:
        return "curator"
    if state.get("replans", 0) >= 1:
        logger.warning("Few items even after replan, proceeding anyway.")
        return "curator"
    return "replan"


def bump_replans(state: DigestState) -> DigestState:
    return {"replans": state.get("replans", 0) + 1, "events": ["router: replanning"]}


def route_after_judge(state: DigestState) -> str:
    """Approve, or send back to writer until max_revisions is exhausted."""
    if state["verdict"].average >= settings.judge_threshold:
        return "approve"
    if state.get("revisions", 0) >= settings.max_revisions:
        logger.warning("Max revisions reached, releasing best-effort digest.")
        return "approve"
    return "revise"


def bump_revisions(state: DigestState) -> DigestState:
    return {"revisions": state.get("revisions", 0) + 1, "events": ["router: revision requested"]}
