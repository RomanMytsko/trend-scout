"""Publish the approved digest to a Telegram channel.

Fully working publisher with a mock-friendly default: when
``TELEGRAM_CHANNEL_ID`` is not configured the post is rendered and saved
locally (dry run), so the channel URL can be plugged in later without any
code changes. With ``TELEGRAM_BOT_TOKEN`` + ``TELEGRAM_CHANNEL_ID`` set the
post goes to the real channel via the Bot API.
"""

import html
import json
import logging
import pathlib
import re
import urllib.error
import urllib.request

from trend_scout.config import settings

logger = logging.getLogger(__name__)

TELEGRAM_LIMIT = 4096
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_HEADING_RE = re.compile(r"^#{1,6}\s*(.+)$")


def to_telegram_html(digest_md: str) -> str:
    """Convert digest markdown to Telegram-flavoured HTML.

    Headings become bold lines, markdown links become anchors, list dashes
    become bullets; everything else is escaped.
    """
    lines_out: list[str] = []
    for line in digest_md.splitlines():
        heading = _HEADING_RE.match(line.strip())
        if heading:
            lines_out.append(f"<b>{html.escape(heading.group(1))}</b>")
            continue

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
        lines_out.append(rendered)
    post = "\n".join(lines_out).strip()
    if len(post) > TELEGRAM_LIMIT:
        post = post[: TELEGRAM_LIMIT - 1] + "…"
    return post


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
) -> tuple[str, str]:
    """Render and deliver the post; returns ``(pipeline_event, post_html)``.

    Dry run (no channel configured) saves the rendered post to
    ``preview_path`` — plug the real channel id in later, nothing else
    changes. Failures degrade gracefully: the digest itself is never lost.
    """
    token = token if token is not None else settings.telegram_bot_token
    channel_id = channel_id if channel_id is not None else settings.telegram_channel_id
    preview_path = preview_path or settings.post_preview_path

    post = to_telegram_html(digest_md)

    if not token or not channel_id:
        path = pathlib.Path(preview_path)
        path.write_text(post, encoding="utf-8")
        return f"publisher: dry-run (channel not configured), post saved to {path}", post

    try:
        send_to_telegram(post, token, channel_id)
    except (urllib.error.URLError, RuntimeError, TimeoutError) as exc:
        logger.warning("Telegram publish failed: %s", exc)
        path = pathlib.Path(preview_path)
        path.write_text(post, encoding="utf-8")
        return f"publisher: FAILED ({exc}), post saved to {path}", post
    return f"publisher: posted to Telegram channel {channel_id}", post
