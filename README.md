# Trend Scout

Multi-agent research digest built with **LangGraph**: an orchestrator-workers
pipeline that researches your topics for the last week, curates the noise away
and writes a short digest — with an **LLM-as-a-judge** quality gate before
anything is released.

Final project for the robot_dreams **Generative AI Developer** course.

[![CI](https://github.com/RomanMytsko/trend-scout/actions/workflows/ci.yml/badge.svg)](https://github.com/RomanMytsko/trend-scout/actions/workflows/ci.yml)
[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/RomanMytsko/trend-scout/blob/main/notebooks/trend_scout_colab.ipynb)

## Architecture

![Pipeline graph](docs/architecture.png)

```
        planner ──> researcher ──> curator ──> writer ──> judge ──> archive ──> END
           ^            │                        ^          │
           └── replan ──┘ (too few items,        └─ revise ─┘ (score < 4.0,
               max 1)                               max 2 revisions)
```

| Node       | Type          | Responsibility                                            |
|------------|---------------|-----------------------------------------------------------|
| planner    | LLM agent     | Decompose topics into diverse search queries              |
| researcher | Tool worker   | RSS + DuckDuckGo news; URL + semantic dedupe, memory gate |
| curator    | LLM agent     | Rank/filter candidates for the audience, drop marketing   |
| writer     | LLM agent     | Compose digest in a strict format; apply judge feedback   |
| judge      | Guardrail+LLM | URL-allowlist check, then rubric scoring (1–5 × 3)        |
| archive    | Memory worker | Store delivered stories in ChromaDB after approval        |

Key engineering decisions:

- **Structured outputs everywhere** — every agent returns a Pydantic model
  (`ResearchPlan`, `CurationResult`, `JudgeVerdict`), no free-text parsing.
- **Two feedback loops** — replan when research is too thin; revise when the
  judge rejects a draft. Both are capped to guarantee termination.
- **Semantic dedupe** — the same story republished by different outlets is
  collapsed to one item: OpenAI embeddings + greedy cosine clustering
  (URL-level dedupe cannot catch cross-outlet duplicates).
- **Cross-run memory** — approved digests are archived to ChromaDB; next runs
  drop candidates semantically close to already-delivered stories, so weekly
  digests do not repeat themselves.
- **Prompt-injection guardrails** — all fetched content is sanitized, rendered
  as `<item>` blocks explicitly marked untrusted, and the final digest may
  only reference URLs that were actually collected (deterministic allowlist,
  markdown links and bare URLs alike).
- **Graceful degradation** — a failing feed, rate-limited search or embedding
  error never crashes the pipeline; each enrichment step falls back cleanly.

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

One item from a real run (2026-07-17, judge scores 5/5/5, ~$0.006 per run):

> **Least privilege for AI agents: Identity, access, and tool binding**
> - Суть: Microsoft наголошує на важливості суворих контролів ідентичності,
>   доступу та прив'язки інструментів для автономних AI-агентів.
> - Чому важливо: впровадження принципу найменших привілеїв допоможе
>   backend-інженерам захистити багатоагентні системи.
> - Лінк: [Microsoft](https://www.microsoft.com/en-us/security/blog/2026/07/16/least-privilege-for-ai-agents-identity-access-and-tool-binding/)

See [`examples/`](examples/) for the full digest produced by the pipeline,
including the judge scores and the pipeline event log. Also there:

- `guardrail_demo.py` — feeds the judge a draft with a hallucinated link and
  shows the full revise loop: deterministic fail → writer revision → re-score;
- `measure_cost.py` — tallies real token usage and cost of one full run.

## Tests

Deterministic logic (sanitization, URL allowlist, dedupe, routing) is covered
by offline unit tests — no LLM calls, run in CI on every push:

```bash
pip install -e '.[dev]'
pytest -q
```

## Project layout

```
src/trend_scout/
├── config.py     # env-driven settings + configurable RSS feeds
├── schemas.py    # Pydantic models + LangGraph state
├── sanitize.py   # untrusted-content guardrails
├── tools.py      # RSS + DuckDuckGo news workers
├── semantic.py   # embeddings + greedy cosine clustering
├── memory.py     # cross-run memory of delivered stories (ChromaDB)
├── prompts.py    # all prompts in one place
├── nodes.py      # agents + conditional routing
├── graph.py      # LangGraph assembly
└── __main__.py   # CLI
```
