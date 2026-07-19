"""Semantic near-duplicate detection over OpenAI embeddings.

URL-level dedupe cannot catch the same story republished by different
outlets. Here every item is embedded once (``title + snippet`` prefix) and
greedy clustering drops items too similar to an already kept one. The same
embeddings are reused by the cross-run memory (:mod:`trend_scout.memory`).
"""

import functools
import math

import langchain_openai

from trend_scout.config import settings
from trend_scout.schemas import RawItem


@functools.lru_cache(maxsize=1)
def _embedder() -> langchain_openai.OpenAIEmbeddings:
    return langchain_openai.OpenAIEmbeddings(model=settings.embedding_model)


def embed_items(items: list[RawItem]) -> list[list[float]]:
    """One embedding per item over its title and snippet prefix."""
    texts = [f"{item.title}\n{item.snippet[:300]}" for item in items]
    return _embedder().embed_documents(texts)


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)


def cluster_keep_indices(vectors: list[list[float]], threshold: float) -> list[int]:
    """Greedy clustering: keep an item unless it duplicates an already kept one.

    Items are assumed to be ordered by preference (curated RSS feeds first),
    so the first occurrence of a story wins.
    """
    kept: list[int] = []
    for i, vector in enumerate(vectors):
        if all(cosine(vector, vectors[j]) < threshold for j in kept):
            kept.append(i)
    return kept
