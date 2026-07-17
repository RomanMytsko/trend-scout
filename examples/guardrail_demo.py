"""Demonstrate the revise loop end-to-end.

Feeds the judge a digest containing a hallucinated (non-collected) link:

1. the deterministic URL-allowlist guardrail fails the draft without any LLM
   call and produces actionable feedback;
2. the router requests a revision;
3. the writer regenerates the digest addressing that feedback;
4. the judge re-scores the corrected draft with the LLM rubric.

Run: ``python examples/guardrail_demo.py`` (needs OPENAI_API_KEY).
"""

from trend_scout import nodes
from trend_scout.schemas import CuratedPick, CurationResult, RawItem


def main() -> None:
    items = [
        RawItem(
            title="Least privilege for AI agents: Identity, access, and tool binding",
            url="https://www.microsoft.com/en-us/security/blog/2026/07/16/least-privilege-for-ai-agents-identity-access-and-tool-binding/",
            source="web: Microsoft",
            published="2026-07-16",
            snippet=(
                "Microsoft outlines why autonomous AI agents need strict identity, "
                "access, and tool binding controls to stay secure."
            ),
        ),
        RawItem(
            title="Agentic orchestration: Enterprise AI has a deployment problem",
            url="https://venturebeat.com/ai/agentic-orchestration-enterprise-ai-organizations-have-a-deployment-problem-not-a-platform-problem-and-most-are-calling-chatbots-agents",
            source="web: VentureBeat",
            published="2026-07-14",
            snippet=(
                "Across 101 enterprises agent orchestration consolidates on model "
                "provider platforms; the hard part is reliable multi-step execution."
            ),
        ),
    ]
    state = {
        "topics": ["multi-agent orchestration", "agent security"],
        "items": items,
        "curation": CurationResult(
            picks=[
                CuratedPick(index=0, relevance=5, why_it_matters="Security baseline for agent deployments."),
                CuratedPick(index=1, relevance=4, why_it_matters="Deployment reality check for orchestration."),
            ]
        ),
        # Forged draft: second link does NOT come from the collected items.
        "digest": (
            "# Дайджест\n"
            "Огляд тижня.\n"
            "## 1. Least privilege для AI-агентів\n"
            "- Суть: Microsoft наголошує на суворих контролях identity та доступу. Це база безпеки агентів.\n"
            "- Чому важливо: прямі вимоги до продакшн-деплойменту агентних систем.\n"
            "- Лінк: [Microsoft](https://www.microsoft.com/en-us/security/blog/2026/07/16/least-privilege-for-ai-agents-identity-access-and-tool-binding/)\n"
            "## 2. Agentic orchestration в enterprise\n"
            "- Суть: оркестрація консолідується на платформах провайдерів. Складність — у надійному виконанні.\n"
            "- Чому важливо: показує, де насправді болить у продакшні.\n"
            "- Лінк: [джерело](https://totally-legit-news.example.com/agentic)\n"
        ),
        "revisions": 0,
        "events": [],
    }

    print("=== step 1: judge on forged draft (deterministic guardrail) ===")
    result = nodes.judge(state)
    verdict = result["verdict"]
    print(f"scores: {verdict.relevance}/{verdict.grounding}/{verdict.format_score}")
    print(f"feedback: {verdict.feedback}\n")

    route = nodes.route_after_judge({"verdict": verdict, "revisions": 0})
    print(f"=== step 2: router decision -> {route} ===\n")
    state.update(result)
    state.update(nodes.bump_revisions(state))

    print("=== step 3: writer revises the draft ===")
    state.update(nodes.writer(state))
    print(state["digest"][:600], "...\n")

    print("=== step 4: judge re-scores the corrected draft ===")
    result = nodes.judge(state)
    verdict = result["verdict"]
    print(f"scores: {verdict.relevance}/{verdict.grounding}/{verdict.format_score} "
          f"avg={verdict.average:.2f}")
    print(f"router -> {nodes.route_after_judge({'verdict': verdict, 'revisions': 1})}")


if __name__ == "__main__":
    main()
