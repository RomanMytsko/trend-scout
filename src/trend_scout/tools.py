"""Worker tools: RSS feeds and web search.

Both tools degrade gracefully: any network/parse failure yields an empty
list instead of crashing the pipeline (the researcher node decides whether
enough material was collected).
"""

import calendar
import datetime
import logging

import feedparser

from trend_scout import sanitize
from trend_scout.config import FEEDS, settings
from trend_scout.schemas import RawItem

logger = logging.getLogger(__name__)


def _entry_datetime(entry: object) -> datetime.datetime | None:
    parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if parsed is None:
        return None
    return datetime.datetime.fromtimestamp(calendar.timegm(parsed), tz=datetime.timezone.utc)


def fetch_rss(days_back: int | None = None) -> list[RawItem]:
    """Fetch fresh entries from the curated feed list."""
    days_back = days_back or settings.days_back
    cutoff = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(days=days_back)
    items: list[RawItem] = []
    for source, url in FEEDS.items():
        try:
            feed = feedparser.parse(url)
        except Exception as exc:  # expected degradation, keep the log short
            logger.warning("RSS fetch failed for %s: %s", source, exc)
            continue
        for entry in feed.entries:
            published = _entry_datetime(entry)
            if published is not None and published < cutoff:
                continue
            items.append(
                RawItem(
                    title=sanitize.clean_text(getattr(entry, "title", ""), 200),
                    url=getattr(entry, "link", ""),
                    source=source,
                    published=published.date().isoformat() if published else None,
                    snippet=sanitize.clean_text(
                        getattr(entry, "summary", ""), settings.max_snippet_chars
                    ),
                )
            )
    return items


def web_search(query: str, max_results: int | None = None) -> list[RawItem]:
    """DuckDuckGo news search for one query. No API key required."""
    max_results = max_results or settings.search_results_per_query
    try:
        from ddgs import DDGS
    except ImportError:  # older package name
        from duckduckgo_search import DDGS

    try:
        with DDGS() as ddgs:
            results = list(
                ddgs.news(query, max_results=max_results, timelimit=settings.search_timelimit)
            )
    except Exception as exc:  # rate limits are routine, a one-line warning is enough
        logger.warning("Web search failed for query %r: %s", query, exc)
        return []

    return [
        RawItem(
            title=sanitize.clean_text(r.get("title", ""), 200),
            url=r.get("url", ""),
            source=f"web: {r.get('source', 'unknown')}",
            published=(r.get("date") or "")[:10] or None,
            snippet=sanitize.clean_text(r.get("body", ""), settings.max_snippet_chars),
        )
        for r in results
        if r.get("url")
    ]


def dedupe(items: list[RawItem]) -> list[RawItem]:
    """Drop duplicates by normalized URL, keep first occurrence."""
    seen: set[str] = set()
    unique: list[RawItem] = []
    for item in items:
        key = item.url.rstrip("/").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique
