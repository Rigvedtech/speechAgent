"""Create tenant orgs. Public signup is closed; only platform admins call this."""

from __future__ import annotations

import logging
import re

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth.security import hash_password
from db.models import Organization, User

logger = logging.getLogger(__name__)


def slugify_org_name(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug[:100] or "org"


def create_organization_with_admin(
    db: Session,
    *,
    organization_name: str,
    organization_slug: str | None,
    full_name: str,
    email: str,
    password: str,
) -> tuple[Organization, User]:
    slug = organization_slug.strip().lower() if organization_slug else slugify_org_name(
        organization_name
    )
    if slug in ("rigved-platform",):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This organization slug is reserved",
        )
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="organization_slug must be lowercase letters, numbers, and hyphens",
        )

    email_norm = email.lower().strip()
    existing_email = db.scalar(select(User).where(User.email == email_norm))
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    existing_slug = db.scalar(select(Organization).where(Organization.slug == slug))
    if existing_slug:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Organization slug '{slug}' is already taken",
        )

    org = Organization(name=organization_name.strip(), slug=slug)
    user = User(
        organization=org,
        full_name=full_name.strip(),
        email=email_norm,
        password_hash=hash_password(password),
        role="admin",
        auth_provider="password",
        last_login_at=None,
    )
    db.add(org)
    db.add(user)
    try:
        db.flush()
    except IntegrityError as ex:
        db.rollback()
        logger.warning("[auth] provision conflict: %s", ex)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization or email already exists",
        ) from ex
    return org, user
