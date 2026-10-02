"""Conversation history endpoints. Always authenticated; every read/write is scoped to the caller."""

from __future__ import annotations

from fastapi import APIRouter, Path, Query, Response, status

from app.api.deps import ContainerDep, RateLimited, RequiredUser
from app.api.errors import responses
from app.schemas.common import _IDENT
from app.schemas.conversations import (
    ConversationCreate,
    ConversationDetail,
    ConversationList,
    ConversationOut,
    ConversationUpdate,
    MessageOut,
)

router = APIRouter(prefix="/conversations", tags=["Conversations"])
ConversationId = Path(pattern=_IDENT, description="Conversation id returned by POST /conversations or /chat")


@router.get("", response_model=ConversationList, summary="List my conversations (most recent first)",
            responses=responses(401))
async def list_conversations(container: ContainerDep, user: RequiredUser,
                             limit: int = Query(default=100, ge=1, le=500)) -> ConversationList:
    rows = await container.conversations.list(user, limit=limit)
    return ConversationList(conversations=[ConversationOut.model_validate(r) for r in rows], total=len(rows))


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED, dependencies=[RateLimited],
             summary="Create an empty conversation",
             description="Optional: `POST /chat` without `conversation_id` also creates one, titled from the question.",
             responses=responses(401, 422, 429))
async def create_conversation(body: ConversationCreate, container: ContainerDep, user: RequiredUser) -> ConversationOut:
    row = await container.conversations.create(user, body.title)
    return ConversationOut.model_validate(row)


@router.get("/{conversation_id}", response_model=ConversationDetail, summary="Get a conversation with its messages",
            description="Messages carry their stored citations so history renders without touching the index.",
            responses=responses(401, 404))
async def get_conversation(container: ContainerDep, user: RequiredUser,
                           conversation_id: str = ConversationId) -> ConversationDetail:
    row = await container.conversations.get(user, conversation_id, with_messages=True)
    return ConversationDetail.model_validate(row)


@router.get("/{conversation_id}/messages", response_model=list[MessageOut], summary="Messages of a conversation",
            responses=responses(401, 404))
async def get_messages(container: ContainerDep, user: RequiredUser, conversation_id: str = ConversationId) -> list[MessageOut]:
    row = await container.conversations.get(user, conversation_id, with_messages=True)
    return [MessageOut.model_validate(m) for m in row.messages]


@router.patch("/{conversation_id}", response_model=ConversationOut, summary="Rename a conversation",
              responses=responses(401, 404, 422))
async def rename_conversation(body: ConversationUpdate, container: ContainerDep, user: RequiredUser,
                              conversation_id: str = ConversationId) -> ConversationOut:
    row = await container.conversations.rename(user, conversation_id, body.title.strip())
    return ConversationOut.model_validate(row)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a conversation",
               description="Deletes the conversation, its messages and stored citations. Not reversible.",
               responses=responses(401, 404))
async def delete_conversation(container: ContainerDep, user: RequiredUser, conversation_id: str = ConversationId) -> Response:
    await container.conversations.delete(user, conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
