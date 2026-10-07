"""Context fusion: turn reranked candidates into a budgeted, de-duplicated, grouped, citable context.

Never truncates legal text: an item that does not fit the remaining budget is skipped whole.
Coverage first: every sub-query gets its best evidence before global score-order filling.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.text import count_tokens, jaccard, words
from app.domain.query import SubQuery
from app.domain.retrieval import BuiltContext, EvidenceGroup, EvidenceItem, RetrievedChunk

NEAR_DUPLICATE_JACCARD = 0.85


class ContextBudget(BaseModel):
    max_context_tokens: int = Field(default=3000, ge=50)
    max_chunks: int = Field(default=10, ge=1)
    max_chunks_per_document: int = Field(default=6, ge=1)
    max_evidence_per_subquery: int = Field(default=4, ge=1)
    min_relative_relevance: float = Field(default=0.15, ge=0.0, le=1.0)


def _tokens(chunk: RetrievedChunk) -> int:
    return count_tokens(f"{chunk.context_header}\n{chunk.content}")


def _group_key(chunk: RetrievedChunk) -> tuple[str, str]:
    md = chunk.metadata
    unit = md.section or (f"para-{md.paragraph}" if md.unit_kind == "paragraph" and md.paragraph else "")
    title = md.title
    if md.section:
        label = "Article" if md.unit_kind == "article" else "Section"
        title = f"{md.title} — {label} {md.section}" + (f" ({md.section_heading})" if md.section_heading else "")
    elif md.case_name:
        title = md.case_name
    return f"{md.document_id}|{md.document_version}|{unit}", title


class _Selection:
    def __init__(self, budget: ContextBudget) -> None:
        self.budget = budget
        self.items: list[RetrievedChunk] = []
        self.tokens = 0
        self.per_doc: dict[str, int] = {}
        self.word_sets: dict[str, set[str]] = {}
        self.dropped_duplicates = 0
        self.dropped_budget = 0

    def contains(self, chunk: RetrievedChunk) -> bool:
        return any(c.chunk_id == chunk.chunk_id for c in self.items)

    def _duplicate_of_selected(self, chunk: RetrievedChunk) -> bool:
        md = chunk.metadata
        if md.parent_chunk_id and any(c.chunk_id == md.parent_chunk_id for c in self.items):
            return True
        terms = set(words(chunk.content))
        for other in self.items:
            if chunk.content in other.content:
                return True
            if jaccard(terms, self.word_sets[other.chunk_id]) >= NEAR_DUPLICATE_JACCARD:
                return True
        return False

    def try_add(self, chunk: RetrievedChunk) -> bool:
        if self.contains(chunk):
            return False
        if self._duplicate_of_selected(chunk):
            self.dropped_duplicates += 1
            return False
        cost = _tokens(chunk)
        children = [c for c in self.items if c.metadata.parent_chunk_id == chunk.chunk_id]
        if children:
            # Parent expansion: replace already-selected children by their parent if it fits.
            freed = sum(_tokens(c) for c in children)
            if self.tokens - freed + cost > self.budget.max_context_tokens:
                self.dropped_budget += 1
                return False
            for c in children:
                self._remove(c)
            self.dropped_duplicates += len(children)
        doc = chunk.metadata.document_id
        if (
            len(self.items) >= self.budget.max_chunks
            or self.per_doc.get(doc, 0) >= self.budget.max_chunks_per_document
            or self.tokens + cost > self.budget.max_context_tokens
        ):
            self.dropped_budget += 1
            return False
        self.items.append(chunk)
        self.tokens += cost
        self.per_doc[doc] = self.per_doc.get(doc, 0) + 1
        self.word_sets[chunk.chunk_id] = set(words(chunk.content))
        return True

    def _remove(self, chunk: RetrievedChunk) -> None:
        self.items.remove(chunk)
        self.tokens -= _tokens(chunk)
        doc = chunk.metadata.document_id
        self.per_doc[doc] -= 1
        self.word_sets.pop(chunk.chunk_id, None)


class ContextBuilder:
    def build(
        self, candidates: list[RetrievedChunk], subqueries: list[SubQuery], budget: ContextBudget
    ) -> BuiltContext:
        ranked = sorted(candidates, key=lambda c: c.final_score, reverse=True)
        considered = len(ranked)
        dropped_low = 0
        # Exact matches on provisions the user named (metadata/graph retrievers) are pinned: they
        # bypass the relevance floor and enter the context first. No reranker score can drop them.
        pinned = sorted(
            (c for c in ranked if {"metadata", "graph"} & set(c.scores)),
            key=lambda c: (c.metadata.document_id, c.metadata.hierarchy_level, c.metadata.char_start),
        )
        pinned_ids = {c.chunk_id for c in pinned}
        ranked = [c for c in ranked if c.chunk_id not in pinned_ids]
        if ranked:
            # Scores are only comparable within a sub-query (the reranker scores each candidate
            # against the sub-query that retrieved it), so the floor is relative per sub-query.
            best_by_sq: dict[str, float] = {}
            for c in ranked:
                for sid in c.subquery_ids or ["_"]:
                    best_by_sq[sid] = max(best_by_sq.get(sid, 0.0), c.final_score)
            kept = [
                c for c in ranked
                if any(c.final_score >= best_by_sq[sid] * budget.min_relative_relevance for sid in (c.subquery_ids or ["_"]))
            ]
            dropped_low = len(ranked) - len(kept)
            ranked = kept

        selection = _Selection(budget)
        # Phase 0: pinned exact-provision evidence (still subject to budgets and de-duplication).
        for chunk in pinned:
            selection.try_add(chunk)
        # Phase 1: coverage across sub-queries (priority order, round-robin).
        ordered_subqueries = sorted(subqueries, key=lambda s: s.priority)
        taken: dict[str, int] = {sq.subquery_id: 0 for sq in ordered_subqueries}
        rejected: set[str] = set()
        for _ in range(budget.max_evidence_per_subquery):
            progressed = False
            for sq in ordered_subqueries:
                if taken[sq.subquery_id] >= budget.max_evidence_per_subquery:
                    continue
                for chunk in ranked:
                    if sq.subquery_id not in chunk.subquery_ids or chunk.chunk_id in rejected:
                        continue
                    if selection.contains(chunk):
                        continue
                    if selection.try_add(chunk):
                        taken[sq.subquery_id] += 1
                        progressed = True
                        break
                    rejected.add(chunk.chunk_id)
            if not progressed or len(selection.items) >= budget.max_chunks:
                break
        # Phase 2: fill remaining budget in global score order.
        for chunk in ranked:
            if len(selection.items) >= budget.max_chunks:
                break
            if chunk.chunk_id not in rejected:
                selection.try_add(chunk)

        groups: dict[str, EvidenceGroup] = {}
        group_score: dict[str, float] = {}
        for chunk in selection.items:
            key, title = _group_key(chunk)
            group = groups.setdefault(key, EvidenceGroup(group_key=key, title=title, items=[]))
            group.items.append(EvidenceItem(citation_id="", chunk=chunk, token_count=_tokens(chunk)))
            group_score[key] = max(group_score.get(key, 0.0), chunk.final_score)
        ordered_groups = sorted(groups.values(), key=lambda g: group_score[g.group_key], reverse=True)
        counter = 0
        for group in ordered_groups:
            group.items.sort(key=lambda item: (item.chunk.metadata.hierarchy_level, item.chunk.metadata.char_start))
            for item in group.items:
                counter += 1
                item.citation_id = f"C{counter}"

        return BuiltContext(
            groups=ordered_groups,
            token_count=selection.tokens,
            candidates_considered=considered,
            dropped_duplicates=selection.dropped_duplicates,
            dropped_low_relevance=dropped_low,
            dropped_budget=selection.dropped_budget,
        )


def render_context(context: BuiltContext) -> str:
    """Render evidence for the LLM: one block per citation, grouped by legal unit."""
    blocks: list[str] = []
    for group in context.groups:
        blocks.append(f"## {group.title}")
        for item in group.items:
            md = item.chunk.metadata
            where = [f"source: {md.source}"]
            if md.cite_as:
                where.append(f"cite as: {md.cite_as}")
            elif md.case_citation:
                where.append(md.case_citation)
            if md.opinion_type and md.opinion_type not in ("majority", "unanimous"):
                author = f" of {md.opinion_author}" if md.opinion_author else ""
                where.append(f"{md.opinion_type} opinion{author}, not the court's holding")
            if md.page_number:
                where.append(f"page {md.page_number}")
            if md.subsection:
                where.append(f"sub-provision {md.subsection}")
            if md.paragraph and md.unit_kind == "paragraph":
                where.append(f"para {md.paragraph}")
            blocks.append(f"[{item.citation_id}] ({'; '.join(where)})\n{item.chunk.content.strip()}")
    return "\n\n".join(blocks)
