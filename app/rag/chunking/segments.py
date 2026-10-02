"""Span utilities shared by chunking strategies: legal-aware sentence splitting and packing."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.core.text import count_tokens

# Abbreviations common in Indian legal writing that end with a period but do not end a sentence.
LEGAL_ABBREVIATIONS = frozenset(
    """sec secs s ss no nos art arts cl cls v vs i.e e.g viz etc ltd co pvt mr mrs ms dr hon'ble
    ors anr p pp para paras vol ch sch r rr st jt supp cri crl sc scc air ibid cf approx govt dept
    u/s r/w w.e.f illus expl exc rs smt shri sh m/s""".split()
)

_BOUNDARY_RE = re.compile(r"[.!?][\"'”’)\]]*\s+")
_LIST_LINE_RE = re.compile(r"\n\s*(?=\(?[a-z0-9ivx]{1,4}\)|Explanation|Illustration|Exception|Provided)", re.IGNORECASE)


@dataclass
class Span:
    start: int
    end: int
    tokens: int
    info: dict[str, Any] = field(default_factory=dict)


def make_span(text: str, start: int, end: int, **info: Any) -> Span | None:
    """Trim whitespace; return None for empty spans. Offsets are absolute into ``text``."""
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    if start >= end:
        return None
    return Span(start, end, count_tokens(text[start:end]), dict(info))


def _is_abbreviation(text: str, dot_index: int) -> bool:
    i = dot_index
    while i > 0 and not text[i - 1].isspace() and text[i - 1] not in "(":
        i -= 1
    word = text[i:dot_index].lower().strip("\"'“‘")
    if not word:
        return False
    if word in LEGAL_ABBREVIATIONS:
        return True
    if len(word) == 1 and word.isalpha():  # initials: "K. S. Puttaswamy"
        return True
    return bool(re.fullmatch(r"(?:[a-z]\.)+[a-z]?", word))  # "i.p.c", "a.i.r"


def split_sentences(text: str, start: int, end: int) -> list[Span]:
    """Split ``text[start:end]`` into sentences, respecting legal abbreviations and list lines."""
    cuts: set[int] = set()
    region = text[start:end]
    for m in _BOUNDARY_RE.finditer(region):
        dot = start + m.start()
        nxt = start + m.end()
        if text[dot] == "." and _is_abbreviation(text, dot):
            continue
        if nxt < end and text[nxt].islower():  # "s. 420 of the ..." style continuation
            continue
        cuts.add(nxt)
    for m in _LIST_LINE_RE.finditer(region):
        cuts.add(start + m.start())
    spans: list[Span] = []
    prev = start
    for cut in sorted(cuts) + [end]:
        if cut <= prev:
            continue
        span = make_span(text, prev, cut)
        if span:
            spans.append(span)
        prev = cut
    return spans


def split_by_tokens(text: str, start: int, end: int, max_tokens: int) -> list[Span]:
    """Last-resort split on token boundaries (used only for oversize atomic pieces)."""
    pieces: list[Span] = []
    matches = list(re.finditer(r"\w+|[^\w\s]", text[start:end]))
    for i in range(0, len(matches), max_tokens):
        group = matches[i : i + max_tokens]
        span = make_span(text, start + group[0].start(), start + group[-1].end())
        if span:
            pieces.append(span)
    return pieces


def pack(
    text: str,
    segments: list[Span],
    max_tokens: int,
    overlap_tokens: int = 0,
    min_tokens: int = 0,
) -> list[Span]:
    """Greedily pack consecutive segments into chunks of <= max_tokens.

    * Oversize segments are split on token boundaries (never silently dropped).
    * ``overlap_tokens`` repeats trailing whole segments of the previous chunk.
    * A trailing chunk smaller than ``min_tokens`` is merged into its predecessor.
    """
    atoms: list[Span] = []
    for seg in segments:
        atoms.extend(split_by_tokens(text, seg.start, seg.end, max_tokens) if seg.tokens > max_tokens else [seg])
    chunks: list[list[Span]] = []
    current: list[Span] = []
    current_tokens = 0
    for atom in atoms:
        if current and current_tokens + atom.tokens > max_tokens:
            chunks.append(current)
            carry: list[Span] = []
            carried = 0
            if overlap_tokens > 0:
                for prev in reversed(current):
                    if carried + prev.tokens > overlap_tokens or len(carry) + 1 >= len(current):
                        break
                    carry.insert(0, prev)
                    carried += prev.tokens
            if carried + atom.tokens > max_tokens:
                carry, carried = [], 0
            current, current_tokens = list(carry), carried
        current.append(atom)
        current_tokens += atom.tokens
    if current:
        chunks.append(current)

    spans = [s for group in chunks if (s := make_span(text, group[0].start, group[-1].end))]
    if min_tokens and len(spans) > 1 and spans[-1].tokens < min_tokens:
        tail = spans.pop()
        merged = make_span(text, spans[-1].start, max(spans[-1].end, tail.end))
        if merged:
            spans[-1] = merged
    return spans
