"""Small, dependency-free text utilities shared across the RAG stack."""

from __future__ import annotations

import hashlib
import re
import unicodedata

_TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)
_WORD_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def count_tokens(text: str) -> int:
    """Approximate token count (word + punctuation units).

    Deterministic and model-independent; sub-word tokenizers typically produce ~1.2-1.4x more.
    Used consistently for chunk sizing and context budgeting.
    """
    return len(_TOKEN_RE.findall(text))


def token_spans(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _TOKEN_RE.finditer(text)]


def words(text: str) -> list[str]:
    return [w.lower() for w in _WORD_RE.findall(text)]


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_unicode(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    return text.replace(" ", " ")


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)
