"""Legal document structure extraction.

Detects top-level units (Part/Chapter context, Sections, Articles, Schedules, numbered judgment
paragraphs) and, inside each unit, the blocks legal readers treat as indivisible: sub-sections,
clauses, Explanations, Provisos, Illustrations, Exceptions and definitions. Chunkers use these
offsets so that, e.g., "Section 420" is never separated from its continuation by a blind cut.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.acts import canonical_act
from app.domain.documents import (
    BlockType,
    DocumentType,
    LegalBlock,
    LegalUnit,
    SourceDocument,
    StructuredDocument,
    UnitKind,
)

_NUM = r"\d{1,4}[A-Z]{0,3}"
PART_RE = re.compile(r"^PART\s+([IVXLC]+[A-Z]?)\b\.?\s*(.*)$")
CHAPTER_RE = re.compile(r"^CHAPTER\s+([IVXLC]+[A-Z]?|\d+[A-Z]?)\b\.?\s*(.*)$", re.IGNORECASE)
SECTION_RE = re.compile(rf"^(?:Section|Sec\.|S\.)\s*({_NUM})\b\s*[.:\-—]*\s*(.*)$", re.IGNORECASE)
ARTICLE_RE = re.compile(rf"^Article\s+({_NUM})\b\s*[.:\-—]*\s*(.*)$", re.IGNORECASE)
# Bare-act style: "420. Cheating and dishonestly inducing delivery of property.—Whoever ..."
BARE_SECTION_RE = re.compile(rf"^({_NUM})\.\s+([A-Z][^—\n]{{2,200}}?)\s*\.?\s*—\s*(.*)$")
SCHEDULE_RE = re.compile(
    r"^(?:THE\s+)?((?:FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH|SEVENTH|EIGHTH|NINTH|TENTH|ELEVENTH|TWELFTH)\s+)?SCHEDULE\b\s*(.*)$",
    re.IGNORECASE,
)
JUDGMENT_PARA_RE = re.compile(r"^(\d{1,4})\.\s+(\S.*)$")

SUBSECTION_RE = re.compile(r"^\((\d{1,3}[A-Z]?)\)\s")
CLAUSE_RE = re.compile(r"^\(([a-z]{1,2}|[ivxlc]{1,6})\)\s")
EXPLANATION_RE = re.compile(r"^Explanation(?:\s*[-—]?\s*(\d+|[IVX]+))?\s*[.:\-—]", re.IGNORECASE)
ILLUSTRATION_RE = re.compile(r"^Illustrations?\b", re.IGNORECASE)
EXCEPTION_RE = re.compile(r"^Exception(?:\s*[-—]?\s*(\d+|[IVX]+))?\s*[.:\-—]", re.IGNORECASE)
PROVISO_RE = re.compile(r"^Provided\s+(?:that|further|also)\b", re.IGNORECASE)
DEFINITION_RE = re.compile(r'^["“][^"”]{1,80}["”]\s+(?:means|includes|shall mean)\b', re.IGNORECASE)

CASE_LAW_HINT_RE = re.compile(
    r"\b(?:JUDGMENT|J\s*U\s*D\s*G\s*M\s*E\s*N\s*T|Appellants?|Respondents?|Petitioners?)\b|\sv(?:s)?\.\s", re.IGNORECASE
)


@dataclass
class _Line:
    text: str  # stripped
    start: int  # absolute offset of stripped text
    end: int


def _lines(text: str) -> list[_Line]:
    lines: list[_Line] = []
    offset = 0
    for raw in text.split("\n"):
        stripped = raw.strip()
        if stripped:
            lead = len(raw) - len(raw.lstrip())
            lines.append(_Line(stripped, offset + lead, offset + lead + len(stripped)))
        offset += len(raw) + 1
    return lines


def infer_document_type(text: str, title: str) -> DocumentType:
    head = text[:3000]
    if re.search(r"\bconstitution\b", title, re.IGNORECASE) and ARTICLE_RE.search(head):
        return DocumentType.CONSTITUTION
    if CASE_LAW_HINT_RE.search(head[:1500]):
        return DocumentType.CASE_LAW
    if re.search(r"\b(?:Act|Sanhita|Adhiniyam|Code),?\s*(?:of\s*)?\d{4}\b", head) or any(
        SECTION_RE.match(line.text) or BARE_SECTION_RE.match(line.text) for line in _lines(head)
    ):
        return DocumentType.STATUTE
    return DocumentType.OTHER


def infer_act(text: str, title: str) -> str | None:
    return canonical_act(title) or canonical_act(text[:500])


_MAX_HEADER_LINE = 160  # outside statutes, long "Section N ..." lines are prose, not headers


def _match_unit(line: str, doc_type: DocumentType) -> tuple[UnitKind, str | None, str | None] | None:
    if doc_type == DocumentType.CASE_LAW:
        m = JUDGMENT_PARA_RE.match(line)
        return (UnitKind.PARAGRAPH, m.group(1), None) if m else None
    if doc_type not in (DocumentType.STATUTE, DocumentType.CONSTITUTION) and len(line) > _MAX_HEADER_LINE:
        return None
    if m := ARTICLE_RE.match(line):
        return UnitKind.ARTICLE, m.group(1).upper(), _heading(m.group(2))
    if m := SECTION_RE.match(line):
        return UnitKind.SECTION, m.group(1).upper(), _heading(m.group(2))
    if m := BARE_SECTION_RE.match(line):
        return UnitKind.SECTION, m.group(1).upper(), m.group(2).strip().rstrip(".")
    if m := SCHEDULE_RE.match(line):
        if line.isupper() or line.lower().startswith(("the ", "schedule")):
            return UnitKind.SCHEDULE, (m.group(1) or "").strip().title() or None, m.group(2).strip() or None
    return None


def _heading(rest: str) -> str | None:
    """Heading = text up to the first '.—', '—' or sentence end, if reasonably short."""
    rest = rest.strip()
    if not rest:
        return None
    cut = re.split(r"\.?—|(?<=[a-z\)])\.\s", rest, maxsplit=1)[0].strip().rstrip(".")
    return cut[:200] if cut else None


def _match_block(line: str, in_illustration: bool) -> tuple[BlockType, str | None] | None:
    if m := EXPLANATION_RE.match(line):
        return BlockType.EXPLANATION, f"Explanation {m.group(1)}" if m.group(1) else "Explanation"
    if m := EXCEPTION_RE.match(line):
        return BlockType.EXCEPTION, f"Exception {m.group(1)}" if m.group(1) else "Exception"
    if ILLUSTRATION_RE.match(line):
        return BlockType.ILLUSTRATION, "Illustration"
    if PROVISO_RE.match(line):
        return BlockType.PROVISO, "Proviso"
    if m := SUBSECTION_RE.match(line):
        return BlockType.SUBSECTION, f"({m.group(1)})"
    if DEFINITION_RE.match(line):
        return BlockType.DEFINITION, None
    if not in_illustration and (m := CLAUSE_RE.match(line)):
        return BlockType.CLAUSE, f"({m.group(1)})"
    return None


def _build_blocks(lines: list[_Line], unit_kind: UnitKind) -> list[LegalBlock]:
    blocks: list[LegalBlock] = []
    current: LegalBlock | None = None
    in_illustration = False
    prev_end = -1
    text_gap_split = unit_kind in (UnitKind.BODY, UnitKind.PARAGRAPH)
    for i, line in enumerate(lines):
        match = None if i == 0 else _match_block(line.text, in_illustration)
        # In unstructured text, a blank line (gap > 1 char) starts a new paragraph block.
        paragraph_break = text_gap_split and current is not None and line.start - prev_end > 1
        if match or current is None or paragraph_break:
            block_type, label = match if match else (BlockType.TEXT, None)
            if match:
                in_illustration = block_type == BlockType.ILLUSTRATION or (
                    in_illustration and block_type == BlockType.CLAUSE
                )
            current = LegalBlock(block_type=block_type, label=label, start=line.start, end=line.end)
            blocks.append(current)
        else:
            current.end = line.end
        prev_end = line.end
    return blocks


def extract_structure(document: SourceDocument) -> StructuredDocument:
    lines = _lines(document.text)
    units: list[LegalUnit] = []
    pending: list[_Line] = []
    unit_meta: tuple[UnitKind, str | None, str | None] | None = None
    part: str | None = None
    chapter: str | None = None
    seen_ids: dict[str, int] = {}

    def flush() -> None:
        if not pending:
            return
        kind, number, heading = unit_meta or (UnitKind.BODY, None, None)
        base_id = f"{kind.value}-{number}" if number else f"{kind.value}-{len(units)}"
        count = seen_ids.get(base_id, 0)
        seen_ids[base_id] = count + 1
        units.append(
            LegalUnit(
                unit_id=base_id if count == 0 else f"{base_id}~{count}",
                kind=kind,
                number=number,
                heading=heading,
                part=part,
                chapter=chapter,
                start=pending[0].start,
                end=pending[-1].end,
                blocks=_build_blocks(pending, kind),
            )
        )

    for line in lines:
        if document.document_type != DocumentType.CASE_LAW and len(line.text) <= 120:
            if m := PART_RE.match(line.text):
                flush()
                pending, unit_meta = [], None
                part = f"Part {m.group(1)}" + (f" — {m.group(2).strip()}" if m.group(2).strip() else "")
                continue
            if m := CHAPTER_RE.match(line.text):
                flush()
                pending, unit_meta = [], None
                chapter = f"Chapter {m.group(1)}" + (f" — {m.group(2).strip()}" if m.group(2).strip() else "")
                continue
        matched = _match_unit(line.text, document.document_type)
        if matched:
            flush()
            pending, unit_meta = [line], matched
        else:
            pending.append(line)
    flush()

    if not units:
        units = [LegalUnit(unit_id="body-0", kind=UnitKind.BODY, start=0, end=0, blocks=[])]
    return StructuredDocument(document=document, units=units)
