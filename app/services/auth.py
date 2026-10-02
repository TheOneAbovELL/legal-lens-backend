"""Authentication service: registration, login and token resolution."""

from __future__ import annotations

from pydantic import BaseModel

from app.core.config import Settings
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.db.models import User
from app.db.repositories import UserRepository


class IssuedToken(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth token type, not a secret
    expires_in: int


class AuthService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def issue(self, user: User) -> IssuedToken:
        token, expires_in = create_access_token(
            user.id,
            secret=self._settings.jwt_secret(),
            algorithm=self._settings.jwt_algorithm,
            issuer=self._settings.jwt_issuer,
            expires_minutes=self._settings.access_token_expire_minutes,
            extra={"role": user.role},
        )
        return IssuedToken(access_token=token, expires_in=expires_in)

    async def register(self, repo: UserRepository, *, username: str, email: str | None, password: str, role: str) -> User:
        if not self._settings.auth_allow_registration:
            raise AuthorizationError("registration disabled", public_message="Self-registration is disabled.")
        return await repo.create(
            username=username, email=email.lower() if email else None, password_hash=hash_password(password), role=role
        )

    async def authenticate(self, repo: UserRepository, login: str, password: str) -> User:
        user = await repo.by_login(login)
        if not verify_password(password, user.password_hash if user else None) or user is None or not user.is_active:
            raise AuthenticationError("invalid credentials", public_message="Invalid username or password.")
        return user

    async def resolve(self, repo: UserRepository, token: str) -> User:
        claims = decode_access_token(
            token, secret=self._settings.jwt_secret(), algorithm=self._settings.jwt_algorithm,
            issuer=self._settings.jwt_issuer,
        )
        user = await repo.get(str(claims["sub"]))
        if user is None or not user.is_active:
            raise AuthenticationError("user not found or inactive")
        return user
