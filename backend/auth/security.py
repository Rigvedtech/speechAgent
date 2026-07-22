"""Password hashing, JWT, password policy, and auth rate limiting."""

from __future__ import annotations

import logging
import re
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Deque, Optional
from uuid import UUID

import bcrypt
import jwt
from fastapi import HTTPException, Request, status

import config as app_config

logger = logging.getLogger(__name__)

_DUMMY_HASH = bcrypt.hashpw(b"__speechagent_dummy__", bcrypt.gensalt()).decode("utf-8")

_WEAK_JWT_SECRETS = {
    "",
    "dev-change-me-speechagent-jwt-secret",
    "change-me-to-a-long-random-string",
    "secret",
    "changeme",
}


def validate_jwt_config() -> None:
    """Call at startup. Refuse weak JWT secrets in production."""
    secret = (app_config.JWT_SECRET or "").strip()
    weak = (
        secret in _WEAK_JWT_SECRETS
        or len(secret) < 32
        or secret.startswith("dev-")
        or secret.startswith("change-me")
    )
    if app_config.APP_ENV == "production" and weak:
        raise RuntimeError(
            "JWT_SECRET is missing or too weak for production. "
            "Set a random secret of at least 32 characters in backend/.env"
        )
    if weak:
        logger.warning(
            "[AUTH] JWT_SECRET is weak — fine for local dev only. "
            "Set a long random JWT_SECRET before production."
        )


def validate_password_strength(password: str) -> None:
    """Raise HTTP 400 if password does not meet policy."""
    if len(password) < 8 or len(password) > 128:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be 8–128 characters",
        )
    if not re.search(r"[A-Za-z]", password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must include at least one letter",
        )
    if not re.search(r"\d", password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must include at least one number",
        )


def hash_password(password: str) -> str:
    raw = password.encode("utf-8")
    if len(raw) > 72:
        raw = raw[:72]
    return bcrypt.hashpw(raw, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: Optional[str]) -> bool:
    if not hashed:
        return False
    raw = plain.encode("utf-8")
    if len(raw) > 72:
        raw = raw[:72]
    try:
        return bcrypt.checkpw(raw, hashed.encode("utf-8"))
    except ValueError:
        return False


def verify_password_against_possible_user(plain: str, hashed: Optional[str]) -> bool:
    """
    Always run a bcrypt check to reduce user-enumeration timing leaks on login.
    """
    return verify_password(plain, hashed or _DUMMY_HASH)


def create_access_token(
    *,
    user_id: UUID,
    organization_id: UUID,
    role: str,
    email: str,
) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=app_config.JWT_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "org_id": str(organization_id),
        "role": role,
        "email": email,
        "iss": app_config.JWT_ISSUER,
        "aud": app_config.JWT_AUDIENCE,
        "typ": "access",
        "jti": secrets.token_urlsafe(16),
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, app_config.JWT_SECRET, algorithm=app_config.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    payload = jwt.decode(
        token,
        app_config.JWT_SECRET,
        algorithms=[app_config.JWT_ALGORITHM],
        audience=app_config.JWT_AUDIENCE,
        issuer=app_config.JWT_ISSUER,
        options={
            "require": ["exp", "iat", "sub", "org_id", "role", "typ"],
        },
    )
    if payload.get("typ") != "access":
        raise jwt.InvalidTokenError("Invalid token type")
    return payload


class AuthRateLimiter:
    """Simple in-memory sliding-window limiter (per process)."""

    def __init__(self, *, max_attempts: int, window_sec: int) -> None:
        self.max_attempts = max_attempts
        self.window_sec = window_sec
        self._hits: dict[str, Deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            bucket = self._hits[key]
            while bucket and now - bucket[0] > self.window_sec:
                bucket.popleft()
            if len(bucket) >= self.max_attempts:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many attempts. Try again in a few minutes.",
                    headers={"Retry-After": str(self.window_sec)},
                )
            bucket.append(now)


_login_limiter = AuthRateLimiter(max_attempts=10, window_sec=15 * 60)
_register_limiter = AuthRateLimiter(max_attempts=5, window_sec=60 * 60)


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def enforce_login_rate_limit(request: Request, email: str) -> None:
    ip = client_ip(request)
    _login_limiter.check(f"login:ip:{ip}")
    _login_limiter.check(f"login:email:{email.lower()}")


def enforce_register_rate_limit(request: Request) -> None:
    ip = client_ip(request)
    _register_limiter.check(f"register:ip:{ip}")
