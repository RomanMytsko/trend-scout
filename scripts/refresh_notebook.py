# ruff: noqa: E501
"""Refresh the checked-in Colab narrative before executing it.

Run from the repository root, then execute the notebook with a real API key.
The script deliberately clears stale outputs so a failed execution cannot be
mistaken for current evidence.
"""

import json
import pathlib

NOTEBOOK = pathlib.Path("notebooks/trend_scout_colab.ipynb")


def source(text: str) -> list[str]:
    return text.strip().splitlines(keepends=True)


def main() -> None:
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    cells = notebook["cells"]
    cells[:] = [
        cell for cell in cells if "before remember:" not in "".join(cell.get("source", []))
    ]

    cells[0]["source"] = source(
        """
# Trend Scout — щоденний AI-дайджест у Telegram (LangGraph)

**Фінальний проєкт** · курс Generative AI Developer (robot_dreams) · Роман Мицко · липень 2026

Репозиторій: https://github.com/RomanMytsko/trend-scout

**Ідея.** Trend Scout запускається щодня, досліджує rolling date window, відбирає нові історії та готує Telegram-пост. Архітектура — чотири LLM-агенти й детерміновані workers у явному LangGraph:

```text
planner → researcher → curator → writer → judge → publisher → archive → END
   ↑           │          │         ↑         │
   └── replan ─┴──────────┘         └ revise ─┘
                                      │
                         hard fail / budget → reject → END
```

| Вузол | Тип | Відповідальність |
|---|---|---|
| planner | LLM-агент | 2–6 запитів для точної дати та заданих тем |
| researcher | worker | RSS + паралельний DDG, URL/semantic dedupe, delivered-memory |
| curator | LLM-агент | ранжування під аудиторію, унікальні picks |
| writer | LLM-агент | Markdown-дайджест і ревізії за фідбеком |
| judge | guardrail + LLM | hard URL/format checks і рубрика 1–5 |
| publisher | worker | Telegram або локальний preview |
| archive | memory | запамʼятовує лише підтверджено доставлені історії |
| reject | terminal | fail-closed: нічого не надсилає й не архівує |

Replan і revise мають жорсткі бюджети. Після їх вичерпання невдалий дайджест блокується, а не публікується best-effort.
"""
    )

    cells[1]["source"] = source(
        """
import pathlib
import subprocess
import sys

# Local execution uses this checkout; Colab installs the public repository.
if pathlib.Path("pyproject.toml").exists():
    package = "."
elif pathlib.Path("../pyproject.toml").exists():
    package = ".."
else:
    package = "git+https://github.com/RomanMytsko/trend-scout.git"
subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", package])
print("trend-scout installed from", package)
"""
    )

    cells[3]["source"] = source(
        """
import os

if not os.environ.get("OPENAI_API_KEY"):
    try:
        from google.colab import userdata
        os.environ["OPENAI_API_KEY"] = userdata.get("OPENAI_API_KEY")
    except Exception:
        import getpass
        os.environ["OPENAI_API_KEY"] = getpass.getpass("OPENAI_API_KEY: ")

os.environ.setdefault("DIGEST_LANGUAGE", "Ukrainian")
os.environ.setdefault("AUDIENCE", "backend Python engineer")
os.environ.setdefault("DAYS_BACK", "7")  # daily schedule, rolling week
print("Configuration ready; API key is not displayed.")
"""
    )

    cells[6]["source"] = source(
        """
## Запуск пайплайну

Теми можна міняти. Baseline — 4 chat-model calls; bounded replan/revise loops можуть збільшити максимум до 12. DDG є keyless і часом throttled, тому тематичні RSS залишаються fallback.
"""
    )

    cells[7]["source"] = source(
        """
TOPICS = [
    "multi-agent orchestration",
    "MCP and A2A protocols",
    "LangGraph and agent frameworks",
    "context engineering",
]

state = graph.run_digest(TOPICS)

print("--- pipeline events ---")
for event in state["events"]:
    print(" ", event)
print("delivery_status:", state.get("delivery_status", "not reached"))
"""
    )

    cells[8]["source"] = source(
        """
## Оцінка якості: hard guardrail + LLM-as-a-judge

Спочатку код перевіряє структуру та URL allowlist. Далі LLM-суддя оцінює relevance, grounding і format. Невдалий hard check або будь-який criterion score нижче 4.0 запускає bounded recovery; після вичерпання бюджету route=`reject`, тож Telegram і delivered-memory недоступні.
"""
    )

    cells[9]["source"] = source(
        """
verdict = state.get("verdict")
if verdict:
    print(f"relevance    : {verdict.relevance}/5")
    print(f"grounding    : {verdict.grounding}/5")
    print(f"format       : {verdict.format_score}/5")
    print(f"average      : {verdict.average:.2f}")
    print(f"criteria pass: {verdict.passes(4.0)} (кожен score >= 4.0)")
    print(f"ревізій      : {state.get('revisions', 0)}")
    print(f"replan-ів    : {state.get('replans', 0)}")
    print(f"hard failure : {state.get('hard_guardrail_failed', False)}")
    print(f"delivery     : {state.get('delivery_status', 'not reached')}")
    print(f"\\nфідбек судді: {verdict.feedback}")
else:
    print("No judge verdict: research/curation was blocked earlier.")
"""
    )

    cells[13]["source"] = source(
        """
print("PLAN (planner, structured output):")
print("  reasoning:", state["plan"].reasoning)
for q in state["plan"].queries:
    print("  query:", q)

print(f"\\nITEMS (researcher): {len(state.get('items', []))} після dedupe/memory, приклади:")
for item in state.get("items", [])[:5]:
    print(f"  [{item.source}] {item.title[:80]}")

print("\\nCURATION (curator):")
for pick in (state["curation"].picks if state.get("curation") else []):
    print(f"  #{pick.index} relevance={pick.relevance}: {pick.why_it_matters[:100]}")
"""
    )

    cells[14]["source"] = source(
        """
## Telegram delivery status

Без credentials publisher працює у preview mode: HTML зберігається локально, але не вважається доставленим і не потрапляє в delivered-memory. З `TELEGRAM_BOT_TOKEN` та `TELEGRAM_CHANNEL_ID` успішна Bot API відповідь дає `delivery_status=sent`, після чого archive може записати історії в Chroma. Для multi-message постів локальний delivery journal запамʼятовує підтверджені chunks і після обробленої помилки продовжує з першого ненадісланого.
"""
    )

    cells[15]["source"] = source(
        """
post = state.get("post", "")
print(post[:800] if post else "No post was rendered because the run stopped before publishing.")
"""
    )

    cells[16]["source"] = source(
        """
## Семантична дедуплікація та delivered-memory

Embeddings використовуються двічі: для схлопування cross-outlet дублікатів і для пошуку історій, уже **реально доставлених** раніше. Preview не змінює production-memory, тому нижче memory-контракт демонструється окремо на ephemeral Chroma client.
"""
    )

    memory_cell = {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source(
            """
import chromadb

from trend_scout import memory

embeddings = state.get("item_embeddings") or []
picks = state.get("curation").picks if state.get("curation") else []
if embeddings and picks:
    client = chromadb.EphemeralClient()
    picked_items = [state["items"][p.index] for p in picks]
    picked_embeddings = [embeddings[p.index] for p in picks]
    print("before remember:", memory.filter_unseen_indices(picked_embeddings, client=client))
    memory.remember(picked_items, picked_embeddings, client=client)
    print("after remember :", memory.filter_unseen_indices(picked_embeddings, client=client))
else:
    print("Embedding step degraded gracefully; memory demo skipped for this run.")
"""
        ),
    }

    cells[17]["source"] = source(
        """
## Висновки

- Явний LangGraph координує чотири LLM-ролі та детерміновані workers.
- Pydantic structured outputs застосовані до decision agents; Markdown writer перевіряється окремо.
- Hard URL/format guardrails працюють fail-closed; LLM judge дає bounded feedback loop.
- Semantic dedupe і Chroma delivered-memory вирішують різні задачі повторів.
- Delivery status відділяє `sent`, `preview`, `failed` і `blocked`; archive доступний лише після `sent`.
- Обмеження чесні: snippets замість full text, DDG throttling, емпіричні cosine thresholds і same-model judge за замовчуванням.

Наступний production-крок — приватний Telegram-канал і зовнішній scheduler; credentials у репозиторій не додаються.
"""
    )

    cells.insert(17, memory_cell)

    for cell in cells:
        if cell["cell_type"] == "code":
            cell["execution_count"] = None
            cell["outputs"] = []

    NOTEBOOK.write_text(
        json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"Refreshed {NOTEBOOK} with {len(cells)} cells and cleared stale outputs.")


if __name__ == "__main__":
    main()
