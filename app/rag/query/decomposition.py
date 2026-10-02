"""Controlled query decomposition for COMPLEX queries.

Decomposition only plans *retrieval tasks*; it never states legal facts. Safeguards:
* single level only (sub-queries are never decomposed again), so no recursion/loops;
* hard cap on sub-queries, minimum sub-query quality, near-duplicate removal;
* the LLM path runs under a timeout and token budget, validates its JSON and falls back to the
  deterministic rule-based decomposer on any failure;
* the original query is always kept as the highest-priority sub-query, so coverage of the
  user's actual question never depends on the decomposition being good.
"""

from __future__ import annotations

import asyncio
import json
import re

from pydantic import BaseModel, Field, ValidationError

from app.core.exceptions import LLMProviderError
from app.core.logging import get_logger
from app.core.text import count_tokens, jaccard, words
from app.domain.acts import ACT_NAMES, act_display_name
from app.domain.query import DecompositionResult, EntityType, LegalEntity, SubQuery
from app.providers.llm.base import ChatMessage, LLMRequest
from app.providers.llm.router import LLMRouter
from app.rag.query.entities import extract_entities
from app.rag.query.expansion import counterpart_subqueries
from app.services.legal_mapping import LegalProvisionMapper

logger = get_logger(__name__)

_TASK_VERBS = (r"what|how|why|which|whether|when|who|explain|describe|compare|identify|analy[sz]e|cite|discuss|list|"
               r"state|outline|evaluate|assess|examine|summari[sz]e|distinguish|contrast|find")
# Splits multi-part questions: "?", ";", sentence ends, and ", (and) <task verb>" / " and <task verb>".
_CLAUSE_SPLIT = re.compile(
    rf"\?\s*|;\s*|\.\s+(?=[A-Z])|,\s*(?:and\s+)?(?=(?:also\s+)?(?:{_TASK_VERBS})\b)"
    rf"|\s+and\s+(?=(?:also\s+)?(?:{_TASK_VERBS})\b)",
    re.IGNORECASE,
)
MIN_SUBQUERY_TOKENS = 3
DUPLICATE_JACCARD = 0.8

_SYSTEM_PROMPT = """You plan document retrieval for an Indian legal research assistant.
Abbreviations (authoritative, do not reinterpret): {glossary}.
Split the user's question into at most {max_n} focused search sub-queries that together retrieve
all evidence needed to answer it. Do NOT answer the question and do NOT state any legal facts,
section numbers or case names that are not in the user's question.
Return only JSON of the form:
{{"subqueries": [{{"query": "...", "purpose": "...", "required_evidence": "...",
  "legal_entities": ["..."], "priority": 1, "depends_on": []}}]}}
priority: 1 (essential) to 3 (supporting). depends_on: indices (0-based) of earlier sub-queries."""


class _LLMSubQuery(BaseModel):
    query: str = Field(min_length=3, max_length=400)
    purpose: str = Field(default="", max_length=300)
    required_evidence: str = Field(default="", max_length=300)
    legal_entities: list[str] = Field(default_factory=list)
    priority: int = Field(default=1, ge=1, le=3)
    depends_on: list[int] = Field(default_factory=list)


class _LLMPlan(BaseModel):
    subqueries: list[_LLMSubQuery]


def _dedupe(subqueries: list[SubQuery], limit: int) -> list[SubQuery]:
    kept: list[SubQuery] = []
    seen: list[set[str]] = []
    for sq in sorted(subqueries, key=lambda s: s.priority):
        terms = set(words(sq.query))
        if count_tokens(sq.query) < MIN_SUBQUERY_TOKENS or not terms:
            continue
        if any(jaccard(terms, other) >= DUPLICATE_JACCARD for other in seen):
            continue
        kept.append(sq)
        seen.append(terms)
        if len(kept) >= limit:
            break
    # Stable, readable IDs after filtering; remap dependencies accordingly.
    id_map = {sq.subquery_id: f"q{i}" for i, sq in enumerate(kept)}
    return [
        sq.model_copy(update={
            "subquery_id": id_map[sq.subquery_id],
            "depends_on": [id_map[d] for d in sq.depends_on if d in id_map],
        })
        for sq in kept
    ]


