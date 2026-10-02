"""Rule-based intent detection over normalised text + extracted entities (no LLM; <1 ms)."""

from __future__ import annotations

import re

from app.domain.query import EntityType, Intent, IntentResult, LegalEntity

_SMALL_TALK = re.compile(
    r"^\s*(?:hi|hello|hey|namaste|good\s+(?:morning|afternoon|evening)|thanks?(?:\s+you)?|thank\s+you|"
    r"ok(?:ay)?|bye|who\s+are\s+you|what\s+can\s+you\s+do)\b[\s!.?]*$",
    re.IGNORECASE,
)
_MAPPING = re.compile(
    r"\b(?:correspond\w*|equivalent|replac\w*|mapp?(?:ed|ing)?|new\s+law|old\s+law|now\s+under|"
    r"counterpart|renumber\w*|bns\s+section\s+for|which\s+section\s+of\s+(?:the\s+)?bns)\b",
    re.IGNORECASE,
)
_CASE_LAW = re.compile(
    r"\b(?:case\s*law|precedents?|judg(?:e)?ments?|held|ruling|ratio|supreme\s+court|high\s+court|"
    r"landmark|bench|overrul\w*|cited|verdict)\b",
    re.IGNORECASE,
)
_PROCEDURAL = re.compile(
    r"\b(?:how\s+(?:to|do\s+i|can\s+i)\s+(?:file|apply|register|lodge|get)|procedure|process\s+for|"
    r"bail|fir|complaint|appeal|limitation\s+period|summons|warrant|chargesheet|charge\s*sheet)\b",
    re.IGNORECASE,
)
_DOCUMENT = re.compile(
    r"\b(?:this\s+(?:document|agreement|contract|clause|notice|fir)|the\s+following\s+(?:clause|text|"
    r"document)|attached|below\s+text|analy[sz]e\s+(?:this|the\s+following))\b",
    re.IGNORECASE,
)
_LOOKUP = re.compile(r"\b(?:what\s+is|what\s+does|define|definition|meaning|explain|text\s+of|says?)\b", re.IGNORECASE)
_LEGAL_VOCAB = re.compile(
    r"\b(?:law|legal|act|section|article|court|offen[cs]e|punish\w*|crime|criminal|civil|right|rights|"
    r"constitution|statute|penal|accused|bail|contract|liabilit\w*|sentence|imprisonment|fine|"
    r"evidence|petition|writ|tort|negligence|cheating|murder|theft|property|marriage|divorce)\b",
    re.IGNORECASE,
)


class IntentDetector:
    def detect(self, query: str, entities: list[LegalEntity]) -> IntentResult:
        signals: list[str] = []
        if _SMALL_TALK.match(query) and not entities:
            return IntentResult(intent=Intent.SMALL_TALK, confidence=0.95, signals=["greeting/pleasantry"])

        scores: dict[Intent, float] = {intent: 0.0 for intent in Intent}
        acts = {e.act for e in entities if e.type == EntityType.SECTION and e.act}
        has_provision = any(e.type in (EntityType.SECTION, EntityType.ARTICLE) for e in entities)

        if _MAPPING.search(query):
            scores[Intent.PROVISION_MAPPING] += 2.0
            signals.append("mapping vocabulary")
        if {"IPC", "BNS"} <= acts or {"CRPC", "BNSS"} <= acts or {"IEA", "BSA"} <= acts:
            scores[Intent.PROVISION_MAPPING] += 1.5
            signals.append("old and new code both referenced")
        if any(e.type == EntityType.CASE_CITATION for e in entities):
            scores[Intent.CASE_LAW] += 2.0
            signals.append("case citation present")
        if _CASE_LAW.search(query):
            scores[Intent.CASE_LAW] += 1.2
            signals.append("case-law vocabulary")
        if _PROCEDURAL.search(query):
            scores[Intent.PROCEDURAL] += 1.3
            signals.append("procedural vocabulary")
        if _DOCUMENT.search(query) or len(query) > 1200:
            scores[Intent.DOCUMENT_ANALYSIS] += 2.0
            signals.append("document analysis request")
        if has_provision:
            scores[Intent.STATUTE_LOOKUP] += 1.0 + (0.8 if _LOOKUP.search(query) else 0.0)
            signals.append("provision referenced")
        if _LEGAL_VOCAB.search(query):
            scores[Intent.GENERAL_LEGAL] += 0.6

        best = max(scores, key=lambda intent: scores[intent])
        total = sum(scores.values())
        if scores[best] == 0.0:
            # No legal signal at all: still treated as a legal question (retrieval decides
            # whether the corpus can answer); low confidence is reported.
            return IntentResult(intent=Intent.GENERAL_LEGAL, confidence=0.3, signals=["no legal signals"])
        return IntentResult(intent=best, confidence=round(scores[best] / total, 3), signals=signals)
