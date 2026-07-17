from trend_scout import tools
from trend_scout.schemas import RawItem


def _item(url: str) -> RawItem:
    return RawItem(title="t", url=url, source="s", snippet="")


def test_dedupe_normalizes_trailing_slash_and_case():
    items = [
        _item("https://a.io/x"),
        _item("https://a.io/x/"),
        _item("HTTPS://A.IO/X"),
        _item("https://b.io/y"),
    ]
    unique = tools.dedupe(items)
    assert [i.url for i in unique] == ["https://a.io/x", "https://b.io/y"]


def test_dedupe_drops_items_without_url():
    items = [_item(""), _item("https://a.io")]
    assert [i.url for i in tools.dedupe(items)] == ["https://a.io"]


def test_dedupe_keeps_first_occurrence():
    first = _item("https://a.io/x")
    second = _item("https://a.io/x/")
    second.title = "duplicate"
    assert tools.dedupe([first, second])[0].title == "t"
