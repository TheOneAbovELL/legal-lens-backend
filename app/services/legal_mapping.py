"""Legacy -> new code provision mapping (IPC->BNS, CrPC->BNSS, IEA->BSA) with provenance.

Results are always explicit about their status: ``exact`` / ``approximate`` / ``no_mapping`` /
``ambiguous`` (dataset and knowledge graph disagree) / ``unknown`` (not in any source). The mapper
never invents a correspondence.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from pydantic import BaseModel

from app.core.exceptions import ConfigurationError, RetrievalError
from app.core.logging import get_logger
from app.domain.retrieval import MappingType, ProvisionMapping
from app.providers.graph_db.neo4j_client import Neo4jClient

logger = get_logger(__name__)

# Legacy code -> replacement code.
CODE_SUCCESSION = {"IPC": "BNS", "CRPC": "BNSS", "IEA": "BSA"}
CODE_PREDECESSOR = {new: old for old, new in CODE_SUCCESSION.items()}


def base_section(section: str) -> str:
    return section.split("(", 1)[0].strip().upper()


class _Entry(BaseModel):
    source_act: str
    source_section: str
    target_act: str
    target_sections: list[str]
    mapping_type: MappingType
    subject: str | None = None
    notes: str | None = None


class LegalProvisionMapper:
    def __init__(self, dataset_path: Path, graph: Neo4jClient | None = None) -> None:
        try:
            raw = json.loads(Path(dataset_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigurationError(f"cannot load provision mapping dataset {dataset_path}: {exc}") from exc
        meta = raw.get("_meta", {})
        self._provenance = meta.get("provenance", str(dataset_path))
        self._verification = meta.get("verification_status", "unverified")
        effective = meta.get("effective_date")
        self._effective = date.fromisoformat(effective) if effective else None
        self._forward: dict[tuple[str, str], _Entry] = {}
        self._reverse: dict[tuple[str, str], list[_Entry]] = {}
        for item in raw.get("mappings", []):
            entry = _Entry.model_validate(item)
            self._forward[(entry.source_act, base_section(entry.source_section))] = entry
            for target in entry.target_sections:
                self._reverse.setdefault((entry.target_act, base_section(target)), []).append(entry)
        self._graph = graph

    @property
    def size(self) -> int:
        return len(self._forward)

    def supports(self, act: str) -> bool:
        return act.upper() in CODE_SUCCESSION or act.upper() in CODE_PREDECESSOR

    def _from_entry(self, entry: _Entry) -> ProvisionMapping:
        return ProvisionMapping(
            source_act=entry.source_act,
            source_section=entry.source_section,
            target_act=entry.target_act,
            target_sections=list(entry.target_sections),
            mapping_type=entry.mapping_type,
            subject=entry.subject,
            notes=entry.notes,
            provenance=self._provenance,
            verification_status=self._verification,
            effective_date=self._effective,
        )

    def lookup_dataset(self, act: str, section: str) -> ProvisionMapping:
        """Map a provision in either direction using the curated dataset only."""
        act, number = act.upper(), base_section(section)
        if act in CODE_SUCCESSION:
            entry = self._forward.get((act, number))
            if entry:
                return self._from_entry(entry)
            return self._unknown(act, section, CODE_SUCCESSION[act])
        if act in CODE_PREDECESSOR:
            entries = self._reverse.get((act, number), [])
            if not entries:
                return self._unknown(act, section, CODE_PREDECESSOR[act])
            sources = [e.source_section for e in entries]
            first = entries[0]
            types = {e.mapping_type for e in entries}
            # Several legacy sections consolidated into one new section is a known many-to-one
            # mapping, not an ambiguity; only conflicting mapping types are ambiguous.
            mapping_type = first.mapping_type if len(types) == 1 else MappingType.AMBIGUOUS
            notes = first.notes if len(entries) == 1 else (
                f"Consolidates {len(entries)} legacy provisions: " + ", ".join(f"{first.source_act} {s}" for s in sources)
            )
            return ProvisionMapping(
                source_act=act,
                source_section=section,
                target_act=first.source_act,
                target_sections=sources,
                mapping_type=mapping_type,
                subject=first.subject if len(entries) == 1 else None,
                notes=notes,
                provenance=self._provenance,
                verification_status=self._verification,
                effective_date=self._effective,
            )
        raise ValueError(f"provision mapping is not supported for act {act!r}")

    def _unknown(self, act: str, section: str, target: str) -> ProvisionMapping:
        return ProvisionMapping(
            source_act=act,
            source_section=section,
            target_act=target,
            mapping_type=MappingType.UNKNOWN,
            provenance=self._provenance,
            verification_status=self._verification,
            notes="Not present in the mapping dataset; no correspondence is asserted.",
        )

    async def map(self, act: str, section: str) -> ProvisionMapping:
        """Dataset lookup, cross-checked against the knowledge graph's REPLACED_BY edges if enabled."""
        result = self.lookup_dataset(act, section)
        if self._graph is None:
            return result
        try:
            if act.upper() in CODE_SUCCESSION:
                rows = await self._graph.replacements(act, base_section(section))
            else:
                rows = await self._graph.replaced_from(act, base_section(section))
        except RetrievalError as exc:
            logger.warning("graph mapping lookup failed; using dataset only", extra={"error_type": type(exc).__name__})
            return result
        graph_targets = sorted({base_section(str(r["section"])) for r in rows if r.get("section")})
        if not graph_targets:
            return result
        dataset_targets = sorted({base_section(t) for t in result.target_sections})
        if result.mapping_type == MappingType.UNKNOWN:
            return result.model_copy(update={
                "target_sections": graph_targets,
                "mapping_type": MappingType.APPROXIMATE,
                "provenance": "Neo4j knowledge graph (REPLACED_BY)",
                "verification_status": "graph_unverified",
                "notes": "Found only in the knowledge graph; treat as approximate until verified.",
            })
        if dataset_targets != graph_targets:
            return result.model_copy(update={
                "mapping_type": MappingType.AMBIGUOUS,
                "notes": f"Dataset maps to {dataset_targets} but the knowledge graph maps to {graph_targets}.",
                "provenance": f"{result.provenance}; Neo4j knowledge graph",
            })
        return result.model_copy(update={"provenance": f"{result.provenance}; confirmed by Neo4j knowledge graph"})
