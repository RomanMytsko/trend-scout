"""Publish an approved digest with preview and resumable Telegram delivery."""

import dataclasses
import hashlib
import html
import json
import logging
import pathlib
import re
import typing
import urllib.error
import urllib.request

from trend_scout.config import settings

logger = logging.getLogger(__name__)

TELEGRAM_LIMIT = 4096
DELIVERY_JOURNAL_VERSION = 1
DELIVERY_JOURNAL_MAX_RECORDS = 100
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_HEADING_RE = re.compile(r"^#{1,6}\s*(.+)$")


@dataclasses.dataclass(frozen=True)
class PublishResult:
    status: typing.Literal["sent", "preview", "failed"]
    event: str
    post_html: str
    chunks: tuple[str, ...]


class DeliveryJournalError(RuntimeError):
    """Raised when delivery progress cannot be read or persisted safely."""


def _render_line(line: str) -> str:
    heading = _HEADING_RE.match(line.strip())
    if heading:
        return f"<b>{html.escape(heading.group(1))}</b>"

    parts: list[str] = []
    cursor = 0
    for match in _MD_LINK_RE.finditer(line):
        parts.append(html.escape(line[cursor : match.start()]))
        text, url = match.group(1), match.group(2)
        parts.append(f'<a href="{html.escape(url, quote=True)}">{html.escape(text)}</a>')
        cursor = match.end()
    parts.append(html.escape(line[cursor:]))
    rendered = "".join(parts)
    if rendered.lstrip().startswith("- "):
        rendered = rendered.replace("- ", "• ", 1)
    return rendered


def _truncate_plain_line(line: str, limit: int) -> str:
    parts: list[str] = []
    length = 0
    for character in line:
        escaped = html.escape(character)
        if length + len(escaped) + 1 > limit:
            break
        parts.append(escaped)
        length += len(escaped)
    return "".join(parts) + "…"


def to_telegram_html(digest_md: str) -> str:
    """Convert digest markdown to Telegram-flavoured HTML."""
    return "\n".join(_render_line(line) for line in digest_md.splitlines()).strip()


def split_telegram_html(digest_md: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    """Render Markdown into complete Telegram-safe HTML messages."""
    rendered_lines = []
    for line in digest_md.splitlines():
        rendered = _render_line(line)
        if len(rendered) > limit:
            rendered = _truncate_plain_line(line, limit)
        rendered_lines.append(rendered)

    chunks: list[str] = []
    current: list[str] = []
    for line in rendered_lines:
        candidate = "\n".join([*current, line]).strip()
        if current and len(candidate) > limit:
            chunks.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        chunks.append("\n".join(current).strip())
    return chunks or [""]


def save_preview(post_html: str, preview_path: str) -> pathlib.Path:
    path = pathlib.Path(preview_path)
    path.write_text(post_html, encoding="utf-8")
    return path


def _delivery_id(channel_id: str, chunks: list[str]) -> str:
    payload = json.dumps([channel_id, chunks], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _load_delivery_journal(path: pathlib.Path) -> dict:
    if not path.exists():
        return {"version": DELIVERY_JOURNAL_VERSION, "deliveries": {}}
    try:
        journal = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeliveryJournalError(f"cannot read delivery journal {path}: {exc}") from exc
    if (
        not isinstance(journal, dict)
        or journal.get("version") != DELIVERY_JOURNAL_VERSION
        or not isinstance(journal.get("deliveries"), dict)
    ):
        raise DeliveryJournalError(f"unsupported delivery journal format in {path}")
    return journal


def _save_delivery_journal(path: pathlib.Path, journal: dict) -> None:
    deliveries = journal["deliveries"]
    while len(deliveries) > DELIVERY_JOURNAL_MAX_RECORDS:
        deliveries.pop(next(iter(deliveries)))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_text(
            json.dumps(journal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(path)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise DeliveryJournalError(f"cannot persist delivery journal {path}: {exc}") from exc


def send_to_telegram(post_html: str, token: str, channel_id: str) -> None:
    """Send one message to a channel via the Bot API. Raises on failure."""
    payload = json.dumps(
        {
            "chat_id": channel_id,
            "text": post_html,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
    ).encode()
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        body = json.loads(response.read())
    if not body.get("ok"):
        raise RuntimeError(f"Telegram API error: {body}")


def publish(
    digest_md: str,
    token: str | None = None,
    channel_id: str | None = None,
    preview_path: str | None = None,
    journal_path: str | None = None,
) -> PublishResult:
    """Render and deliver the post, returning a structured delivery result.

    Dry run (no channel configured) saves the rendered post to
    ``preview_path`` — plug the real channel id in later, nothing else
    changes. Failures degrade gracefully: the digest itself is never lost.
    """
    token = token if token is not None else settings.telegram_bot_token
    channel_id = channel_id if channel_id is not None else settings.telegram_channel_id
    preview_path = preview_path or settings.post_preview_path
    journal_path = journal_path or settings.delivery_journal_path

    chunks = split_telegram_html(digest_md)
    post = "\n\n<!-- Telegram message boundary -->\n\n".join(chunks)

    if not token or not channel_id:
        path = save_preview(post, preview_path)
        return PublishResult(
            status="preview",
            event=f"publisher: dry-run (channel not configured), post saved to {path}",
            post_html=post,
            chunks=tuple(chunks),
        )

    journal_file = pathlib.Path(journal_path)
    delivery_id = _delivery_id(channel_id, chunks)
    try:
        journal = _load_delivery_journal(journal_file)
        entry = journal["deliveries"].setdefault(
            delivery_id,
            {"channel_id": channel_id, "next_chunk": 0, "total_chunks": len(chunks)},
        )
        next_chunk = entry.get("next_chunk")
        if (
            not isinstance(next_chunk, int)
            or next_chunk < 0
            or entry.get("total_chunks") != len(chunks)
        ):
            raise DeliveryJournalError("delivery checkpoint is inconsistent")
        if next_chunk >= len(chunks):
            return PublishResult(
                status="sent",
                event="publisher: delivery already completed; no chunks resent",
                post_html=post,
                chunks=tuple(chunks),
            )
        resumed_from = next_chunk
        for index in range(next_chunk, len(chunks)):
            chunk = chunks[index]
            send_to_telegram(chunk, token, channel_id)
            entry["next_chunk"] = index + 1
            _save_delivery_journal(journal_file, journal)
    except (DeliveryJournalError, urllib.error.URLError, RuntimeError, TimeoutError) as exc:
        logger.warning("Telegram publish failed: %s", exc)
        path = save_preview(post, preview_path)
        checkpoint = entry.get("next_chunk", 0) if "entry" in locals() else 0
        return PublishResult(
            status="failed",
            event=(
                f"publisher: FAILED ({exc}), resume checkpoint {checkpoint}/{len(chunks)}, "
                f"post saved to {path}"
            ),
            post_html=post,
            chunks=tuple(chunks),
        )
    suffix = f" ({len(chunks)} messages)" if len(chunks) > 1 else ""
    resume_suffix = f", resumed at message {resumed_from + 1}" if resumed_from else ""
    return PublishResult(
        status="sent",
        event=f"publisher: posted to Telegram channel {channel_id}{suffix}{resume_suffix}",
        post_html=post,
        chunks=tuple(chunks),
    )
