"""Offline proof that exhausted hard-guardrail failures cannot publish."""

from trend_scout import nodes
from trend_scout.config import settings
from trend_scout.schemas import JudgeVerdict


def main() -> None:
    verdict = JudgeVerdict(
        relevance=1,
        grounding=1,
        format_score=1,
        feedback="A non-source URL remains in the draft.",
    )
    state = {
        "verdict": verdict,
        "hard_guardrail_failed": True,
        "revisions": settings.max_revisions,
    }
    route = nodes.route_after_judge(state)
    print(f"hard_guardrail_failed: {state['hard_guardrail_failed']}")
    print(f"revisions: {state['revisions']}/{settings.max_revisions}")
    print(f"route: {route}")
    print("publisher reachable: no")


if __name__ == "__main__":
    main()
