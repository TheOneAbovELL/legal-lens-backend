"""Retrieval profiles (FAST / BALANCED / DEEP) and the adaptive profile selector.

Instead of scattering if-statements across the pipeline, every retrieval decision (sources,
candidate depth, reranker, expansion, decomposition, context budget, chunk representation) is a
field of a :class:`RetrievalProfile`. The selector maps query characteristics to a profile:

* ``rules`` mode: configurable complexity -> profile and intent minimums;
* ``data_driven`` mode: additionally picks, per complexity class, the chunk profile with the best
  measured metric from the latest evaluation run (``evaluation/results/latest.json``).
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from app.core.exceptions import ConfigurationError
from app.core.logging import get_logger
from app.domain.query import Complexity, ComplexityResult, IntentResult

logger = get_logger(__name__)
PROFILE_ORDER = ["FAST", "BALANCED", "DEEP"]


class RetrievalProfile(BaseModel):
    name: str
    top_k: int = Field(ge=1, le=100)
    candidate_k: int = Field(ge=1, le=200)
    sources: list[str]
    source_weights: dict[str, float] = Field(default_factory=dict)
    reranker: str = "none"
    query_expansion: bool = False
    decomposition: bool = False
    max_context_tokens: int = Field(ge=50)
    max_chunks: int = Field(ge=1)
    max_chunks_per_document: int = Field(ge=1)
    max_evidence_per_subquery: int = Field(ge=1)
    chunk_profiles: list[str] | None = None
    selection_reasons: list[str] = Field(default_factory=list)


class ProfileSelection(BaseModel):
    profile: RetrievalProfile
    mode: str


class RetrievalProfileSelector:
    def __init__(
        self,
        profiles: dict[str, RetrievalProfile],
        *,
        complexity_map: dict[str, str],
        intent_minimum: dict[str, str],
        chunk_profiles_by_type: dict[str, list[str]],
        default_chunk_profile: str,
        mode: str = "rules",
        evaluation_results: Path | None = None,
        available_sources: set[str] | None = None,
        indexed_chunk_profiles: set[str] | None = None,
    ) -> None:
        self._profiles = profiles
        self._complexity_map = complexity_map
        self._intent_minimum = intent_minimum
        self._chunk_by_type = chunk_profiles_by_type
        self._default_chunk_profile = default_chunk_profile
        self._mode = mode
        self.available_sources = available_sources
        self.indexed_chunk_profiles = indexed_chunk_profiles
        self._learned: dict[str, str] = self._load_learned(evaluation_results) if mode == "data_driven" else {}

    @classmethod
    def from_file(cls, path: Path, **kwargs: object) -> RetrievalProfileSelector:
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
            profiles = {name: RetrievalProfile(name=name, **spec) for name, spec in raw["profiles"].items()}
        except (OSError, KeyError, ValueError) as exc:
            raise ConfigurationError(f"invalid retrieval profiles file {path}: {exc}") from exc
        return cls(
            profiles,
            complexity_map=raw.get("complexity_to_profile", {}),
            intent_minimum=raw.get("intent_minimum_profile", {}),
            chunk_profiles_by_type=raw.get("chunk_profiles_by_document_type", {}),
            **kwargs,  # type: ignore[arg-type]
        )

    @staticmethod
    def _load_learned(path: Path | None) -> dict[str, str]:
        """Best chunk profile per complexity from a previous evaluation run."""
        if path is None or not Path(path).exists():
            logger.warning("data_driven selection requested but no evaluation results found; using rules")
            return {}
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            return {str(k): str(v) for k, v in data.get("recommendations", {}).get("chunk_profile_by_complexity", {}).items()}
        except (OSError, ValueError) as exc:
            logger.warning("could not read evaluation results; using rules", extra={"error": str(exc)})
            return {}

    @property
    def names(self) -> list[str]:
        return list(self._profiles)

    def get(self, name: str) -> RetrievalProfile:
        try:
            return self._profiles[name.upper()].model_copy(deep=True)
        except KeyError as exc:
            raise ConfigurationError(f"unknown retrieval profile {name!r}; available: {self.names}") from exc

    def select(
        self,
        complexity: ComplexityResult | None,
        intent: IntentResult | None,
        *,
        override: str | None = None,
        document_types: list[str] | None = None,
    ) -> ProfileSelection:
        reasons: list[str] = []
        if override:
            name = override.upper()
            reasons.append(f"profile forced by request: {name}")
        else:
            level = complexity.complexity.value if complexity else Complexity.MODERATE.value
            name = self._complexity_map.get(level, "BALANCED")
            reasons.append(f"complexity {level} -> {name}")
            if intent is not None:
                minimum = self._intent_minimum.get(intent.intent.value)
                if minimum and PROFILE_ORDER.index(minimum) > PROFILE_ORDER.index(name):
                    reasons.append(f"intent {intent.intent.value} requires at least {minimum}")
                    name = minimum
        profile = self.get(name)

        if self.available_sources is not None:
            missing = [s for s in profile.sources if s not in self.available_sources]
            if missing:
                profile.sources = [s for s in profile.sources if s in self.available_sources]
                reasons.append(f"sources unavailable: {', '.join(missing)}")

        level = complexity.complexity.value if complexity else None
        if level and level in self._learned:
            profile.chunk_profiles = [self._learned[level]]
            reasons.append(f"chunk profile {self._learned[level]} selected from evaluation results")
            mode = "data_driven"
        else:
            types = document_types or []
            chosen: list[str] = []
            for t in types:
                for p in self._chunk_by_type.get(t, []):
                    if p not in chosen:
                        chosen.append(p)
            profile.chunk_profiles = chosen or [self._default_chunk_profile]
            reasons.append(f"chunk profiles {profile.chunk_profiles} (rules)")
            mode = "rules"
        if self.indexed_chunk_profiles is not None and profile.chunk_profiles:
            present = [p for p in profile.chunk_profiles if p in self.indexed_chunk_profiles]
            if not present:
                reasons.append("selected chunk profile not indexed; searching all indexed representations")
            profile.chunk_profiles = present or None
        profile.selection_reasons = reasons
        return ProfileSelection(profile=profile, mode=mode)
