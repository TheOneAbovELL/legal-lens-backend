"""Query complexity classification (SIMPLE / MODERATE / COMPLEX).

A transparent, weighted feature model rather than a keyword switch. Features combine structure
(number of questions, clauses, length), extracted legal entities (distinct provisions, acts,
case citations) and reasoning cues (comparison, causal/analytical, temporal/version,
cross-reference, conflicting authority). Weights and thresholds are configurable via JSON
(``COMPLEXITY_CONFIG_PATH``) and the evaluation script reports classifier accuracy against the
labelled dataset so they can be calibrated with data rather than intuition.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

from pydantic import BaseModel, Field

from app.core.exceptions import ConfigurationError
from app.core.text import count_tokens
from app.domain.query import (
    Complexity,
    ComplexityResult,
    EntityType,
    EvidenceLevel,
    Intent,
    IntentResult,
    LegalEntity,
)

_COMPARISON = re.compile(
    r"\b(?:compare|comparison|compared|differen(?:ce|t|tiate)|distinguish|contrast|versus|vs\.?|"
    r"similarit\w*|as\s+opposed\s+to|between\s+.+\s+and)\b",
    re.IGNORECASE,
)
_REASONING = re.compile(
    r"\b(?:why|how\s+(?:does|do|did|would|can|could)|analy[sz]e|analysis|evaluate|assess|implications?|"
    r"consequences?|impact|affect\w*|interplay|reconcile|justify|rationale|critically|examine)\b",
    re.IGNORECASE,
)
_TEMPORAL = re.compile(
    r"\b(?:before|after|amend\w*|replac\w*|repeal\w*|transition\w*|old\s+law|new\s+law|came\s+into\s+force|"
    r"retrospective\w*|prospective\w*|19\d{2}|20\d{2}|with\s+effect\s+from|w\.e\.f)\b",
    re.IGNORECASE,
)
_CROSS_REF = re.compile(r"\b(?:read\s+with|in\s+conjunction\s+with|together\s+with|along\s+with)\b", re.IGNORECASE)
_CONFLICT = re.compile(
    r"\b(?:conflict\w*|divergent|overrul\w*|contradict\w*|inconsisten\w*|split\s+of\s+opinion|larger\s+bench)\b",
    re.IGNORECASE,
)
_EVIDENCE_DEMAND = re.compile(r"\b(?:cite|citations?|authorit(?:y|ies)|with\s+cases|case\s+law|precedents?)\b", re.IGNORECASE)
_MULTI_PART = re.compile(r"\b(?:and\s+(?:also|then)|also\s+explain|additionally|as\s+well\s+as|furthermore)\b", re.IGNORECASE)
_INTERROGATIVE_CLAUSE = re.compile(
    r"(?:^|[,;]\s*|\band\s+)(?:what|which|when|where|who|whom|whose|why|how|is|are|can|does|do|should)\b",
    re.IGNORECASE,
)


class ComplexityConfig(BaseModel):
    weights: dict[str, float] = Field(
        default_factory=lambda: {
            "extra_provisions": 0.9,  # per distinct provision beyond the first (capped)
            "multiple_acts": 1.2,
            "case_citations": 0.6,
            "questions": 1.0,  # per question beyond the first (capped)
            "comparison": 1.6,
            "reasoning": 1.1,
            "temporal": 0.9,
            "cross_reference": 1.0,
            "conflict": 1.5,
            "evidence_demand": 0.6,
            "multi_part": 0.8,
            "length": 0.8,  # log-scaled beyond 20 tokens
            "intent_mapping": 0.8,
            "intent_document": 1.5,
            "intent_case_law": 0.5,
        }
    )
    moderate_threshold: float = 1.0
    complex_threshold: float = 2.6
    max_provision_bonus: int = 4
    max_question_bonus: int = 3

    @classmethod
    def load(cls, path: Path | None) -> ComplexityConfig:
        if path is None:
            return cls()
        try:
            return cls.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            raise ConfigurationError(f"invalid complexity config {path}: {exc}") from exc


class QueryComplexityClassifier:
    def __init__(self, config: ComplexityConfig | None = None) -> None:
        self.config = config or ComplexityConfig()

    def features(self, query: str, entities: list[LegalEntity], intent: IntentResult | None) -> dict[str, float]:
        provisions = {e.key for e in entities if e.type in (EntityType.SECTION, EntityType.ARTICLE)}
        acts = {e.act for e in entities if e.act and e.type in (EntityType.SECTION, EntityType.ARTICLE, EntityType.ACT)}
        questions = max(query.count("?"), len(_INTERROGATIVE_CLAUSE.findall(query)) or 1)
        tokens = count_tokens(query)
        cfg = self.config
        return {
            "extra_provisions": float(min(max(len(provisions) - 1, 0), cfg.max_provision_bonus)),
            "multiple_acts": 1.0 if len(acts) > 1 else 0.0,
            "case_citations": float(min(sum(e.type == EntityType.CASE_CITATION for e in entities), 3)),
            "questions": float(min(questions - 1, cfg.max_question_bonus)),
            "comparison": 1.0 if _COMPARISON.search(query) else 0.0,
            "reasoning": 1.0 if _REASONING.search(query) else 0.0,
            "temporal": 1.0 if _TEMPORAL.search(query) else 0.0,
            "cross_reference": 1.0 if _CROSS_REF.search(query) else 0.0,
            "conflict": 1.0 if _CONFLICT.search(query) else 0.0,
            "evidence_demand": 1.0 if _EVIDENCE_DEMAND.search(query) else 0.0,
            "multi_part": 1.0 if _MULTI_PART.search(query) else 0.0,
            "length": round(max(0.0, math.log2(tokens / 20)) if tokens > 20 else 0.0, 3),
            "intent_mapping": 1.0 if intent and intent.intent == Intent.PROVISION_MAPPING else 0.0,
            "intent_document": 1.0 if intent and intent.intent == Intent.DOCUMENT_ANALYSIS else 0.0,
            "intent_case_law": 1.0 if intent and intent.intent == Intent.CASE_LAW else 0.0,
        }

    def classify(
        self, query: str, entities: list[LegalEntity], intent: IntentResult | None = None
    ) -> ComplexityResult:
        cfg = self.config
        feats = self.features(query, entities, intent)
        contributions = {name: feats[name] * cfg.weights.get(name, 0.0) for name in feats}
        score = round(sum(contributions.values()), 3)

        if score >= cfg.complex_threshold:
            complexity = Complexity.COMPLEX
        elif score >= cfg.moderate_threshold:
            complexity = Complexity.MODERATE
        else:
            complexity = Complexity.SIMPLE
        # Confidence grows with distance from the nearest decision threshold.
        margin = min(abs(score - cfg.moderate_threshold), abs(score - cfg.complex_threshold))
        confidence = round(0.5 + 0.5 * math.tanh(margin), 3)

        reasons = [
            f"{name.replace('_', ' ')} (+{value:.2f})"
            for name, value in sorted(contributions.items(), key=lambda kv: -kv[1])
            if value > 0
        ] or ["single, direct question"]

        multi_hop = bool(feats["cross_reference"] or feats["temporal"] or feats["intent_mapping"]
                         or feats["multiple_acts"])
        distinct_docs = feats["multiple_acts"] or feats["case_citations"] > 1
        evidence = (
            EvidenceLevel.CROSS_DOCUMENT if distinct_docs or multi_hop
            else EvidenceLevel.MULTI_SOURCE if complexity != Complexity.SIMPLE
            else EvidenceLevel.SINGLE_SOURCE
        )
        return ComplexityResult(
            complexity=complexity,
            confidence=confidence,
            score=score,
            reasons=reasons,
            features=feats,
            detected_entities=entities,
            requires_decomposition=complexity == Complexity.COMPLEX,
            requires_reranking=complexity != Complexity.SIMPLE,
            requires_multi_hop=multi_hop,
            evidence_level=evidence,
        )
