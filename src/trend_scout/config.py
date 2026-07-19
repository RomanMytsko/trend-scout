"""Runtime configuration loaded from environment variables."""

import dataclasses
import json
import logging
import os
import urllib.parse

import dotenv

dotenv.load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_FEEDS: dict[str, str] = {
    "Hacker News (AI agents)": "https://hnrss.org/newest?q=AI+agents",
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
    normalized = {
        str(name).strip(): str(url).strip()
        for name, url in feeds.items()
        if str(name).strip()
        and urllib.parse.urlsplit(str(url).strip()).scheme in {"http", "https"}
    }
    if not normalized:
        logger.warning("RSS_FEEDS_JSON has no valid HTTP(S) feeds, using default feeds.")
        return DEFAULT_FEEDS
    return normalized


FEEDS = feeds_from_env()


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("%s must be an integer, using %s.", name, default)
        return default
    if value < minimum:
        logger.warning("%s must be >= %s, using %s.", name, minimum, default)
        return default
    return value


def _env_float(
    name: str, default: float, minimum: float = 0.0, maximum: float | None = None
) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.warning("%s must be a number, using %s.", name, default)
        return default
    if value < minimum or (maximum is not None and value > maximum):
        logger.warning("%s is outside the supported range, using %s.", name, default)
        return default
    return value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    logger.warning("%s must be a boolean, using %s.", name, default)
    return default


@dataclasses.dataclass(frozen=True)
class Settings:
    openai_model: str = os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini")
    judge_model: str = os.getenv("OPENAI_JUDGE_MODEL") or os.getenv(
        "OPENAI_CHAT_MODEL", "gpt-4.1-mini"
    )
    embedding_model: str = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    days_back: int = _env_int("DAYS_BACK", 7, minimum=1)
    top_n: int = _env_int("TOP_N", 5, minimum=1)
    max_revisions: int = _env_int("MAX_REVISIONS", 2)
    max_replans: int = _env_int("MAX_REPLANS", 1)
    min_items: int = _env_int("MIN_ITEMS", 5, minimum=1)
    min_curated_items: int = _env_int("MIN_CURATED_ITEMS", 3, minimum=1)
    search_results_per_query: int = _env_int("SEARCH_RESULTS_PER_QUERY", 6, minimum=1)
    max_snippet_chars: int = _env_int("MAX_SNIPPET_CHARS", 600, minimum=100)
    search_workers: int = _env_int("SEARCH_WORKERS", 4, minimum=1)
    audience: str = os.getenv("AUDIENCE", "backend Python engineer")
    language: str = os.getenv("DIGEST_LANGUAGE", "Ukrainian")
    judge_threshold: float = _env_float("JUDGE_THRESHOLD", 4.0, minimum=1.0, maximum=5.0)
    semantic_dedupe: bool = _env_bool("SEMANTIC_DEDUPE", True)
    semantic_threshold: float = _env_float(
        "SEMANTIC_THRESHOLD", 0.86, minimum=0.0, maximum=1.0
    )
    memory_enabled: bool = _env_bool("MEMORY_ENABLED", True)
    memory_dir: str = os.getenv("MEMORY_DIR", ".trend_scout_memory")
    memory_threshold: float = _env_float(
        "MEMORY_THRESHOLD", 0.88, minimum=0.0, maximum=1.0
    )
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_channel_id: str = os.getenv("TELEGRAM_CHANNEL_ID", "")
    post_preview_path: str = os.getenv("POST_PREVIEW_PATH", "telegram_post_preview.html")
    delivery_journal_path: str = os.getenv(
        "DELIVERY_JOURNAL_PATH", ".trend_scout_delivery.json"
    )

    @property
    def search_timelimit(self) -> str:
        """DuckDuckGo news recency: last day for daily digests, else week."""
        return "d" if self.days_back <= 1 else "w"


settings = Settings()
