"""Guardrails for untrusted external content (prompt-injection surface).

Everything fetched from the web (titles, snippets, RSS summaries) is treated
as data, never as instructions:

* HTML is stripped, whitespace collapsed, length capped;
* content is rendered inside numbered ``<item>`` blocks so prompts can
  reference it explicitly as untrusted;
* the final digest may only link to URLs that were actually collected
  (deterministic allowlist check, see :func:`extract_violating_urls`).
"""

import html
import re

from trend_scout.schemas import RawItem

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_MD_LINK_RE = re.compile(r"\]\((https?://[^)\s]+)\)")


def clean_text(text: str, max_chars: int) -> str:
    """Strip HTML, collapse whitespace, cap length."""
    text = html.unescape(text or "")
    text = _TAG_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    return text[:max_chars]


def render_items_block(items: list[RawItem]) -> str:
    """Render candidates as numbered blocks of untrusted data for prompts."""
    blocks = []
    for i, item in enumerate(items):
        blocks.append(
            f'<item index="{i}" source="{item.source}" published="{item.published or "n/a"}">\n'
            f"title: {item.title}\nurl: {item.url}\nsnippet: {item.snippet}\n</item>"
        )
    return "\n".join(blocks)


def extract_violating_urls(digest_md: str, allowed_urls: set[str]) -> list[str]:
    """Return markdown-linked URLs that were not present in collected items."""
    linked = _MD_LINK_RE.findall(digest_md)
    normalized_allowed = {u.rstrip("/") for u in allowed_urls}
    return [u for u in linked if u.rstrip("/") not in normalized_allowed]
