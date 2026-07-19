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
_URL_RE = re.compile(r"https?://[^\s)\]>\"']+")


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
        source = html.escape(item.source, quote=True)
        published = html.escape(item.published or "n/a", quote=True)
        title = html.escape(item.title, quote=True)
        url = html.escape(item.url, quote=True)
        snippet = html.escape(item.snippet, quote=True)
        blocks.append(
            f'<item index="{i}" source="{source}" published="{published}">\n'
            f"title: {title}\nurl: {url}\nsnippet: {snippet}\n</item>"
        )
    return "\n".join(blocks)


def extract_violating_urls(digest_md: str, allowed_urls: set[str]) -> list[str]:
    """Return any URL in the digest (markdown-linked or bare) that was not
    present in collected items."""
    normalized_allowed = {u.rstrip("/") for u in allowed_urls}
    violations: list[str] = []
    for url in _URL_RE.findall(digest_md):
        normalized = url.rstrip(".,;:!?").rstrip("/")
        if normalized not in normalized_allowed and normalized not in violations:
            violations.append(normalized)
    return violations


def validate_digest_structure(digest_md: str, expected_items: int) -> list[str]:
    """Return deterministic violations of the required digest structure."""
    lines = [line.strip() for line in digest_md.splitlines() if line.strip()]
    if not lines or not lines[0].startswith("# ") or lines[0].startswith("## "):
        return ["digest must start with a level-one '# ' title"]

    section_starts = [i for i, line in enumerate(lines) if re.match(r"^##\s+\d+\.\s+", line)]
    violations: list[str] = []
    if len(section_starts) != expected_items:
        violations.append(
            f"expected {expected_items} numbered item sections, found {len(section_starts)}"
        )
    if expected_items and (not section_starts or section_starts[0] < 2):
        violations.append("digest must contain an intro sentence before the first item")

    for number, start in enumerate(section_starts, 1):
        end = section_starts[number] if number < len(section_starts) else len(lines)
        section = lines[start + 1 : end]
        for label in ("- Суть:", "- Чому важливо:", "- Лінк:"):
            if sum(line.startswith(label) for line in section) != 1:
                violations.append(f"item {number} must contain exactly one '{label}' line")
    return violations
