"""Auth + user management HTTP routes (Phase 0)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth.deps import get_current_user, get_db, is_platform_admin_user, require_admin
from auth.schemas import (
    AuthResponse,
    CreateUserRequest,
    LoginRequest,
    MeResponse,
    OrganizationOut,
    UpdateUserRequest,
    UserOut,
)
from auth.security import (
    create_access_token,
    enforce_login_rate_limit,
    hash_password,
    validate_password_strength,
    verify_password_against_possible_user,
)
from db.models import Organization, User
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])
users_router = APIRouter(prefix="/api/users", tags=["users"])


def _auth_response(user: User, org: Organization) -> AuthResponse:
    token = create_access_token(
        user_id=user.id,
        organization_id=user.organization_id,
        role=user.role,
        email=user.email,
    )
    return AuthResponse(
        access_token=token,
        user=UserOut.model_validate(user),
        organization=OrganizationOut.model_validate(org),
        is_platform_admin=is_platform_admin_user(user),
    )


@router.post("/register-org", status_code=status.HTTP_403_FORBIDDEN)
def register_organization():
    """Public self-serve signup is closed. Use /request-access; platform admins grant login."""
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Public organization registration is closed. Request access and wait for approval.",
    )


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    enforce_login_rate_limit(request, body.email)
    user = db.scalar(select(User).where(User.email == body.email))
    password_ok = verify_password_against_possible_user(
        body.password, user.password_hash if user else None
    )
    if user is None or not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    org = db.get(Organization, user.organization_id)
    if org is None or not org.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization is inactive",
        )

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return _auth_response(user, org)

@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = db.get(Organization, user.organization_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return MeResponse(
        user=UserOut.model_validate(user),
        organization=OrganizationOut.model_validate(org),
        is_platform_admin=is_platform_admin_user(user),
    )


@users_router.get("", response_model=List[UserOut])
def list_users(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        select(User)
        .where(User.organization_id == admin.organization_id)
        .order_by(User.created_at.asc())
    ).all()
    return [UserOut.model_validate(u) for u in rows]


@users_router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: CreateUserRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin adds recruiter / viewer / admin in the same organization."""
    validate_password_strength(body.password)
    existing = db.scalar(select(User).where(User.email == body.email))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        organization_id=admin.organization_id,
        full_name=body.full_name,
        email=body.email,
        password_hash=hash_password(body.password),
        role=body.role,
        auth_provider="password",
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as ex:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        ) from ex

    db.refresh(user)
    logger.info(
        "[auth] User created email=%s role=%s by=%s",
        user.email,
        user.role,
        admin.email,
    )
    return UserOut.model_validate(user)


@users_router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: UUID,
    body: UpdateUserRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None or user.organization_id != admin.organization_id:
        raise HTTPException(status_code=404, detail="User not found")

    if body.full_name is not None:
        user.full_name = body.full_name
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        if user.id == admin.id and body.is_active is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate your own account",
            )
        user.is_active = body.is_active
    if body.password is not None:
        validate_password_strength(body.password)
        user.password_hash = hash_password(body.password)

    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)

@users_router.delete("/{user_id}", response_model=UserOut)
def deactivate_user(
    user_id: UUID,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Soft-deactivate a user (is_active=false)."""
    user = db.get(User, user_id)
    if user is None or user.organization_id != admin.organization_id:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate your own account",
        )
    user.is_active = False
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)
