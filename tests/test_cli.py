import sys

from trend_scout import __main__


def test_blocked_run_exits_nonzero_and_does_not_export_digest(tmp_path, monkeypatch, capsys):
    output = tmp_path / "blocked.md"
    monkeypatch.setattr(
        __main__.graph,
        "run_digest",
        lambda topics: {
            "digest": "# Rejected draft",
            "delivery_status": "blocked",
            "events": ["quality_gate: BLOCKED"],
        },
    )
    monkeypatch.setattr(sys, "argv", ["trend-scout", "agents", "--out", str(output)])

    assert __main__.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "delivery status: blocked" in captured.err
    assert not output.exists()


def test_preview_run_exits_zero_and_can_export_digest(tmp_path, monkeypatch, capsys):
    output = tmp_path / "digest.md"
    monkeypatch.setattr(
        __main__.graph,
        "run_digest",
        lambda topics: {
            "digest": "# Approved preview",
            "delivery_status": "preview",
            "events": ["publisher: preview"],
        },
    )
    monkeypatch.setattr(sys, "argv", ["trend-scout", "agents", "--out", str(output)])

    assert __main__.main() == 0
    captured = capsys.readouterr()
    assert "# Approved preview" in captured.out
    assert output.read_text(encoding="utf-8") == "# Approved preview"
