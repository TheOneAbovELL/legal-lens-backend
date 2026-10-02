"""Lexical sparse encoder (BM25-style) for Qdrant sparse vectors.

Documents get BM25 term-frequency saturation weights; Qdrant's ``Modifier.IDF`` supplies the
inverse document frequency at query time, so the corpus-wide statistics stay in the index and
nothing has to be held in application memory.
"""

from __future__ import annotations

import re
import zlib
from collections import Counter

from pydantic import BaseModel

_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)

# Compact English stop-word list; legal function words ("shall", "whoever") are kept on purpose.
STOPWORDS = frozenset(
    """a an and are as at be been but by for from has have he her his i if in into is it its
    me my of on or our she so than that the their them then there these they this those to
    was we were what when where which who whom will with you your do does did can could would
    should about please tell explain""".split()
)

# Canonicalise common legal abbreviations so "sec. 420" and "section 420" share terms.
_SYNONYMS = {
    "sec": "section",
    "secs": "section",
    "ss": "section",
    "sections": "section",
    "art": "article",
    "arts": "article",
    "articles": "article",
    "u": "",  # from "u/s"
    "s": "",
}


class SparseVector(BaseModel):
    indices: list[int]
    values: list[float]


def lexical_terms(text: str) -> list[str]:
    terms: list[str] = []
    for raw in _TOKEN_RE.findall(text.lower()):
        term = _SYNONYMS.get(raw, raw)
        if term and term not in STOPWORDS:
            terms.append(term)
    return terms


def term_index(term: str) -> int:
    # Stable across processes (unlike hash()); 31-bit to stay within Qdrant's uint32 range.
    return zlib.crc32(term.encode("utf-8")) & 0x7FFFFFFF


class SparseEncoder:
    def __init__(self, k1: float = 1.2, b: float = 0.75, avg_doc_len: float = 120.0) -> None:
        self.k1 = k1
        self.b = b
        self.avg_doc_len = avg_doc_len

    def encode_document(self, text: str) -> SparseVector:
        terms = lexical_terms(text)
        if not terms:
            return SparseVector(indices=[], values=[])
        counts = Counter(terms)
        length_norm = 1 - self.b + self.b * (len(terms) / self.avg_doc_len)
        weights: dict[int, float] = {}
        for term, tf in counts.items():
            weight = tf * (self.k1 + 1) / (tf + self.k1 * length_norm)
            idx = term_index(term)
            weights[idx] = weights.get(idx, 0.0) + weight
        indices = sorted(weights)
        return SparseVector(indices=indices, values=[weights[i] for i in indices])

    def encode_query(self, text: str) -> SparseVector:
        indices = sorted({term_index(t) for t in lexical_terms(text)})
        return SparseVector(indices=indices, values=[1.0] * len(indices))
