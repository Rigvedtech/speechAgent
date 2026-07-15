"""Encrypt / decrypt per-org ATS API keys (Fernet)."""

from __future__ import annotations

import base64
import hashlib
import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

import config as app_config

logger = logging.getLogger(__name__)


def _fernet() -> Fernet:
    """
    Build Fernet from ATS_SECRET_ENCRYPTION_KEY.
    Accepts a raw Fernet key, or any passphrase (SHA-256 → urlsafe key).
    Falls back to JWT_SECRET in development only.
    """
    raw = (app_config.ATS_SECRET_ENCRYPTION_KEY or "").strip()
    if not raw:
        raw = (app_config.JWT_SECRET or "").strip()
        if app_config.APP_ENV == "production":
            raise RuntimeError(
                "ATS_SECRET_ENCRYPTION_KEY must be set in production to store ATS API keys"
            )
        logger.warning(
            "[ats] ATS_SECRET_ENCRYPTION_KEY unset — deriving from JWT_SECRET (dev only)"
        )
    if not raw:
        raise RuntimeError("No encryption key available for ATS API keys")

    # Valid Fernet keys are 44-char url-safe base64 (32 bytes)
    try:
        if len(raw) == 44:
            return Fernet(raw.encode("utf-8"))
    except Exception:
        pass

    derived = base64.urlsafe_b64encode(hashlib.sha256(raw.encode("utf-8")).digest())
    return Fernet(derived)


def encrypt_api_key(plaintext: str) -> str:
    text = (plaintext or "").strip()
    if not text:
        raise ValueError("API key is empty")
    token = _fernet().encrypt(text.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_api_key(ciphertext: Optional[str]) -> str:
    if not ciphertext or not str(ciphertext).strip():
        return ""
    try:
        return _fernet().decrypt(str(ciphertext).strip().encode("utf-8")).decode("utf-8")
    except InvalidToken as ex:
        logger.error("[ats] Failed to decrypt ATS API key (wrong master key?)")
        raise ValueError(
            "Could not decrypt ATS API key. Check ATS_SECRET_ENCRYPTION_KEY."
        ) from ex
