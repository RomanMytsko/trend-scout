"""Runtime configuration loaded from environment variables."""

import dataclasses
import os

import dotenv

dotenv.load_dotenv()

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


@dataclasses.dataclass(frozen=True)
class Settings:
    openai_model: str = os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini")
    days_back: int = int(os.getenv("DAYS_BACK", "7"))
    top_n: int = int(os.getenv("TOP_N", "5"))
    max_revisions: int = int(os.getenv("MAX_REVISIONS", "2"))
    min_items: int = int(os.getenv("MIN_ITEMS", "5"))
    search_results_per_query: int = int(os.getenv("SEARCH_RESULTS_PER_QUERY", "6"))
    max_snippet_chars: int = int(os.getenv("MAX_SNIPPET_CHARS", "600"))
    audience: str = os.getenv("AUDIENCE", "backend Python engineer")
    language: str = os.getenv("DIGEST_LANGUAGE", "Ukrainian")
    judge_threshold: float = float(os.getenv("JUDGE_THRESHOLD", "4.0"))


settings = Settings()
