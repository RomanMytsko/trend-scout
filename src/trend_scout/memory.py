"""Cross-run memory of already-delivered stories (ChromaDB).

Every approved digest archives the embeddings of its items. On the next run
candidates semantically close to anything delivered before are dropped, so
weekly digests do not repeat last week's stories.

All functions accept an optional Chroma client for testability; by default a
persistent client under ``settings.memory_dir`` is used.
"""

import functools
import hashlib
import logging

import chromadb

from trend_scout.config import settings
from trend_scout.schemas import RawItem

logger = logging.getLogger(__name__)

COLLECTION = "delivered_items"


@functools.lru_cache(maxsize=1)
def _default_client() -> chromadb.api.ClientAPI:
    return chromadb.PersistentClient(path=settings.memory_dir)


def _collection(client: chromadb.api.ClientAPI | None = None):
    client = client or _default_client()
    return client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})


def filter_unseen_indices(
    embeddings: list[list[float]],
    client: chromadb.api.ClientAPI | None = None,
    threshold: float | None = None,
) -> list[int]:
    """Indices of items that were not delivered in previous runs."""
    if not embeddings:
        return []
    threshold = threshold if threshold is not None else settings.memory_threshold
    collection = _collection(client)
    if collection.count() == 0:
        return list(range(len(embeddings)))

    result = collection.query(query_embeddings=embeddings, n_results=1)
    kept: list[int] = []
    for i, distances in enumerate(result["distances"]):
        similarity = 1 - distances[0] if distances else 0.0
        if similarity < threshold:
            kept.append(i)
    return kept


def remember(
    items: list[RawItem],
    embeddings: list[list[float]],
    client: chromadb.api.ClientAPI | None = None,
) -> int:
    """Archive delivered items; returns how many were stored."""
    if not items:
        return 0
    collection = _collection(client)
    collection.upsert(
        ids=[hashlib.sha256(item.url.rstrip("/").lower().encode()).hexdigest() for item in items],
        embeddings=embeddings,
        metadatas=[{"url": item.url, "title": item.title} for item in items],
    )
    return len(items)
