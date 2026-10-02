"""Retrieval metrics over binary relevance judgements.

Relevance is judged at the *legal unit* level (document + section) so that results are
comparable across chunking strategies that cut the same section differently. Each retrieved
chunk carries the set of units its character span overlaps (a chunk spanning two sections covers
both; a structure-unaware chunk is judged by where its text actually lies):

* Precision@K — fraction of the top-K chunks that belong to a relevant unit.
* Recall@K    — fraction of the expected units covered by at least one top-K chunk.
* HitRate@K   — 1 if any top-K chunk is relevant.
* MRR         — reciprocal rank of the first relevant chunk (0 if none in the list).
* nDCG@K      — binary-gain DCG over chunks; the ideal ranking places one relevant chunk per
                expected unit first, i.e. IDCG uses min(K, |expected units|) gains.
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def precision_at_k(relevant_flags: Sequence[bool], k: int) -> float:
    top = list(relevant_flags[:k])
    return sum(top) / k if k else 0.0


def recall_at_k(retrieved_units: Sequence[set[str]], expected_units: set[str], k: int) -> float:
    if not expected_units:
        return 0.0
    covered: set[str] = set()
    for units in retrieved_units[:k]:
        covered |= units & expected_units
    return len(covered) / len(expected_units)


def hit_rate_at_k(relevant_flags: Sequence[bool], k: int) -> float:
    return 1.0 if any(relevant_flags[:k]) else 0.0


def mrr(relevant_flags: Sequence[bool]) -> float:
    for i, flag in enumerate(relevant_flags, start=1):
        if flag:
            return 1.0 / i
    return 0.0


def ndcg_at_k(retrieved_units: Sequence[set[str]], expected_units: set[str], k: int) -> float:
    """Binary gain at a rank when the chunk covers at least one not-yet-seen expected unit."""
    if not expected_units:
        return 0.0
    seen: set[str] = set()
    dcg = 0.0
    for i, units in enumerate(retrieved_units[:k], start=1):
        new = (units & expected_units) - seen
        if new:
            seen |= new
            dcg += 1.0 / math.log2(i + 1)
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(k, len(expected_units)) + 1))
    return dcg / ideal if ideal else 0.0
