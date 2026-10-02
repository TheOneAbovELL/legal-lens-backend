"""MEM-0: short-term, query-level session memory (MoM 2026-01-09: "not persistent memory").

Bounded in every dimension (turns per session, number of sessions, TTL) and process-local.
Used for two things only:
* resolving follow-up questions ("what is its punishment?") by carrying over the provisions
  discussed in the previous turn into retrieval;
* giving the LLM a very short conversation summary (never treated as evidence).
"""

from __future__ import annotations

import re
import time
from collections import OrderedDict, deque

from pydantic import BaseModel, Field

from app.core.text import count_tokens
from app.domain.query import EntityType, LegalEntity

_FOLLOW_UP = re.compile(
    r"\b(?:it|its|this|that|these|those|the\s+same|said\s+(?:section|provision|article)|above|"
    r"what\s+about|and\s+(?:the|its)|how\s+about)\b",
    re.IGNORECASE,
)


class SessionTurn(BaseModel):
    query: str
    answer_preview: str = ""
    entities: list[LegalEntity] = Field(default_factory=list)
    timestamp: float = Field(default_factory=time.time)


class FollowUpResolution(BaseModel):
    retrieval_query: str
    inherited_entities: list[LegalEntity] = Field(default_factory=list)
    is_follow_up: bool = False


class SessionMemory:
    def __init__(self, max_turns: int = 4, ttl_seconds: int = 1800, max_sessions: int = 5000) -> None:
        self._max_turns = max_turns
        self._ttl = ttl_seconds
        self._max_sessions = max_sessions
        self._sessions: OrderedDict[str, deque[SessionTurn]] = OrderedDict()

    def _evict(self) -> None:
        now = time.time()
        expired = [k for k, turns in self._sessions.items() if not turns or now - turns[-1].timestamp > self._ttl]
        for key in expired:
            del self._sessions[key]
        while len(self._sessions) > self._max_sessions:
            self._sessions.popitem(last=False)

    def history(self, key: str) -> list[SessionTurn]:
        self._evict()
        turns = self._sessions.get(key)
        if turns is None:
            return []
        self._sessions.move_to_end(key)
        return list(turns)

    def add(self, key: str, turn: SessionTurn) -> None:
        turns = self._sessions.setdefault(key, deque(maxlen=self._max_turns))
        turns.append(turn)
        self._sessions.move_to_end(key)
        self._evict()

    def clear(self, key: str) -> None:
        self._sessions.pop(key, None)

    @property
    def session_count(self) -> int:
        return len(self._sessions)


def resolve_follow_up(query: str, entities: list[LegalEntity], history: list[SessionTurn]) -> FollowUpResolution:
    """Carry provisions from the previous turn into a follow-up that names none itself."""
    has_provision = any(e.type in (EntityType.SECTION, EntityType.ARTICLE, EntityType.CASE_CITATION) for e in entities)
    if has_provision or not history:
        return FollowUpResolution(retrieval_query=query)
    if not (_FOLLOW_UP.search(query) or count_tokens(query) <= 6):
        return FollowUpResolution(retrieval_query=query)
    for turn in reversed(history):
        inherited = [e for e in turn.entities if e.type in (EntityType.SECTION, EntityType.ARTICLE, EntityType.CASE_CITATION)]
        if inherited:
            refs = ", ".join(e.raw for e in inherited[:4])
            return FollowUpResolution(
                retrieval_query=f"{query} (regarding {refs})", inherited_entities=inherited, is_follow_up=True
            )
    return FollowUpResolution(retrieval_query=query)
