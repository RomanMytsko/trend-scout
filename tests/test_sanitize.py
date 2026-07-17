from trend_scout import sanitize
from trend_scout.schemas import RawItem


def test_clean_text_strips_html_collapses_ws_and_caps():
    raw = "<p>Hello&nbsp;   <b>world</b></p>\n\n  and   more"
    assert sanitize.clean_text(raw, 11) == "Hello world"
    assert sanitize.clean_text("", 100) == ""
    assert sanitize.clean_text(None, 100) == ""


def test_render_items_block_is_indexed_and_delimited():
    items = [
        RawItem(title="A", url="https://a.io/x", source="rss", snippet="s1"),
        RawItem(title="B", url="https://b.io/y", source="web", snippet="s2"),
    ]
    block = sanitize.render_items_block(items)
    assert '<item index="0" source="rss"' in block
    assert '<item index="1" source="web"' in block
    assert block.count("</item>") == 2


def test_extract_violating_urls_allows_collected_and_flags_foreign():
    allowed = {"https://a.io/x/", "https://b.io/y"}
    digest = (
        "# Digest\n"
        "- [ok one](https://a.io/x)\n"          # trailing-slash normalization
        "- [ok two](https://b.io/y/)\n"
        "- [evil](https://phish.example.com/p)\n"
    )
    violations = sanitize.extract_violating_urls(digest, allowed)
    assert violations == ["https://phish.example.com/p"]


def test_extract_violating_urls_empty_digest():
    assert sanitize.extract_violating_urls("no links here", {"https://a.io"}) == []
