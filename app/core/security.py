"""Password hashing (bcrypt) and signed, expiring access tokens (JWT)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.exceptions import AuthenticationError

BCRYPT_MAX_BYTES = 72
# Pre-computed hash used to equalise timing when the user does not exist.
_DUMMY_HASH = bcrypt.hashpw(b"timing-equaliser", bcrypt.gensalt(rounds=12)).decode()


def hash_password(password: str) -> str:
    raw = password.encode("utf-8")
    if len(raw) > BCRYPT_MAX_BYTES:
        raise ValueError("password exceeds 72 bytes")
    return bcrypt.hashpw(raw, bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, password_hash: str | None) -> bool:
    raw = password.encode("utf-8")[:BCRYPT_MAX_BYTES]
    if password_hash is None:
        bcrypt.checkpw(raw, _DUMMY_HASH.encode())
        return False
    try:
        return bcrypt.checkpw(raw, password_hash.encode())
    except ValueError:
        return False


def create_access_token(
    subject: str, *, secret: str, algorithm: str, issuer: str, expires_minutes: int, extra: dict | None = None
) -> tuple[str, int]:
    now = datetime.now(UTC)
    expires = timedelta(minutes=expires_minutes)
    claims = {
        "sub": subject,
        "iss": issuer,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int((now + expires).timestamp()),
        "jti": uuid.uuid4().hex,
        "type": "access",
        **(extra or {}),
    }
    return jwt.encode(claims, secret, algorithm=algorithm), int(expires.total_seconds())


def decode_access_token(token: str, *, secret: str, algorithm: str, issuer: str) -> dict:
    try:
        claims = jwt.decode(
            token, secret, algorithms=[algorithm], issuer=issuer,
            options={"require": ["exp", "iat", "sub", "iss"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("token expired", public_message="Access token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError(f"invalid token: {type(exc).__name__}") from exc
    if claims.get("type") != "access":
        raise AuthenticationError("wrong token type")
    return claims
