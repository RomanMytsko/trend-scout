# Reproducible evidence

The folder separates historical model-run evidence from deterministic demos:

| Artifact | What it proves |
|---|---|
| `final_notebook_run_2026-07-19.txt` | Final Colab: 9/9 cells, 5/5/4 judge scores, preview not archived |
| `daily_run_events_2026-07-19.txt` | A real `3.67 -> 4.67` judge/writer revision loop |
| `digest_daily_2026-07-19.md` | Result of that daily run |
| `digest_weekly_2026-07-19.md` | A stronger five-item weekly result |
| `telegram_post_2026-07-19.html` | Rendered Telegram preview |
| `cost_measurement.txt` | Baseline tokens, calls and estimated model cost |
| `guardrail_demo.py` | Hard URL failure followed by a successful LLM revision |
| `guardrail_demo_output.txt` | Captured output of the guardrail/revision demo |
| `fail_closed_demo.py` | Offline proof that an exhausted hard failure routes to reject |
| `fail_closed_demo_output.txt` | Captured fail-closed output |

Run the deterministic proof without credentials:

```bash
uv run python examples/fail_closed_demo.py
```

The real-run artifacts are snapshots, not promises that live news/search will
return the same sources later. Current production semantics differ from the
historical trace in one deliberate way: preview mode is no longer archived as
delivered.
