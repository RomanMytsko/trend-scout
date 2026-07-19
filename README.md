# Trend Scout

Multi-agent daily digest for a Telegram channel, built with **LangGraph**: an
orchestrator-workers pipeline that researches your topics every day, curates
the noise away, writes a short digest and posts it to your channel — with an
**LLM-as-a-judge** quality gate before anything is published.

Telegram delivery works out of the box in dry-run mode (the rendered post is
saved locally); set `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHANNEL_ID` and the same
pipeline posts to the real channel.

Final project for the robot_dreams **Generative AI Developer** course.

[![CI](https://github.com/RomanMytsko/trend-scout/actions/workflows/ci.yml/badge.svg)](https://github.com/RomanMytsko/trend-scout/actions/workflows/ci.yml)
[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/RomanMytsko/trend-scout/blob/main/notebooks/trend_scout_colab.ipynb)

## Architecture

![Pipeline graph](docs/architecture.png)

```
  planner ──> researcher ──> curator ──> writer ──> judge ──> publisher ──> archive ──> END
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
| publisher  | Tool worker   | Render Telegram HTML and post to the channel (or dry-run) |
| archive    | Memory worker | Store delivered stories in ChromaDB after publication     |

Key engineering decisions:

- **Structured outputs everywhere** — every agent returns a Pydantic model
  (`ResearchPlan`, `CurationResult`, `JudgeVerdict`), no free-text parsing.
- **Two feedback loops** — replan when research is too thin; revise when the
  judge rejects a draft. Both are capped to guarantee termination.
- **Semantic dedupe** — the same story republished by different outlets is
  collapsed to one item: OpenAI embeddings + greedy cosine clustering
  (URL-level dedupe cannot catch cross-outlet duplicates).
- **Cross-run memory** — published digests are archived to ChromaDB; next runs
  drop candidates semantically close to already-delivered stories, so daily
  posts do not repeat themselves.
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

Only `OPENAI_API_KEY` is required — search and RSS tools are keyless. Without
Telegram credentials the publisher runs in dry-run mode and saves the rendered
post to `telegram_post_preview.html`.

Or open the Colab notebook: [`notebooks/trend_scout_colab.ipynb`](notebooks/trend_scout_colab.ipynb).

## Daily schedule

The pipeline is a single command, so scheduling is one cron line (or a Celery
beat entry / launchd job):

```cron
# every day at 08:00
0 8 * * * cd /path/to/trend-scout && .venv/bin/trend-scout >> digest.log 2>&1
```

## Telegram channel setup (when ready)

1. Create a channel, add your bot as an admin.
2. Put `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHANNEL_ID` (e.g. `@my_channel`)
   into `.env`.
3. That's it — the same pipeline now posts for real; no code changes.

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
