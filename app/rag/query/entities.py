"""Legal entity extraction: statutory sections, constitutional articles, acts and case citations.

Handles the inconsistent forms seen in Indian legal text, e.g. "Section 420 IPC",
"s. 420 of the Indian Penal Code", "u/s 304A IPC", "IPC 302", "420 IPC", "Sections 299 and 300",
"Article 21", "Arts. 14, 19 and 21", "Maneka Gandhi v. Union of India", "AIR 1978 SC 597".
"""

from __future__ import annotations

import re

from app.domain.acts import ACT_ALIAS_RE, alias_to_code
from app.domain.query import EntityType, LegalEntity

_NUM = r"\d{1,4}[A-Z]{0,3}(?:\(\d{1,3}[A-Za-z]?\))*"
_NUM_LIST = rf"{_NUM}(?:\s*(?:,|and|&|or|to)\s*{_NUM})*"
_ACT = ACT_ALIAS_RE.pattern

SECTION_KEYWORD_RE = re.compile(
    rf"\b(?:sections?|secs?\.?|ss?\.|u/s\.?|under\s+section)\s*({_NUM_LIST})"
    rf"(?:\s*(?:of\s+)?(?:the\s+)?({_ACT}))?",
    re.IGNORECASE,
)
ACT_FIRST_RE = re.compile(rf"({_ACT})\s*(?:,\s*)?(?:sections?|secs?\.?|s\.)?\s*({_NUM})(?![\w])", re.IGNORECASE)
NUMBER_FIRST_RE = re.compile(rf"(?<![\w(])({_NUM})\s+(?:of\s+(?:the\s+)?)?({_ACT})", re.IGNORECASE)
ARTICLE_RE = re.compile(rf"\b(?:articles?|arts?\.)\s*({_NUM_LIST})", re.IGNORECASE)
_SINGLE_NUM_RE = re.compile(_NUM)

_PARTY = r"[A-Z][\w.&'’-]*(?:\s+(?:of|and|&|the|for)?\s*[A-Z][\w.&'’-]*){0,6}"
CASE_NAME_RE = re.compile(rf"({_PARTY})\s+(?:v\.|vs\.?|versus)\s+({_PARTY})")
REPORTER_RE = re.compile(
    r"\b(?:AIR\s+\d{4}\s+(?:SC|[A-Z][a-z]+)\s+\d+|\(\d{4}\)\s+\d+\s+SCC\s+\d+|\d{4}\s+SCC\s+OnLine\s+\w+\s+\d+)\b"
)


def _numbers(group: str) -> list[str]:
    return [m.group(0) for m in _SINGLE_NUM_RE.finditer(group)]


def _base_number(raw: str) -> str:
    return raw.split("(", 1)[0].upper()


def extract_entities(text: str) -> list[LegalEntity]:
    """Return de-duplicated legal entities in order of appearance."""
    found: dict[str, tuple[int, LegalEntity]] = {}

    def add(pos: int, entity: LegalEntity) -> None:
        if entity.key not in found or found[entity.key][0] > pos:
            found[entity.key] = (pos, entity)

    acts = [(m.start(), alias_to_code(m.group(0))) for m in ACT_ALIAS_RE.finditer(text)]
    for pos, code in acts:
        add(pos, LegalEntity(type=EntityType.ACT, value=code, act=code, raw=text[pos : pos + len(code)]))

    section_hits: list[tuple[int, str, str | None, str]] = []
    for m in SECTION_KEYWORD_RE.finditer(text):
        act = alias_to_code(m.group(2)) if m.group(2) else None
        for num in _numbers(m.group(1)):
            section_hits.append((m.start(), num, act, m.group(0)))
    for m in ACT_FIRST_RE.finditer(text):
        section_hits.append((m.start(), m.group(2), alias_to_code(m.group(1)), m.group(0)))
    for m in NUMBER_FIRST_RE.finditer(text):
        section_hits.append((m.start(), m.group(1), alias_to_code(m.group(2)), m.group(0)))

    distinct_acts = {code for _, code in acts if code != "CONSTITUTION"}
    for pos, num, act, raw in section_hits:
        if act is None and len(distinct_acts) == 1:
            act = next(iter(distinct_acts))  # "Sections 299 and 300 ... under the IPC"
        add(pos, LegalEntity(type=EntityType.SECTION, value=_base_number(num), act=act, raw=raw.strip()))

    for m in ARTICLE_RE.finditer(text):
        for num in _numbers(m.group(1)):
            add(m.start(), LegalEntity(type=EntityType.ARTICLE, value=_base_number(num), act="CONSTITUTION",
                                       raw=m.group(0).strip()))

    for m in CASE_NAME_RE.finditer(text):
        name = f"{m.group(1).strip()} v. {m.group(2).strip()}"
        add(m.start(), LegalEntity(type=EntityType.CASE_CITATION, value=name, raw=m.group(0)))
    for m in REPORTER_RE.finditer(text):
        add(m.start(), LegalEntity(type=EntityType.CASE_CITATION, value=m.group(0), raw=m.group(0)))

    # Drop an unqualified section when the same number was also found with an act.
    qualified = {(e.type, e.value) for _, e in found.values() if e.act and e.type == EntityType.SECTION}
    entities = [
        e for _, e in sorted(found.values(), key=lambda item: item[0])
        if not (e.type == EntityType.SECTION and e.act is None and (e.type, e.value) in qualified)
    ]
    return entities


def provision_refs(entities: list[LegalEntity]) -> list[tuple[str, str]]:
    """(act_code, number) pairs for sections/articles with a known act."""
    refs = []
    for e in entities:
        if e.type in (EntityType.SECTION, EntityType.ARTICLE) and e.act:
            ref = (e.act, e.value)
            if ref not in refs:
                refs.append(ref)
    return refs
