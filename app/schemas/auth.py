"""Authentication schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import RoleName

_EMAIL = r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}$"


class SignupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.\-]+$")
    email: str | None = Field(default=None, max_length=254, pattern=_EMAIL)
    password: str = Field(min_length=8, max_length=72)
    role: RoleName = "citizen"

    @field_validator("password")
    @classmethod
    def _password_strength(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("password must be at most 72 bytes")
        if value.isdigit() or value.isalpha():
            raise ValueError("password must mix letters with digits or symbols")
        return value


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=254, description="Username or email")
    password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    id: str
    username: str
    email: str | None
    role: str
    created_at: datetime


class TokenResponse(BaseModel):
    message: str
    user: str
    role: str
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth token type, not a secret
    expires_in: int
