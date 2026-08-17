"""One-time set-password tokens. Raw token is never stored."""

from __future__ import annotations

import hmac
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

import config as app_config
from auth.security import hash_password, validate_password_strength
from db.models import PasswordSetupToken, User

logger = logging.getLogger(__name__)

INVALID_LINK = "This link is invalid or has expired."
_TOKEN_MIN_LEN = 20
_TOKEN_MAX_LEN = 128
_PURPOSE_INVITE = "invite"


def hash_setup_token(raw: str) -> str:
    key = (app_config.JWT_SECRET or "").encode("utf-8")
    return hmac.new(key, raw.encode("utf-8"), hashlib.sha256).hexdigest()


def public_frontend_origin() -> str:
    base = (app_config.FRONTEND_BASE_URL or "").strip().rstrip("/")
    if base:
        return base
    origins = app_config.CORS_ORIGINS or []
    first = (origins[0] or "").strip().rstrip("/") if origins else ""
    return first


def issue_invite_token(db: Session, user_id: UUID) -> str:
    """Invalidate unused invite tokens, store HMAC of a new raw token, return raw once."""
    now = datetime.now(timezone.utc)
    db.execute(
        update(PasswordSetupToken)
        .where(
            PasswordSetupToken.user_id == user_id,
            PasswordSetupToken.purpose == _PURPOSE_INVITE,
            PasswordSetupToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    raw = secrets.token_urlsafe(32)
    row = PasswordSetupToken(
        user_id=user_id,
        token_hash=hash_setup_token(raw),
        purpose=_PURPOSE_INVITE,
        expires_at=now + timedelta(hours=app_config.PASSWORD_SETUP_HOURS),
    )
    db.add(row)
    db.flush()
    logger.info("[auth] invite token issued user_id=%s", user_id)
    return raw


def _load_unused_token(db: Session, raw: str, *, for_update: bool) -> PasswordSetupToken | None:
    if not raw or len(raw) < _TOKEN_MIN_LEN or len(raw) > _TOKEN_MAX_LEN:
        return None
    token_hash = hash_setup_token(raw)
    stmt = select(PasswordSetupToken).where(PasswordSetupToken.token_hash == token_hash)
    if for_update:
        stmt = stmt.with_for_update()
    return db.scalar(stmt)


def _token_usable(row: PasswordSetupToken | None) -> bool:
    if row is None or row.used_at is not None:
        return False
    now = datetime.now(timezone.utc)
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return expires > now


def peek_invite_token(db: Session, raw: str) -> User:
    """Validate without consuming. Same error for every failure."""
    row = _load_unused_token(db, raw, for_update=False)
    if not _token_usable(row) or row is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=INVALID_LINK)
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=INVALID_LINK)
    return user


def consume_invite_token(db: Session, raw: str, password: str) -> User:
    row = _load_unused_token(db, raw, for_update=True)
    if not _token_usable(row) or row is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=INVALID_LINK)
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=INVALID_LINK)
    validate_password_strength(password)
    now = datetime.now(timezone.utc)
    user.password_hash = hash_password(password)
    row.used_at = now
    db.execute(
        update(PasswordSetupToken)
        .where(
            PasswordSetupToken.user_id == user.id,
            PasswordSetupToken.purpose == _PURPOSE_INVITE,
            PasswordSetupToken.used_at.is_(None),
            PasswordSetupToken.id != row.id,
        )
        .values(used_at=now)
    )
    db.commit()
    db.refresh(user)
    logger.info("[auth] password set via invite user_id=%s", user.id)
    return user
