"""FastAPI dependencies: container access, DB sessions, authentication, rate limiting."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.container import Container
from app.core.exceptions import AuthenticationError, RateLimitExceeded
from app.db.models import User
from app.db.repositories import UserRepository

_bearer = HTTPBearer(auto_error=False)


def get_container(request: Request) -> Container:
    return request.app.state.container


ContainerDep = Annotated[Container, Depends(get_container)]


async def get_session(container: ContainerDep) -> AsyncIterator[AsyncSession]:
    async with container.database.sessions() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_users(session: SessionDep) -> UserRepository:
    return UserRepository(session)


UsersDep = Annotated[UserRepository, Depends(get_users)]


async def token_user(
    container: ContainerDep,
    users: UsersDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User | None:
    """Resolve the bearer token if one is sent (invalid tokens are rejected); never enforces login."""
    if credentials is None:
        return None
    if credentials.scheme.lower() != "bearer":
        raise AuthenticationError("unsupported auth scheme")
    return await container.auth.resolve(users, credentials.credentials)


async def optional_user(container: ContainerDep, user: Annotated[User | None, Depends(token_user)]) -> User | None:
    """User for protected resources: required when AUTH_REQUIRED=true, optional otherwise."""
    if user is None and container.settings.auth_required:
        raise AuthenticationError("missing bearer token", public_message="Authentication required.")
    return user


async def required_user(user: Annotated[User | None, Depends(optional_user)]) -> User:
    if user is None:
        raise AuthenticationError("missing bearer token", public_message="Authentication required.")
    return user


OptionalUser = Annotated[User | None, Depends(optional_user)]
RequiredUser = Annotated[User, Depends(required_user)]


def client_key(request: Request, user: User | None) -> str:
    if user is not None:
        return f"user:{user.id}"
    return f"ip:{request.client.host if request.client else 'unknown'}"


async def rate_limit(request: Request, container: ContainerDep, users: UsersDep,
                     credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]) -> None:
    """Applies to public endpoints too (e.g. login), so it must not require authentication."""
    if not container.settings.rate_limit_enabled:
        return
    user: User | None = None
    if credentials is not None:
        try:
            user = await container.auth.resolve(users, credentials.credentials)
        except AuthenticationError:
            user = None  # unauthenticated callers are limited per IP
    allowed, retry_after = request.app.state.rate_limiter.check(client_key(request, user))
    if not allowed:
        exc = RateLimitExceeded(f"rate limit exceeded; retry after {retry_after}s")
        exc.retry_after = retry_after  # type: ignore[attr-defined]
        raise exc


RateLimited = Depends(rate_limit)
