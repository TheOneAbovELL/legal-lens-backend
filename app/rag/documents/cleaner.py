"""Text cleaning that preserves legal layout (line starts matter for structure detection)."""

from __future__ import annotations

import re

from app.core.text import normalize_unicode

_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")
_TRAILING_WS = re.compile(r"[ \t]+\n")
_MULTI_SPACE = re.compile(r"[ \t]{2,}")
_MANY_BLANKS = re.compile(r"\n{3,}")
# Consumes the line break too, so a dropped page number never creates a false paragraph break.
_PAGE_NUMBER_LINE = re.compile(r"^[ \t]*(?:page[ \t]+)?\d{1,4}[ \t]*(?:\n|$)", re.IGNORECASE | re.MULTILINE)
_DASHES = str.maketrans({"–": "—", "‒": "—", "―": "—"})


def clean_text(text: str) -> str:
    """Normalise unicode/whitespace, re-join hyphenated line breaks, drop bare page numbers.

    Line structure is kept: section headings and clause markers are detected at line starts.
    Pages are cleaned individually by the ingestion pipeline so page offsets stay exact.
    """
    text = normalize_unicode(text).translate(_DASHES)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x0c", "\n\n")
    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    text = _PAGE_NUMBER_LINE.sub("", text)
    text = _TRAILING_WS.sub("\n", text)
    text = _MULTI_SPACE.sub(" ", text)
    text = _MANY_BLANKS.sub("\n\n", text)
    return text.strip() + "\n"
