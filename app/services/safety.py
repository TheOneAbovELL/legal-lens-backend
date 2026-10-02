"""Legal safety guard. Its decision controls graph routing: a refusal ends the pipeline before
retrieval or any LLM call.

Blocked (redirected) per the Legal Lens system design guardrails:
  outcome prediction, personal legal advice, litigation strategy, guilt determination;
plus facilitation of offences (e.g. forging documents, tampering with evidence) and attempts to
override the assistant's instructions. Informational questions about the same topics
("what is the punishment for forgery?") are allowed.
"""

from __future__ import annotations

import re

from app.domain.query import SafetyDecision, SafetyResult

DISCLAIMER = (
    "This is legal information for educational and research purposes only, not legal advice. "
    "For advice on a specific situation, consult a qualified advocate."
)

REDIRECTS: dict[str, str] = {
    "outcome_prediction": (
        "I cannot predict case outcomes. I can help you find similar cases and explain how courts have "
        "ruled on comparable facts and the legal standards they applied."
    ),
    "personal_advice": (
        "I cannot advise on personal legal decisions. I can explain the relevant law, procedures and "
        "options in general terms; for advice on your situation please consult a qualified advocate."
    ),
    "strategy": (
        "I cannot recommend litigation strategies or arguments. I can show the provisions involved and how "
        "similar arguments have been treated in reported cases."
    ),
    "guilt_determination": (
        "Only a court can determine guilt or liability. I can explain the ingredients of the offence and "
        "the legal standards a court applies."
    ),
    "crime_facilitation": (
        "I can't help with that. I can explain what the law says about such conduct, including the "
        "offences and penalties involved."
    ),
    "prompt_injection": (
        "I can only answer legal information questions using the indexed legal sources."
    ),
}

_I = re.IGNORECASE
_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("prompt_injection", re.compile(
        r"\b(?:ignore|disregard|forget)\s+(?:all\s+|any\s+|the\s+|your\s+)?(?:previous|prior|above|earlier|system)\s+"
        r"(?:instructions?|prompts?|rules?)|\breveal\s+(?:your\s+)?(?:system\s+)?prompt\b|\bjailbreak\b|\bDAN\s+mode\b", _I)),
    ("crime_facilitation", re.compile(
        r"\b(?:how\s+(?:to|do\s+i|can\s+i|could\s+i|should\s+i)|help\s+me(?:\s+to)?|steps?\s+to|ways?\s+to|guide\s+(?:me\s+)?to|"
        r"teach\s+me(?:\s+to)?|best\s+way\s+to)\b.{0,60}?\b(?:forge|forging|fabricat\w*|tamper\w*|destroy\w*\s+(?:the\s+)?evidence|"
        r"bribe|launder\w*|evade\s+(?:arrest|police|the\s+police|tax(?:es)?)|escape\s+(?:from\s+)?(?:police|custody|jail|prison)|"
        r"threaten\w*|intimidat\w*|blackmail\w*|extort\w*|hide\s+(?:the\s+)?(?:body|evidence|money|assets)|"
        r"(?:avoid|without)\s+(?:getting\s+)?caught|fake\s+(?:a\s+|an\s+)?(?:document|certificate|id|fir|signature|will|deed)|"
        r"(?:file|lodge)\s+(?:a\s+)?false\s+(?:fir|complaint|case))", _I)),
    ("outcome_prediction", re.compile(
        r"\bwill\s+(?:i|we|my\s+\w+|the\s+(?:accused|petitioner|appellant|plaintiff|defendant))\s+(?:win|lose|be\s+(?:convicted|acquitted|"
        r"released)|get\s+(?:bail|acquitted|convicted|custody|divorce))\b|\b(?:chances?|odds|likelihood|probability)\s+of\s+"
        r"(?:winning|losing|success|acquittal|conviction|getting\s+bail)|\bpredict\s+(?:the\s+)?(?:outcome|result|verdict|judg(?:e)?ment)|"
        r"\bwhat\s+will\s+the\s+(?:court|judge|bench)\s+(?:decide|rule|hold|say)", _I)),
    ("guilt_determination", re.compile(
        r"\b(?:is|was|are)\s+(?:he|she|they|this\s+(?:person|man|woman|guy)|my\s+\w+|the\s+accused\s+in\s+my\s+case)\s+"
        r"(?:\w+\s+){0,3}?guilty\b|"
        r"\bdid\s+(?:he|she|they|my\s+\w+)\s+commit\s+(?:a|an|the)?\s*(?:crime|offen[cs]e)", _I)),
    ("strategy", re.compile(
        r"\bwhat\s+(?:strategy|argument|arguments|defen[cs]e|line\s+of\s+defen[cs]e)\s+should\b|\bhow\s+(?:can|do)\s+(?:i|we)\s+win\b|"
        r"\bbest\s+(?:legal\s+)?(?:strategy|argument|defen[cs]e)\s+(?:to|for)\b|"
        r"\bhow\s+to\s+(?:get|secure|ensure)\s+(?:an?\s+)?acquittal", _I)),
    ("personal_advice", re.compile(
        r"\bshould\s+i\s+(?:file|sue|divorce|plead|settle|appeal|sign|accept|go\s+to\s+court|hire|withdraw|confess|surrender)\b|"
        r"\bwhat\s+should\s+i\s+do\b|\badvise\s+me\s+(?:on|whether|to|if)\b|\bis\s+it\s+advisable\s+for\s+me\b", _I)),
]

_PERSONAL = re.compile(r"\b(?:my|me|i\s+am|i'm|i\s+was|i\s+have|mine)\b", _I)
_FOREIGN = re.compile(
    r"\b(?:united\s+states|u\.?s\.?a?\b|american|uk\b|united\s+kingdom|england|british|canada|canadian|australia|"
    r"australian|singapore|pakistan|bangladesh|eu\s+law|european)", _I)


class SafetyGuard:
    def check(self, query: str) -> SafetyResult:
        for category, pattern in _RULES:
            if pattern.search(query):
                return SafetyResult(
                    decision=SafetyDecision.REFUSE,
                    categories=[category],
                    reasons=[f"request matches the '{category}' guardrail"],
                )
        categories: list[str] = []
        reasons: list[str] = []
        note = None
        if _FOREIGN.search(query):
            categories.append("foreign_jurisdiction")
            note = ("Legal Lens covers Indian law. Information about other jurisdictions is outside the indexed "
                    "sources and is not provided.")
            reasons.append("query references a non-Indian jurisdiction")
        if _PERSONAL.search(query):
            categories.append("personal_situation")
            reasons.append("query describes a personal situation; general information only")
        decision = SafetyDecision.ALLOW_WITH_CAUTION if categories else SafetyDecision.ALLOW
        return SafetyResult(decision=decision, categories=categories, reasons=reasons, jurisdiction_note=note)

    @staticmethod
    def redirect_message(result: SafetyResult) -> str:
        category = result.categories[0] if result.categories else "personal_advice"
        return REDIRECTS.get(category, REDIRECTS["personal_advice"])
