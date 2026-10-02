"""Labelled evaluation dataset model."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from app.core.exceptions import ConfigurationError
from app.core.text import sha256


class EvalExample(BaseModel):
    id: str
    query: str
    #: "document_id:section" units, e.g. "fixture-ipc:420". The unit of relevance.
    expected_sections: list[str] = Field(default_factory=list)
    expected_document_ids: list[str] = Field(default_factory=list)
    relevant_chunk_ids: list[str] = Field(default_factory=list)
    query_type: str = "general"
    complexity: str = "SIMPLE"
    evidence_requirements: str = ""
    expected_answer_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _has_labels(self) -> EvalExample:
        if not (self.expected_sections or self.expected_document_ids or self.relevant_chunk_ids):
            raise ValueError(f"example {self.id} has no relevance labels")
        return self

    @property
    def expected_units(self) -> set[str]:
        if self.expected_sections:
            return set(self.expected_sections)
        return {f"{d}:*" for d in self.expected_document_ids}


class EvalDataset(BaseModel):
    name: str
    description: str = ""
    corpus: str
    examples: list[EvalExample]
    fingerprint: str = ""

    @classmethod
    def load(cls, path: Path) -> EvalDataset:
        try:
            raw = Path(path).read_text(encoding="utf-8")
            dataset = cls.model_validate(json.loads(raw))
        except (OSError, ValueError) as exc:
            raise ConfigurationError(f"invalid evaluation dataset {path}: {exc}") from exc
        ids = [e.id for e in dataset.examples]
        if len(ids) != len(set(ids)):
            raise ConfigurationError("evaluation example IDs must be unique")
        dataset.fingerprint = sha256(raw)[:16]
        return dataset
