"""Conversation API schemas (built from ORM rows via ``from_attributes``; no persistence imports)."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


def _utc(value: datetime | None) -> datetime | None:
    """SQLite drops tzinfo; timestamps are stored in UTC, so label naive values explicitly."""
    return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200, description="Optional; defaults to 'New conversation'")


class ConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    citation_id: str
    document_id: str
    chunk_id: str | None = None
    source: str
    title: str
    act: str | None = None
    section: str | None = None
    page: int | None = None
    excerpt: str = ""
    score: float | None = None


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    conversation_id: str
    role: str = Field(description="user | assistant")
    content: str
    status: str = Field(description="complete | refused | insufficient_evidence | small_talk | failed | incomplete")
    request_id: str | None = None
    complexity: str | None = None
    intent: str | None = None
    created_at: datetime
    citations: list[EvidenceOut] = Field(default_factory=list, validation_alias=AliasChoices("citations", "evidence"))

    _tz = field_validator("created_at")(_utc)


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None

    _tz = field_validator("created_at", "updated_at", "archived_at")(_utc)


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


class ConversationList(BaseModel):
    conversations: list[ConversationOut]
    total: int
