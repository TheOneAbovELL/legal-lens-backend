"""Deterministic query expansion for the MODERATE path (no LLM).

Produces a small set of focused retrieval variants:
* the normalised query itself;
* an act-expanded variant (abbreviations -> full statute names, which is how statute text is
  written, helping dense retrieval);
* counterpart provisions from the mapping dataset (e.g. IPC 420 -> BNS 318) when the mapping is
  known, so both old and new code text can be retrieved.
"""

from __future__ import annotations

from app.domain.acts import ACT_ALIAS_RE, act_display_name, alias_to_code
from app.domain.query import EntityType, LegalEntity, SubQuery
from app.domain.retrieval import MappingType
from app.rag.query.entities import provision_refs
from app.services.legal_mapping import LegalProvisionMapper, base_section


def expand_acts(query: str) -> str:
    def repl(match) -> str:  # type: ignore[no-untyped-def]
        code = alias_to_code(match.group(0))
        name = act_display_name(code) or match.group(0)
        return name if name.lower() != match.group(0).lower() else match.group(0)

    return ACT_ALIAS_RE.sub(repl, query)


def counterpart_subqueries(
    entities: list[LegalEntity], mapper: LegalProvisionMapper | None, start_index: int, limit: int
) -> list[SubQuery]:
    if mapper is None:
        return []
    subqueries: list[SubQuery] = []
    mentioned = set(provision_refs(entities))
    for act, number in provision_refs(entities):
        if len(subqueries) >= limit or not mapper.supports(act):
            continue
        mapping = mapper.lookup_dataset(act, number)
        if mapping.mapping_type not in (MappingType.EXACT, MappingType.APPROXIMATE):
            continue
        for target in mapping.target_sections:
            ref = (mapping.target_act, base_section(target))
            if ref in mentioned:
                continue
            mentioned.add(ref)
            subqueries.append(
                SubQuery(
                    subquery_id=f"q{start_index + len(subqueries)}",
                    query=f"{act_display_name(mapping.target_act)} Section {target} {mapping.subject or ''}".strip(),
                    purpose=f"counterpart of {act} Section {number} ({mapping.mapping_type.value} mapping)",
                    required_evidence="statutory text of the counterpart provision",
                    legal_entities=[f"{mapping.target_act} {target}"],
                    priority=2,
                )
            )
    return subqueries


class QueryExpander:
    def __init__(self, mapper: LegalProvisionMapper | None, max_variants: int = 4) -> None:
        self._mapper = mapper
        self._max_variants = max_variants

    def expand(self, query: str, entities: list[LegalEntity]) -> list[SubQuery]:
        subqueries = [SubQuery(subquery_id="q0", query=query, purpose="original question", priority=0)]
        provisions = [e for e in entities if e.type in (EntityType.SECTION, EntityType.ARTICLE)]
        if len(provisions) > 1:
            # Comparisons: one focused look-up per named provision so each gets its own evidence.
            for e in provisions:
                label = "Article" if e.type == EntityType.ARTICLE else "Section"
                text = f"{act_display_name(e.act) or ''} {label} {e.value}".strip()
                subqueries.append(SubQuery(subquery_id=f"q{len(subqueries)}", query=text,
                                           purpose=f"text of {e.raw}", legal_entities=[e.raw], priority=1))
        else:
            expanded = expand_acts(query)
            if expanded != query:
                subqueries.append(
                    SubQuery(subquery_id="q1", query=expanded, purpose="statute names expanded", priority=1,
                             legal_entities=[e.raw for e in entities if e.type != EntityType.ACT])
                )
        remaining = self._max_variants - len(subqueries)
        subqueries.extend(counterpart_subqueries(entities, self._mapper, len(subqueries), max(remaining, 0)))
        return subqueries[: self._max_variants]
