"""Graph nodes (agents) and conditional routing functions."""

import concurrent.futures
import datetime
import functools
import logging

import langchain_openai

from trend_scout import memory, prompts, sanitize, semantic, tools
from trend_scout import publisher as tg_publisher
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


@functools.lru_cache(maxsize=1)
def _judge_llm() -> langchain_openai.ChatOpenAI:
    return langchain_openai.ChatOpenAI(model=settings.judge_model, temperature=0)


def _structured(schema: type):
    return _llm().with_structured_output(schema)


def _judge_structured(schema: type):
    return _judge_llm().with_structured_output(schema)


# --- agents -----------------------------------------------------------------


def planner(state: DigestState) -> DigestState:
    """LLM agent: decompose topics into concrete search queries."""
    replan = state.get("replans", 0) > 0
    window_end = datetime.datetime.now(tz=datetime.timezone.utc).date()
    window_start = window_end - datetime.timedelta(days=settings.days_back)
    plan: ResearchPlan = _structured(ResearchPlan).invoke(
        [
            ("system", prompts.PLANNER_SYSTEM),
            (
                "user",
                prompts.PLANNER_USER.format(
                    topics="; ".join(state["topics"]),
                    audience=settings.audience,
                    window_start=window_start.isoformat(),
                    window_end=window_end.isoformat(),
                    days_back=settings.days_back,
                    replan="yes" if replan else "no",
                ),
            ),
        ]
    )
    return {"plan": plan, "events": [f"planner: {len(plan.queries)} queries"]}


def researcher(state: DigestState) -> DigestState:
    """Deterministic worker: tools -> URL dedupe -> semantic dedupe -> memory.

    Semantic steps degrade gracefully: any embedding/Chroma failure keeps the
    URL-deduped list and the pipeline continues.
    """
    queries = state["plan"].queries
    max_workers = min(settings.search_workers, len(queries) + 1)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        rss_future = executor.submit(tools.fetch_rss)
        search_futures = [executor.submit(tools.web_search, query) for query in queries]
        items: list[RawItem] = rss_future.result()
        search_batches = [future.result() for future in search_futures]

    rss_count = len(items)
    search_count = sum(len(batch) for batch in search_batches)
    for batch in search_batches:
        items.extend(batch)
    items = tools.dedupe(items)
    events = [
        f"researcher: {rss_count} rss + {search_count} search -> {len(items)} unique items"
    ]

    embeddings: list[list[float]] = []
    if settings.semantic_dedupe and items:
        try:
            embeddings = semantic.embed_items(items)
            keep = semantic.cluster_keep_indices(embeddings, settings.semantic_threshold)
            if len(keep) < len(items):
                events.append(f"researcher: semantic dedupe {len(items)} -> {len(keep)} stories")
            items = [items[i] for i in keep]
            embeddings = [embeddings[i] for i in keep]
        except Exception:
            logger.warning("Semantic dedupe failed, keeping URL-level dedupe.", exc_info=True)
            embeddings = []

    if settings.memory_enabled and embeddings:
        try:
            keep = memory.filter_unseen_indices(embeddings)
            dropped = len(items) - len(keep)
            if dropped:
                events.append(f"memory: dropped {dropped} already-covered stories")
            items = [items[i] for i in keep]
            embeddings = [embeddings[i] for i in keep]
        except Exception:
            logger.warning("Memory filter failed, keeping all items.", exc_info=True)

    return {"items": items, "item_embeddings": embeddings, "events": events}


def curator(state: DigestState) -> DigestState:
    """LLM agent: rank and filter candidates for the audience."""
    if not state.get("items"):
        return {"curation": CurationResult(picks=[]), "events": ["curator: no items to rank"]}
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
    valid = []
    seen_indexes: set[int] = set()
    for pick in curation.picks:
        if 0 <= pick.index < len(state["items"]) and pick.index not in seen_indexes:
            valid.append(pick)
            seen_indexes.add(pick.index)
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
    format_violations = sanitize.validate_digest_structure(state["digest"], len(picked))
    if bad_urls or format_violations:
        failures = []
        if bad_urls:
            failures.append(
                "Digest links to URLs that are not in the source items "
                f"(possible hallucination): {bad_urls}. Use only exact source URLs."
            )
        if format_violations:
            failures.append("Deterministic format violations: " + "; ".join(format_violations))
        verdict = JudgeVerdict(
            relevance=1,
            grounding=1,
            format_score=1,
            feedback=" ".join(failures),
        )
        return {
            "verdict": verdict,
            "hard_guardrail_failed": True,
            "events": ["judge: FAILED deterministic guardrail"],
        }

    verdict = _judge_structured(JudgeVerdict).invoke(
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
        "hard_guardrail_failed": False,
        "events": [
            f"judge: relevance={verdict.relevance} grounding={verdict.grounding} "
            f"format={verdict.format_score} avg={verdict.average:.2f}"
        ],
    }


