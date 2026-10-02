from __future__ import annotations

import time

import jwt
import pytest

from app.api.rate_limit import SlidingWindowRateLimiter
from app.core.exceptions import AuthenticationError
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password

SECRET = "s" * 40


def test_password_hashing_roundtrip() -> None:
    h = hash_password("correct horse 1")
    assert h != "correct horse 1"
    assert verify_password("correct horse 1", h)
    assert not verify_password("wrong", h)
    assert not verify_password("anything", None)


def test_password_over_72_bytes_rejected() -> None:
    with pytest.raises(ValueError):
        hash_password("x" * 73)


def test_token_roundtrip_and_tampering() -> None:
    token, ttl = create_access_token("user-1", secret=SECRET, algorithm="HS256", issuer="ll", expires_minutes=5)
    assert ttl == 300
    assert decode_access_token(token, secret=SECRET, algorithm="HS256", issuer="ll")["sub"] == "user-1"
    with pytest.raises(AuthenticationError):
        decode_access_token(token, secret="other" * 10, algorithm="HS256", issuer="ll")
    with pytest.raises(AuthenticationError):
        decode_access_token(token, secret=SECRET, algorithm="HS256", issuer="someone-else")


def test_expired_token_rejected() -> None:
    claims = {"sub": "u", "iss": "ll", "iat": int(time.time()) - 100, "exp": int(time.time()) - 10, "type": "access"}
    token = jwt.encode(claims, SECRET, algorithm="HS256")
    with pytest.raises(AuthenticationError, match="expired"):
        decode_access_token(token, secret=SECRET, algorithm="HS256", issuer="ll")


def test_none_algorithm_rejected() -> None:
    token = jwt.encode({"sub": "u", "iss": "ll", "iat": 1, "exp": 9999999999, "type": "access"}, None, algorithm="none")
    with pytest.raises(AuthenticationError):
        decode_access_token(token, secret=SECRET, algorithm="HS256", issuer="ll")


def test_rate_limiter_window_and_bounded_clients() -> None:
    limiter = SlidingWindowRateLimiter(limit=2, window_seconds=60, max_clients=100)
    assert limiter.check("a")[0] and limiter.check("a")[0]
    allowed, retry_after = limiter.check("a")
    assert not allowed and retry_after > 0
    assert limiter.check("b")[0]
    for i in range(500):
        limiter.check(f"c{i}")
    assert len(limiter._hits) <= 100
