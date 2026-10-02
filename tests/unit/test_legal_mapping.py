from __future__ import annotations

from typing import Any

from app.core.config import PROJECT_ROOT
from app.domain.retrieval import MappingType
from app.services.legal_mapping import LegalProvisionMapper

DATASET = PROJECT_ROOT / "data" / "mappings" / "ipc_bns.json"


def test_exact_forward_mapping_with_provenance() -> None:
    m = LegalProvisionMapper(DATASET).lookup_dataset("IPC", "420")
    assert m.mapping_type == MappingType.EXACT
    assert m.target_act == "BNS" and m.target_sections == ["318(4)"]
    assert m.provenance and m.verification_status == "curated_unverified"
    assert m.effective_date is not None and m.effective_date.isoformat() == "2024-07-01"


def test_no_mapping_and_unknown_are_distinct() -> None:
    mapper = LegalProvisionMapper(DATASET)
    assert mapper.lookup_dataset("IPC", "377").mapping_type == MappingType.NO_MAPPING
    unknown = mapper.lookup_dataset("IPC", "9999")
    assert unknown.mapping_type == MappingType.UNKNOWN and unknown.target_sections == []


def test_reverse_mapping_consolidation_is_not_ambiguous() -> None:
    m = LegalProvisionMapper(DATASET).lookup_dataset("BNS", "318")
    assert m.mapping_type == MappingType.EXACT
    assert set(m.target_sections) == {"415", "417", "420"}
    assert "Consolidates" in (m.notes or "")


def test_subsection_lookup_uses_base_section() -> None:
    assert LegalProvisionMapper(DATASET).lookup_dataset("BNS", "103(1)").target_sections == ["302"]


class _Graph:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    async def replacements(self, code: str, section: str) -> list[dict[str, Any]]:
        return self.rows

    async def replaced_from(self, code: str, section: str) -> list[dict[str, Any]]:
        return self.rows


async def test_graph_disagreement_marks_ambiguous() -> None:
    mapper = LegalProvisionMapper(DATASET, graph=_Graph([{"section": "999"}]))  # type: ignore[arg-type]
    m = await mapper.map("IPC", "420")
    assert m.mapping_type == MappingType.AMBIGUOUS
    assert "knowledge graph" in (m.notes or "")


async def test_graph_confirmation_and_graph_only() -> None:
    confirmed = await LegalProvisionMapper(DATASET, graph=_Graph([{"section": "318"}])).map("IPC", "420")  # type: ignore[arg-type]
    assert confirmed.mapping_type == MappingType.EXACT and "confirmed" in confirmed.provenance
    graph_only = await LegalProvisionMapper(DATASET, graph=_Graph([{"section": "7"}])).map("IPC", "9999")  # type: ignore[arg-type]
    assert graph_only.mapping_type == MappingType.APPROXIMATE and graph_only.verification_status == "graph_unverified"
