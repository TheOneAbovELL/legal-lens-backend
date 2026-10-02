"""Retriever interface. Retrievers know nothing about FastAPI or LangGraph."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from pydantic import BaseModel, Field

from app.domain.chunks import Chunk
from app.domain.query import LegalEntity
from app.domain.retrieval import RetrievalFilters, RetrievedChunk


class RetrievalQuery(BaseModel):
    text: str
    subquery_id: str = "q0"
    entities: list[LegalEntity] = Field(default_factory=list)


class Retriever(ABC):
    name: ClassVar[str]
    #: False for retrievers driven by the extracted entities of the whole request (run once).
    per_subquery: ClassVar[bool] = True

    @abstractmethod
    async def retrieve(self, query: RetrievalQuery, filters: RetrievalFilters | None, top_k: int) -> list[RetrievedChunk]:
        """Return up to ``top_k`` results ordered best-first."""


def to_retrieved(chunk: Chunk, source: str, score: float, rank: int, subquery_id: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk.chunk_id,
        content=chunk.content,
        context_header=chunk.context_header,
        metadata=chunk.metadata,
        scores={source: score},
        ranks={source: rank},
        subquery_ids=[subquery_id],
    )
