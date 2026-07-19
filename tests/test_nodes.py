from trend_scout import nodes
from trend_scout.schemas import CuratedPick, CurationResult, RawItem


def _state(delivery_status: str):
    return {
        "delivery_status": delivery_status,
        "items": [RawItem(title="story", url="https://x.io/1", source="s")],
        "item_embeddings": [[1.0, 0.0]],
        "curation": CurationResult(
            picks=[CuratedPick(index=0, relevance=5, why_it_matters="relevant")]
        ),
    }


def test_archive_skips_preview_and_failed_delivery(monkeypatch):
    monkeypatch.setattr(nodes.memory, "remember", lambda *args, **kwargs: 1)
    for status in ("preview", "failed", "blocked"):
        result = nodes.archive(_state(status))
        assert f"delivery status {status}" in result["events"][0]


def test_archive_remembers_only_sent_delivery(monkeypatch):
    calls = []
    monkeypatch.setattr(
        nodes.memory,
        "remember",
        lambda items, embeddings: calls.append((items, embeddings)) or len(items),
    )
    result = nodes.archive(_state("sent"))
    assert calls
    assert result["events"] == ["archive: remembered 1 delivered stories"]


def test_curator_deduplicates_indexes(monkeypatch):
    curation = CurationResult(
        picks=[
            CuratedPick(index=0, relevance=5, why_it_matters="first"),
            CuratedPick(index=0, relevance=4, why_it_matters="duplicate"),
            CuratedPick(index=1, relevance=4, why_it_matters="second"),
        ]
    )

    class FakeStructured:
        def invoke(self, messages):
            return curation

    monkeypatch.setattr(nodes, "_structured", lambda schema: FakeStructured())
    state = {
        "topics": ["agents"],
        "items": [
            RawItem(title="a", url="https://a.io", source="s"),
            RawItem(title="b", url="https://b.io", source="s"),
        ],
    }
    result = nodes.curator(state)
    assert [pick.index for pick in result["curation"].picks] == [0, 1]