def publish(state: DigestState) -> DigestState:
    """Deliver the approved digest to the Telegram channel (dry-run without it)."""
    result = tg_publisher.publish(state["digest"])
    return {
        "post": result.post_html,
        "delivery_status": result.status,
        "events": [result.event],
    }


def reject(state: DigestState) -> DigestState:
    """Fail closed: keep an optional preview but never send or archive it."""
    digest = state.get("digest", "")
    result: DigestState = {
        "delivery_status": "blocked",
        "events": ["quality_gate: BLOCKED, nothing was published or archived"],
    }
    if digest:
        post = tg_publisher.to_telegram_html(digest)
        path = tg_publisher.save_preview(post, settings.post_preview_path)
        result["post"] = post
        result["events"] = [f"quality_gate: BLOCKED, preview saved to {path}"]
    return result


def archive(state: DigestState) -> DigestState:
    """Persist delivered stories to cross-run memory after judge approval."""
    delivery_status = state.get("delivery_status", "failed")
    if delivery_status != "sent":
        return {"events": [f"archive: skipped (delivery status {delivery_status})"]}
    if not settings.memory_enabled:
        return {"events": ["archive: memory disabled"]}
    embeddings = state.get("item_embeddings") or []
    if not embeddings:
        return {"events": ["archive: no embeddings available, skipped"]}
    picks = state["curation"].picks
    picked_items = [state["items"][p.index] for p in picks]
    picked_embeddings = [embeddings[p.index] for p in picks]
    try:
        stored = memory.remember(picked_items, picked_embeddings)
    except Exception:
        logger.warning("Archiving to memory failed.", exc_info=True)
        return {"events": ["archive: failed, skipped"]}
    return {"events": [f"archive: remembered {stored} delivered stories"]}


# --- conditional routing ----------------------------------------------------


def route_after_research(state: DigestState) -> str:
    """Not enough material -> one replan with broader queries, else curate."""
    if len(state.get("items", [])) >= settings.min_items:
        return "curator"
    if state.get("replans", 0) >= settings.max_replans:
        if state.get("items"):
            logger.warning("Few items even after replan, asking the curator to assess them.")
            return "curator"
        logger.warning("No items found after the replan budget was exhausted.")
        return "reject"
    return "replan"


def route_after_curation(state: DigestState) -> str:
    """Require enough curated signal; otherwise replan once or fail closed."""
    picks = state.get("curation", CurationResult(picks=[])).picks
    if len(picks) >= min(settings.min_curated_items, settings.top_n):
        return "writer"
    if state.get("replans", 0) < settings.max_replans:
        return "replan"
    if picks:
        logger.warning("Only %s relevant items after replan; proceeding to the judge.", len(picks))
        return "writer"
    return "reject"


def bump_replans(state: DigestState) -> DigestState:
    return {
        "replans": state.get("replans", 0) + 1,
        "revisions": 0,
        "events": ["router: replanning for more relevant sources"],
    }


def route_after_judge(state: DigestState) -> str:
    """Approve only a passing draft; otherwise replan, revise, or reject."""
    verdict = state["verdict"]
    if not state.get("hard_guardrail_failed", False) and verdict.passes(
        settings.judge_threshold
    ):
        return "approve"
    if state.get("revisions", 0) >= settings.max_revisions:
        logger.warning("Max revisions reached; blocking the digest.")
        return "reject"
    if (
        not state.get("hard_guardrail_failed", False)
        and verdict.relevance < settings.judge_threshold
        and state.get("replans", 0) < settings.max_replans
    ):
        return "replan"
    return "revise"


def bump_revisions(state: DigestState) -> DigestState:
    return {"revisions": state.get("revisions", 0) + 1, "events": ["router: revision requested"]}
