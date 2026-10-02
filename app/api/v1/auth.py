"""Authentication endpoints (bcrypt + signed JWT access tokens)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, status

from app.api.deps import ContainerDep, RateLimited, RequiredUser, UsersDep
from app.api.errors import responses
from app.schemas.auth import LoginRequest, SignupRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["Authentication"])

_SWAGGER_HINT = (
    "\n\n**Swagger:** copy `access_token` from the response, click **Authorize** (top right) and paste it "
    "(without the `Bearer ` prefix). Protected endpoints then send `Authorization: Bearer <token>`."
)


def _user_out(user) -> UserOut:  # type: ignore[no-untyped-def]
    return UserOut(id=user.id, username=user.username, email=user.email, role=user.role, created_at=user.created_at)


@router.post(
    "/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED, dependencies=[RateLimited],
    summary="Create an account and receive an access token",
    description="Passwords are stored as bcrypt hashes (8–72 bytes, must mix letters with digits/symbols). "
    "Disabled when `AUTH_ALLOW_REGISTRATION=false` (403)." + _SWAGGER_HINT,
    responses=responses(403, 409, 422, 429),
)
async def signup(
    body: Annotated[SignupRequest, Body(openapi_examples={"citizen": {"summary": "New citizen account", "value": {
        "username": "test_user", "email": "test@example.com", "password": "Change-me-123", "role": "citizen"}}})],
    container: ContainerDep, users: UsersDep,
) -> TokenResponse:
    user = await container.auth.register(users, username=body.username, email=body.email, password=body.password,
                                         role=body.role)
    token = container.auth.issue(user)
    return TokenResponse(message="Signup successful", user=user.username, role=user.role, **token.model_dump())


@router.post(
    "/login", response_model=TokenResponse, dependencies=[RateLimited],
    summary="Log in and receive a signed JWT",
    description="Accepts a username or email. Invalid credentials return 401 (no user enumeration)." + _SWAGGER_HINT,
    responses=responses(401, 422, 429),
)
async def login(
    body: Annotated[LoginRequest, Body(openapi_examples={"login": {"summary": "Log in", "value": {
        "username": "test_user", "password": "Change-me-123"}}})],
    container: ContainerDep, users: UsersDep,
) -> TokenResponse:
    user = await container.auth.authenticate(users, body.username, body.password)
    token = container.auth.issue(user)
    return TokenResponse(message="Login successful", user=user.username, role=user.role, **token.model_dump())


@router.get("/me", response_model=UserOut, summary="Current user (requires bearer token)",
            description="Use it to check that Swagger's **Authorize** token works.", responses=responses(401))
async def me(user: RequiredUser) -> UserOut:
    return _user_out(user)
