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
    chunks = publisher.split_telegram_html("x" * 6000)
    assert all(len(chunk) <= publisher.TELEGRAM_LIMIT for chunk in chunks)
    assert chunks[0].endswith("…")


def test_long_post_splits_between_complete_html_lines():
    item = "## Item\n- Лінк: [source](https://example.com/path)\n" + ("текст\n" * 900)
    chunks = publisher.split_telegram_html(item)
    assert len(chunks) > 1
    assert all(len(chunk) <= publisher.TELEGRAM_LIMIT for chunk in chunks)
    assert all(chunk.count("<a ") == chunk.count("</a>") for chunk in chunks)


def test_dry_run_without_channel_saves_preview(tmp_path):
    preview = tmp_path / "post.html"
    result = publisher.publish(
        "# Test\n[link](https://a.io)", token="", channel_id="", preview_path=str(preview)
    )
    assert result.status == "preview"
    assert "dry-run" in result.event
    assert preview.read_text(encoding="utf-8") == result.post_html
    assert "<b>Test</b>" in result.post_html


def test_failed_send_degrades_to_preview(tmp_path, monkeypatch):
    def boom(post, token, channel_id):
        raise RuntimeError("Telegram API error: chat not found")

    monkeypatch.setattr(publisher, "send_to_telegram", boom)
    preview = tmp_path / "post.html"
    result = publisher.publish(
        "# T", token="123:abc", channel_id="@nope", preview_path=str(preview)
    )
    assert result.status == "failed"
    assert "FAILED" in result.event
    assert preview.exists()


def test_successful_send_reports_sent(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(
        publisher,
        "send_to_telegram",
        lambda post, token, channel_id: sent.append((post, token, channel_id)),
    )
    result = publisher.publish(
        "# T",
        token="123:abc",
        channel_id="@channel",
        preview_path=str(tmp_path / "post.html"),
        journal_path=str(tmp_path / "delivery.json"),
    )
    assert result.status == "sent"
    assert sent == [("<b>T</b>", "123:abc", "@channel")]


def test_retry_resumes_after_last_confirmed_chunk(tmp_path, monkeypatch):
    journal = tmp_path / "delivery.json"
    monkeypatch.setattr(publisher, "split_telegram_html", lambda digest: ["one", "two", "three"])

    first_attempt = []

    def fail_on_second(post, token, channel_id):
        first_attempt.append(post)
        if post == "two":
            raise RuntimeError("temporary Telegram failure")

    monkeypatch.setattr(publisher, "send_to_telegram", fail_on_second)
    first = publisher.publish(
        "same digest",
        token="123:abc",
        channel_id="@channel",
        preview_path=str(tmp_path / "post.html"),
        journal_path=str(journal),
    )

    assert first.status == "failed"
    assert first_attempt == ["one", "two"]

    resumed_attempt = []
    monkeypatch.setattr(
        publisher,
        "send_to_telegram",
        lambda post, token, channel_id: resumed_attempt.append(post),
    )
    resumed = publisher.publish(
        "same digest",
        token="123:abc",
        channel_id="@channel",
        preview_path=str(tmp_path / "post.html"),
        journal_path=str(journal),
    )

    assert resumed.status == "sent"
    assert resumed_attempt == ["two", "three"]

    already_complete = []
    monkeypatch.setattr(
        publisher,
        "send_to_telegram",
        lambda post, token, channel_id: already_complete.append(post),
    )
    repeated = publisher.publish(
        "same digest",
        token="123:abc",
        channel_id="@channel",
        preview_path=str(tmp_path / "post.html"),
        journal_path=str(journal),
    )

    assert repeated.status == "sent"
    assert already_complete == []
    assert "already completed" in repeated.event
