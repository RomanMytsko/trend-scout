"""Semantic clustering and cross-run memory, offline (fake embeddings)."""

import chromadb
import pytest

from trend_scout import memory, semantic
from trend_scout.schemas import RawItem

A = [1.0, 0.0, 0.0]
A_CLOSE = [0.98, 0.2, 0.0]  # cosine(A, A_CLOSE) ~ 0.98
B = [0.0, 1.0, 0.0]
C = [0.0, 0.0, 1.0]


def test_cosine_bounds():
    assert semantic.cosine(A, A) == pytest.approx(1.0)
    assert semantic.cosine(A, B) == pytest.approx(0.0)
    assert semantic.cosine(A, []) == 0.0


def test_cluster_drops_near_duplicates_keeps_first():
    keep = semantic.cluster_keep_indices([A, A_CLOSE, B, C], threshold=0.86)
    assert keep == [0, 2, 3]


def test_cluster_keeps_everything_below_threshold():
    assert semantic.cluster_keep_indices([A, B, C], threshold=0.86) == [0, 1, 2]


@pytest.fixture()
def client():
    return chromadb.EphemeralClient()


def test_memory_empty_collection_keeps_all(client):
    assert memory.filter_unseen_indices([A, B], client=client) == [0, 1]


def test_memory_filters_previously_delivered_stories(client):
    items = [RawItem(title="story", url="https://x.io/1", source="s")]
    stored = memory.remember(items, [A], client=client)
    assert stored == 1

    keep = memory.filter_unseen_indices([A_CLOSE, B], client=client, threshold=0.88)
    assert keep == [1]  # A_CLOSE matches the remembered story, B is new


def test_memory_remember_empty_is_noop(client):
    assert memory.remember([], [], client=client) == 0
