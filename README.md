# Trend Scout

Multi-agent research digest built with **LangGraph**: an orchestrator-workers
pipeline that researches your topics for the last week, curates the noise away
and writes a short digest — with an **LLM-as-a-judge** quality gate before
anything is released.

Final project for the robot_dreams **Generative AI Developer** course.

## Architecture

![Pipeline graph](docs/architecture.png)

```
        planner ──> researcher ──> curator ──> writer ──> judge ──> END
           ^            │                        ^          │
           └── replan ──┘ (too few items,        └─ revise ─┘ (score < 4.0,
               max 1)                               max 2 revisions)
```

| Node       | Type          | Responsibility                                          |
|------------|---------------|---------------------------------------------------------|
| planner    | LLM agent     | Decompose topics into diverse search queries            |
| researcher | Tool worker   | Execute RSS + DuckDuckGo news tools, dedupe             |
| curator    | LLM agent     | Rank/filter candidates for the audience, drop marketing |
| writer     | LLM agent     | Compose digest in a strict format; apply judge feedback |
| judge      | Guardrail+LLM | URL-allowlist check, then rubric scoring (1–5 × 3)      |

Key engineering decisions:

- **Structured outputs everywhere** — every agent returns a Pydantic model
  (`ResearchPlan`, `CurationResult`, `JudgeVerdict`), no free-text parsing.
- **Two feedback loops** — replan when research is too thin; revise when the
  judge rejects a draft. Both are capped to guarantee termination.
- **Prompt-injection guardrails** — all fetched content is sanitized, rendered
  as `<item>` blocks explicitly marked untrusted, and the final digest may
  only link to URLs that were actually collected (deterministic allowlist).
- **Graceful degradation** — a failing feed or rate-limited search never
  crashes the pipeline; the researcher works with whatever was collected.

## Quickstart

```bash
git clone https://github.com/RomanMytsko/trend-scout.git
cd trend-scout
python3 -m venv .venv && .venv/bin/pip install -e .
cp .env.example .env   # put your OPENAI_API_KEY there

.venv/bin/trend-scout                        # default agentic-AI topics
.venv/bin/trend-scout "vector databases" "RAG evaluation" -o digest.md
```

Only `OPENAI_API_KEY` is required — search and RSS tools are keyless.

Or open the Colab notebook: [`notebooks/trend_scout_colab.ipynb`](notebooks/trend_scout_colab.ipynb).

## Example output

See [`examples/`](examples/) for a real digest produced by the pipeline,
including the judge scores and the pipeline event log.

## Project layout

```
src/trend_scout/
├── config.py     # env-driven settings + curated RSS feeds
├── schemas.py    # Pydantic models + LangGraph state
├── sanitize.py   # untrusted-content guardrails
├── tools.py      # RSS + DuckDuckGo news workers
├── prompts.py    # all prompts in one place
├── nodes.py      # agents + conditional routing
├── graph.py      # LangGraph assembly
└── __main__.py   # CLI
```
