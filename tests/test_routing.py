"""Conditional-routing and guardrail logic, fully offline (no LLM calls)."""

from trend_scout import nodes, sanitize
from trend_scout.config import settings
from trend_scout.schemas import CurationResult, CuratedPick, JudgeVerdict, RawItem


def _items(n: int) -> list[RawItem]:
    return [RawItem(title=f"t{i}", url=f"https://x.io/{i}", source="s") for i in range(n)]


# --- research routing -------------------------------------------------------


def test_enough_items_go_to_curator():
    state = {"items": _items(settings.min_items), "replans": 0}
    assert nodes.route_after_research(state) == "curator"


def test_too_few_items_trigger_one_replan():
    state = {"items": _items(1), "replans": 0}
    assert nodes.route_after_research(state) == "replan"


def test_replan_budget_exhausted_proceeds_anyway():
    state = {"items": _items(1), "replans": 1}
    assert nodes.route_after_research(state) == "curator"


# --- judge routing ----------------------------------------------------------


def _verdict(score: int) -> JudgeVerdict:
    return JudgeVerdict(relevance=score, grounding=score, format_score=score, feedback="fb")


def test_passing_verdict_approves():
    state = {"verdict": _verdict(5), "revisions": 0}
    assert nodes.route_after_judge(state) == "approve"


def test_failing_verdict_requests_revision():
    state = {"verdict": _verdict(2), "revisions": 0}
    assert nodes.route_after_judge(state) == "revise"


def test_revision_budget_exhausted_releases_best_effort():
    state = {"verdict": _verdict(2), "revisions": settings.max_revisions}
    assert nodes.route_after_judge(state) == "approve"


def test_average_is_mean_of_three_criteria():
    verdict = JudgeVerdict(relevance=5, grounding=4, format_score=3, feedback="")
    assert verdict.average == 4.0


# --- deterministic URL-allowlist guardrail inside the judge node ------------


def test_judge_fails_digest_with_hallucinated_url_without_llm():
    items = _items(2)
    state = {
        "topics": ["x"],
        "items": items,
        "curation": CurationResult(
            picks=[CuratedPick(index=0, relevance=5, why_it_matters="w")]
        ),
        "digest": "# D\n[ok](https://x.io/0)\n[evil](https://attacker.example/pwn)",
    }
    result = nodes.judge(state)  # returns before any LLM call
    verdict = result["verdict"]
    assert verdict.average == 1.0
    assert "attacker.example" in verdict.feedback
    assert nodes.route_after_judge({"verdict": verdict, "revisions": 0}) == "revise"


def test_judge_guardrail_ignores_urls_that_were_collected():
    items = _items(1)
    digest = "# D\n[ok](https://x.io/0)"
    assert sanitize.extract_violating_urls(digest, {i.url for i in items}) == []
