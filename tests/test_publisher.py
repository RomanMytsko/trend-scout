from trend_scout import publisher


def test_markdown_converts_to_telegram_html():
    md = "# Дайджест\nВступ.\n## 1. Title\n- Суть: коротко <тест> & ще.\n- Лінк: [Джерело](https://a.io/x?a=1&b=2)"
    post = publisher.to_telegram_html(md)
    assert "<b>Дайджест</b>" in post
    assert "<b>1. Title</b>" in post
    assert "• Суть: коротко &lt;тест&gt; &amp; ще." in post
    assert '<a href="https://a.io/x?a=1&amp;b=2">Джерело</a>' in post
    assert "](" not in post


def test_post_is_truncated_to_telegram_limit():
    post = publisher.to_telegram_html("x" * 6000)
    assert len(post) <= publisher.TELEGRAM_LIMIT
    assert post.endswith("…")


def test_dry_run_without_channel_saves_preview(tmp_path):
    preview = tmp_path / "post.html"
    event, post = publisher.publish(
        "# Test\n[link](https://a.io)", token="", channel_id="", preview_path=str(preview)
    )
    assert "dry-run" in event
    assert preview.read_text(encoding="utf-8") == post
    assert "<b>Test</b>" in post


def test_failed_send_degrades_to_preview(tmp_path, monkeypatch):
    def boom(post, token, channel_id):
        raise RuntimeError("Telegram API error: chat not found")

    monkeypatch.setattr(publisher, "send_to_telegram", boom)
    preview = tmp_path / "post.html"
    event, post = publisher.publish(
        "# T", token="123:abc", channel_id="@nope", preview_path=str(preview)
    )
    assert "FAILED" in event
    assert preview.exists()
