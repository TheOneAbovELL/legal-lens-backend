"""Shared API schemas."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.domain.acts import canonical_act
from app.domain.retrieval import ProvisionMapping, RetrievalFilters

ProfileName = Literal["FAST", "BALANCED", "DEEP"]
RoleName = Literal["citizen", "advocate", "researcher"]
_IDENT = r"^[A-Za-z0-9_.:\-]{1,128}$"


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str | None = None
    details: list[dict] | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class SearchFilters(BaseModel):
    document_ids: list[str] | None = Field(default=None, max_length=50)
    document_types: list[Literal["statute", "constitution", "case_law", "regulation", "commentary", "other"]] | None = None
    acts: list[str] | None = Field(default=None, max_length=20)
    sections: list[str] | None = Field(default=None, max_length=50)
    jurisdiction: str | None = Field(default=None, max_length=16)
    court: list[str] | None = Field(default=None, max_length=20)
    date_from: date | None = None
    date_to: date | None = None

    def to_domain(self) -> RetrievalFilters:
        acts = [canonical_act(a) or a.upper() for a in self.acts] if self.acts else None
        return RetrievalFilters(
            document_ids=self.document_ids, document_types=self.document_types, acts=acts,
            sections=[s.upper() for s in self.sections] if self.sections else None,
            jurisdiction=self.jurisdiction, courts=self.court,
            decided_after=self.date_from, decided_before=self.date_to,
        )


class BnsAlert(BaseModel):
    """Statute alert for legacy provisions (frontend contract: old / new / effective)."""

    old: str
    new: str | None
    effective: date | None
    mapping_type: str
    subject: str | None = None
    notes: str | None = None
    verification_status: str
    provenance: str

    @classmethod
    def from_mapping(cls, m: ProvisionMapping) -> BnsAlert:
        new = ", ".join(f"{m.target_act} {t}" for t in m.target_sections) or None
        return cls(
            old=f"{m.source_act} {m.source_section}", new=new, effective=m.effective_date,
            mapping_type=m.mapping_type.value, subject=m.subject, notes=m.notes,
            verification_status=m.verification_status, provenance=m.provenance,
        )