class RuleBasedDecomposer:
    def __init__(self, mapper: LegalProvisionMapper | None, max_subqueries: int) -> None:
        self._mapper = mapper
        self._max = max_subqueries

    def decompose(self, query: str, entities: list[LegalEntity]) -> list[SubQuery]:
        subqueries = [SubQuery(subquery_id="orig", query=query, purpose="original question", priority=0)]
        # Fragments like "identify the corresponding provisions" are anchored to the query's provisions,
        # or to its acts when no provision is named.
        provision_labels = [e.raw for e in entities if e.type in (EntityType.SECTION, EntityType.ARTICLE)] or [
            act_display_name(e.value) or e.value for e in entities if e.type == EntityType.ACT]
        for i, clause in enumerate(p.strip() for p in _CLAUSE_SPLIT.split(query) if p and p.strip()):
            if clause.lower() == query.lower().rstrip("?").strip():
                continue
            clause_entities = extract_entities(clause)
            if provision_labels and not clause_entities:
                # "what punishment does it prescribe" -> anchor the fragment to the query's provisions
                clause = f"{clause} ({', '.join(provision_labels[:3])})"
            subqueries.append(SubQuery(subquery_id=f"part{i}", query=clause, purpose="question part", priority=2))
        for e in entities:
            if e.type in (EntityType.SECTION, EntityType.ARTICLE):
                label = "Article" if e.type == EntityType.ARTICLE else "Section"
                act = act_display_name(e.act) if e.act else ""
                subqueries.append(SubQuery(
                    subquery_id=f"prov-{e.act}-{e.value}",
                    query=f"{act} {label} {e.value}".strip(),
                    purpose=f"retrieve the text of {e.act or ''} {label} {e.value}".replace("  ", " "),
                    required_evidence="statutory text",
                    legal_entities=[e.raw],
                    priority=1,
                ))
            elif e.type == EntityType.CASE_CITATION:
                subqueries.append(SubQuery(
                    subquery_id=f"case-{len(subqueries)}", query=e.value, purpose="retrieve the cited judgment",
                    required_evidence="judgment text", legal_entities=[e.value], priority=1,
                ))
        for sq in counterpart_subqueries(entities, self._mapper, 0, limit=self._max):
            subqueries.append(sq.model_copy(update={"subquery_id": f"map-{sq.subquery_id}", "priority": 1}))
        return _dedupe(subqueries, self._max)


class QueryDecomposer:
    def __init__(
        self,
        *,
        rule_based: RuleBasedDecomposer,
        llm: LLMRouter | None,
        use_llm: bool,
        max_subqueries: int,
        timeout: float,
        max_tokens: int,
    ) -> None:
        self._rules = rule_based
        self._llm = llm
        self._use_llm = use_llm and llm is not None
        self._max = max_subqueries
        self._timeout = timeout
        self._max_tokens = max_tokens

    async def decompose(self, query: str, entities: list[LegalEntity], *, allow_llm: bool = True) -> DecompositionResult:
        if not (self._use_llm and allow_llm and self._llm is not None and self._llm.configured):
            return DecompositionResult(subqueries=self._rules.decompose(query, entities), method="rule")
        try:
            subqueries = await asyncio.wait_for(self._llm_decompose(query), timeout=self._timeout)
        except (LLMProviderError, TimeoutError, ValidationError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("llm decomposition failed; using rule-based", extra={"error_type": type(exc).__name__})
            return DecompositionResult(
                subqueries=self._rules.decompose(query, entities),
                method="rule_fallback",
                warnings=[f"LLM decomposition unavailable ({type(exc).__name__}); rule-based plan used."],
            )
        # Provision look-ups from the rule-based planner are cheap and deterministic: merge them in.
        rule_extras = [sq for sq in self._rules.decompose(query, entities) if sq.priority > 0]
        merged = _dedupe(subqueries[:1] + rule_extras + subqueries[1:], self._max)
        return DecompositionResult(subqueries=merged, method="llm")

    async def _llm_decompose(self, query: str) -> list[SubQuery]:
        assert self._llm is not None
        response = await self._llm.complete(LLMRequest(
            messages=[
                ChatMessage(role="system", content=_SYSTEM_PROMPT.format(
                    max_n=self._max - 1, glossary="; ".join(f"{k} = {v}" for k, v in ACT_NAMES.items()))),
                ChatMessage(role="user", content=query),
            ],
            temperature=0.0,
            max_tokens=self._max_tokens,
            json_mode=True,
            timeout=self._timeout,
        ))
        plan = _LLMPlan.model_validate(json.loads(response.text))
        subqueries = [SubQuery(subquery_id="orig", query=query, purpose="original question", priority=0)]
        for i, item in enumerate(plan.subqueries[: self._max]):
            subqueries.append(SubQuery(
                subquery_id=f"llm{i}",
                query=item.query.strip(),
                purpose=item.purpose or "retrieval task",
                required_evidence=item.required_evidence,
                legal_entities=item.legal_entities[:5],
                # LLM plans rank after entity-grounded look-ups (priority 1) when the cap applies.
                priority=min(item.priority + 1, 5),
                depends_on=[f"llm{d}" for d in item.depends_on if 0 <= d < i],
            ))
        return subqueries
