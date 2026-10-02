"""Chat API schemas. ``answer`` and ``source`` are kept from the original v1 contract."""

from __future__ import annotations

from pydantic import AliasChoices, BaseModel, Field

from app.domain.retrieval import Citation
from app.graph.runner import PipelineMetadata, RetrievalDiagnostics
from app.schemas.common import _IDENT, BnsAlert, ProfileName, RoleName, SearchFilters

CHAT_EXAMPLES = {
    "simple": {"summary": "SIMPLE — single provision lookup",
               "value": {"query": "What is the punishment for cheating under Section 420 IPC?"}},
    "moderate": {"summary": "MODERATE — two provisions / mapping",
                 "value": {"query": "Explain the difference between Article 14 and Article 21."}},
    "complex": {"summary": "COMPLEX — comparison across codes (decomposed)",
                "value": {"query": "Compare the legal consequences under IPC 420 and BNS 318, analyze how the change "
                                   "affects an accused person, and cite the relevant authorities."}},
    "follow_up": {"summary": "MEM-0 follow-up (send twice with the same session_id)",
                  "value": {"query": "What is its punishment?", "session_id": "demo-session-1"}},
    "refusal": {"summary": "Safety guard (redirected, no retrieval)", "value": {"query": "Will I win my cheating case?"}},
}


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=8000, description="The legal question")
    session_id: str | None = Field(
        default=None, pattern=_IDENT, validation_alias=AliasChoices("session_id", "conversation_id"),
        description="Optional conversation id (alias: conversation_id). Enables MEM-0 short-term follow-ups.",
    )
    user_role: RoleName | None = Field(default=None, description="Answer style; defaults to the user's role, else citizen")
    profile: ProfileName | None = Field(default=None, description="Force a retrieval profile (default: adaptive routing)")
    filters: SearchFilters | None = Field(default=None, description="Restrict retrieval by act, section, court, date…")
    stream: bool = Field(default=False, description="Return Server-Sent Events instead of JSON")

    model_config = {"populate_by_name": True,
                    "json_schema_extra": {"example": CHAT_EXAMPLES["simple"]["value"]}}


class ChatResponse(BaseModel):
    answer: str | None = Field(description="Grounded answer with [C#] evidence and [M#] mapping citations")
    source: str = Field(description="Legacy field: 'qdrant' when answered from indexed evidence, else 'none'")
    request_id: str
    refused: bool = Field(description="True when the safety guard redirected the request")
    citations: list[Citation] = Field(description="Only evidence actually cited in the answer")
    bns_alerts: list[BnsAlert] = Field(description="IPC/CrPC/IEA -> BNS/BNSS/BSA alerts with provenance")
    warnings: list[str]
    disclaimer: str | None
    metadata: PipelineMetadata
    diagnostics: RetrievalDiagnostics | None = Field(
        default=None, description="Stage-by-stage retrieval diagnostics (non-production environments only)"
    )
