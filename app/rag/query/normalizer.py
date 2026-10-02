"""Deterministic query normalisation (no LLM)."""

from __future__ import annotations

import re

from app.core.text import normalize_unicode

_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bu/s\.?\s*", re.IGNORECASE), "under Section "),
    (re.compile(r"\br/w\b\.?", re.IGNORECASE), "read with"),
    (re.compile(r"\bw\.e\.f\.?", re.IGNORECASE), "with effect from"),
    (re.compile(r"\bsecs?\.\s*(?=\d)", re.IGNORECASE), "Section "),
    (re.compile(r"\barts?\.\s*(?=\d)", re.IGNORECASE), "Article "),
)
_WS = re.compile(r"\s+")


def normalize_query(query: str) -> str:
    text = normalize_unicode(query)
    for pattern, replacement in _REPLACEMENTS:
        text = pattern.sub(replacement, text)
    return _WS.sub(" ", text).strip()
