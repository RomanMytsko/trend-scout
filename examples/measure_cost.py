"""Measure real token usage and cost of one full pipeline run.

Attaches a callback that tallies token usage across every LLM call in the
graph, then prices it with gpt-4.1-mini rates.

Run: ``python examples/measure_cost.py`` (needs OPENAI_API_KEY).
"""

from langchain_core.callbacks import BaseCallbackHandler

from trend_scout import graph

PRICE_IN_PER_M = 0.40   # USD per 1M input tokens, gpt-4.1-mini
PRICE_OUT_PER_M = 1.60  # USD per 1M output tokens


class TokenTally(BaseCallbackHandler):
    def __init__(self) -> None:
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def on_llm_end(self, response, **kwargs) -> None:
        self.calls += 1
        usage = (response.llm_output or {}).get("token_usage", {})
        if not usage:
            try:
                usage = response.generations[0][0].message.usage_metadata or {}
                usage = {
                    "prompt_tokens": usage.get("input_tokens", 0),
                    "completion_tokens": usage.get("output_tokens", 0),
                }
            except (AttributeError, IndexError):
                usage = {}
        self.prompt_tokens += usage.get("prompt_tokens", 0)
        self.completion_tokens += usage.get("completion_tokens", 0)


def main() -> None:
    tally = TokenTally()
    state = graph.run_digest(
        [
            "multi-agent orchestration",
            "MCP and A2A protocols",
            "LangGraph and agent frameworks",
            "context engineering",
        ],
        config={"callbacks": [tally]},
    )

    cost = (
        tally.prompt_tokens / 1e6 * PRICE_IN_PER_M
        + tally.completion_tokens / 1e6 * PRICE_OUT_PER_M
    )
    print("--- pipeline events ---")
    for event in state.get("events", []):
        print(" ", event)
    print("\n--- token usage ---")
    print(f"LLM calls:         {tally.calls}")
    print(f"prompt tokens:     {tally.prompt_tokens}")
    print(f"completion tokens: {tally.completion_tokens}")
    print(f"estimated cost:    ${cost:.4f} (gpt-4.1-mini)")


if __name__ == "__main__":
    main()
