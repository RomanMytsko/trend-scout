"""Runtime configuration loaded from environment variables."""

import dataclasses
import json
import logging
import os

import dotenv

dotenv.load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_FEEDS: dict[str, str] = {
    "Hacker News (front page)": "https://hnrss.org/frontpage",
    "OpenAI News": "https://openai.com/news/rss.xml",
    "LangChain Blog": "https://blog.langchain.com/rss/",
    "Google AI Blog": "https://blog.google/technology/ai/rss/",
    "arXiv cs.MA (multi-agent)": (
        "https://export.arxiv.org/api/query?search_query=cat:cs.MA"
        "&sortBy=submittedDate&sortOrder=descending&max_results=15"
    ),
}


def feeds_from_env() -> dict[str, str]:
    """Feed list is configuration: override via ``RSS_FEEDS_JSON`` env var.

    Expected format: ``{"Feed name": "https://feed.url", ...}``.
    Falls back to :data:`DEFAULT_FEEDS` when unset or invalid.
    """
    raw = os.getenv("RSS_FEEDS_JSON", "").strip()
    if not raw:
        return DEFAULT_FEEDS
    try:
        feeds = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("RSS_FEEDS_JSON is not valid JSON, using default feeds.")
        return DEFAULT_FEEDS
    if not isinstance(feeds, dict) or not feeds:
        logger.warning("RSS_FEEDS_JSON must be a non-empty JSON object, using default feeds.")
        return DEFAULT_FEEDS
    return {str(name): str(url) for name, url in feeds.items()}


FEEDS = feeds_from_env()


@dataclasses.dataclass(frozen=True)
class Settings:
    openai_model: str = os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini")
    embedding_model: str = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    days_back: int = int(os.getenv("DAYS_BACK", "7"))
    top_n: int = int(os.getenv("TOP_N", "5"))
    max_revisions: int = int(os.getenv("MAX_REVISIONS", "2"))
    min_items: int = int(os.getenv("MIN_ITEMS", "5"))
    search_results_per_query: int = int(os.getenv("SEARCH_RESULTS_PER_QUERY", "6"))
    max_snippet_chars: int = int(os.getenv("MAX_SNIPPET_CHARS", "600"))
    audience: str = os.getenv("AUDIENCE", "backend Python engineer")
    language: str = os.getenv("DIGEST_LANGUAGE", "Ukrainian")
    judge_threshold: float = float(os.getenv("JUDGE_THRESHOLD", "4.0"))
    semantic_dedupe: bool = os.getenv("SEMANTIC_DEDUPE", "1") == "1"
    semantic_threshold: float = float(os.getenv("SEMANTIC_THRESHOLD", "0.86"))
    memory_enabled: bool = os.getenv("MEMORY_ENABLED", "1") == "1"
    memory_dir: str = os.getenv("MEMORY_DIR", ".trend_scout_memory")
    memory_threshold: float = float(os.getenv("MEMORY_THRESHOLD", "0.88"))


settings = Settings()
