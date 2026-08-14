"""Platform operator APIs: all organizations and their users."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth.deps import get_db, require_platform_admin
from auth.provisioning import create_organization_with_admin
from auth.schemas import TenantUserRole, UserOut
from auth.security import hash_password, validate_password_strength, verify_password
from db.models import AccessRequest, InterviewSession, Organization, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["platform-admin"])

TENANT_ROLES = ("admin", "recruiter", "viewer")


class AdminOrganizationOut(BaseModel):
    id: UUID
    name: str
    slug: str
    is_active: bool
    is_platform: bool
    created_at: datetime
    user_count: int

    model_config = {"from_attributes": True}


class AdminOrganizationDetailOut(BaseModel):
    organization: AdminOrganizationOut
    users: List[UserOut]


class PatchOrganizationRequest(BaseModel):
    is_active: Optional[bool] = None
    name: Optional[str] = Field(None, min_length=2, max_length=255)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if v else v


class AdminCreateUserRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    role: TenantUserRole = "recruiter"

    @field_validator("email")
    @classmethod
    def email_lower(cls, v: str) -> str:
        return v.lower().strip()

    @field_validator("full_name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()


class AdminPatchUserRequest(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=255)
    role: Optional[TenantUserRole] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=8, max_length=128)

    @field_validator("full_name")
    @classmethod
    def strip_name(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if v else v


def _org_out(org: Organization, user_count: int) -> AdminOrganizationOut:
    return AdminOrganizationOut(
        id=org.id,
        name=org.name,
        slug=org.slug,
        is_active=org.is_active,
        is_platform=bool(org.is_platform),
        created_at=org.created_at,
        user_count=user_count,
    )


def _user_count(db: Session, org_id: UUID) -> int:
    return int(db.scalar(select(func.count()).select_from(User).where(User.organization_id == org_id)) or 0)


@router.get("/organizations", response_model=List[AdminOrganizationOut])
def list_organizations(
    admin: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    del admin
    rows = db.execute(
        select(Organization, func.count(User.id))
        .outerjoin(User, User.organization_id == Organization.id)
        .group_by(Organization.id)
        .order_by(Organization.created_at.desc())
    ).all()
    return [_org_out(org, int(count or 0)) for org, count in rows]


@router.get("/organizations/{org_id}", response_model=AdminOrganizationDetailOut)
def get_organization(
    org_id: UUID,
    admin: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    del admin
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    users = db.scalars(
        select(User).where(User.organization_id == org.id).order_by(User.created_at.asc())
    ).all()
    return AdminOrganizationDetailOut(
        organization=_org_out(org, len(users)),
        users=[UserOut.model_validate(u) for u in users],
    )


@router.patch("/organizations/{org_id}", response_model=AdminOrganizationOut)
def patch_organization(
    org_id: UUID,
    body: PatchOrganizationRequest,
    admin: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    if org.is_platform and body.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate the platform organization",
        )
    if body.name is not None:
        org.name = body.name
    if body.is_active is not None:
        org.is_active = body.is_active
    db.commit()
    db.refresh(org)
    logger.info("[admin] org %s updated by %s", org.slug, admin.email)
    return _org_out(org, _user_count(db, org.id))


@router.post(
    "/organizations/{org_id}/users",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
)
def create_org_user(
    org_id: UUID,
    body: AdminCreateUserRequest,
    admin: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    if org.is_platform:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Platform operators are managed under Operators",
        )
    if body.role not in TENANT_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    validate_password_strength(body.password)
    existing = db.scalar(select(User).where(User.email == body.email))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = User(
        organization_id=org.id,
        full_name=body.full_name,
        email=body.email,
        password_hash=hash_password(body.password),
        role=body.role,
        auth_provider="password",
        is_active=True,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as ex:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email already registered") from ex
    db.refresh(user)
    logger.info("[admin] user %s created in %s by %s", user.email, org.slug, admin.email)
    return UserOut.model_validate(user)


@router.patch("/users/{user_id}", response_model=UserOut)
def patch_org_user(
    user_id: UUID,
    body: AdminPatchUserRequest,
    admin: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == "platform_admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Platform operator accounts are managed under Operators",
        )
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot edit your own operator account here")
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.password is not None:
        validate_password_strength(body.password)
        user.password_hash = hash_password(body.password)
    db.commit()
    db.refresh(user)
    logger.info("[admin] user %s updated by %s", user.email, admin.email)
    return UserOut.model_validate(user)


class AdminOverviewOut(BaseModel):
    pending_requests: int
    customer_orgs: int
    active_orgs: int
    inactive_orgs: int
    tenant_users: int
    operators: int
    interviews_this_month: int
    requests_by_status: dict[str, int]
    users_by_role: dict[str, int]
    interviews_by_month: list[dict[str, str | int]]


class CreateOrganizationRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    admin_full_name: str = Field(..., min_length=2, max_length=255)
    admin_email: EmailStr
    admin_password: str = Field(..., min_length=8, max_length=128)
    organization_slug: Optional[str] = Field(None, max_length=100)

    @field_validator("admin_email")
    @classmethod
    def email_lower(cls, v: str) -> str:
        return v.lower().strip()

    @field_validator("name", "admin_full_name")
    @classmethod
    def strip_text(cls, v: str) -> str:
        return v.strip()


class CreateOrganizationResult(BaseModel):
    organization: AdminOrganizationOut
    login_email: str


class CreateOperatorRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def email_lower(cls, v: str) -> str:
        return v.lower().strip()

    @field_validator("full_name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()


class PatchOperatorRequest(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=255)
    is_active: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=8, max_length=128)

    @field_validator("full_name")
    @classmethod
    def strip_name(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if v else v


class ChangeOwnPasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)


def _platform_org(db: Session) -> Organization:
    org = db.scalar(select(Organization).where(Organization.is_platform.is_(True)))
    if org is None:
        raise HTTPException(status_code=500, detail="Platform organization is missing")
    return org


def _active_operator_count(db: Session) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == "platform_admin", User.is_active.is_(True))
        )
        or 0
    )


@router.get("/overview", response_model=AdminOverviewOut)
def admin_overview(
    admin: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    del admin
    pending_requests = int(
        db.scalar(
            select(func.count())
            .select_from(AccessRequest)
            .where(AccessRequest.status == "pending")
        )
        or 0
    )
    customer_orgs = int(
        db.scalar(
            select(func.count()).select_from(Organization).where(Organization.is_platform.is_(False))
        )
        or 0
    )
    active_orgs = int(
        db.scalar(
            select(func.count())
            .select_from(Organization)
            .where(Organization.is_platform.is_(False), Organization.is_active.is_(True))
        )
        or 0
    )
    tenant_users = int(
        db.scalar(
            select(func.count()).select_from(User).where(User.role != "platform_admin")
        )
        or 0
    )
    operators = _active_operator_count(db)
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    interviews_this_month = int(
        db.scalar(
            select(func.count())
            .select_from(InterviewSession)
            .where(InterviewSession.created_at >= month_start)
        )
        or 0
    )

    request_rows = db.execute(
        select(AccessRequest.status, func.count()).group_by(AccessRequest.status)
    ).all()
    requests_by_status = {"pending": 0, "granted": 0, "rejected": 0}
    for status_name, count in request_rows:
        if status_name in requests_by_status:
            requests_by_status[status_name] = int(count or 0)

    role_rows = db.execute(
        select(User.role, func.count())
        .where(User.role != "platform_admin")
        .group_by(User.role)
    ).all()
    users_by_role = {"admin": 0, "recruiter": 0, "viewer": 0}
    for role_name, count in role_rows:
        if role_name in users_by_role:
            users_by_role[role_name] = int(count or 0)

    month_keys: list[datetime] = []
    y, m = month_start.year, month_start.month
    for _ in range(6):
        month_keys.append(datetime(y, m, 1, tzinfo=timezone.utc))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    month_keys.reverse()

    interview_month = func.date_trunc("month", InterviewSession.created_at)
    interview_rows = db.execute(
        select(interview_month, func.count()).group_by(interview_month)
    ).all()
    by_month: dict[str, int] = {}
    for month_val, count in interview_rows:
        if month_val is None:
            continue
        if getattr(month_val, "tzinfo", None) is None:
            month_val = month_val.replace(tzinfo=timezone.utc)
        key = month_val.astimezone(timezone.utc).strftime("%Y-%m")
        by_month[key] = int(count or 0)

    interviews_by_month = [
        {
            "month": dt.strftime("%Y-%m"),
            "label": dt.strftime("%b"),
            "count": by_month.get(dt.strftime("%Y-%m"), 0),
        }
        for dt in month_keys
    ]

    return AdminOverviewOut(
        pending_requests=pending_requests,
        customer_orgs=customer_orgs,
        active_orgs=active_orgs,
        inactive_orgs=max(0, customer_orgs - active_orgs),
        tenant_users=tenant_users,
        operators=operators,
        interviews_this_month=interviews_this_month,
        requests_by_status=requests_by_status,
        users_by_role=users_by_role,
        interviews_by_month=interviews_by_month,
    )


@router.post("/organizations", response_model=CreateOrganizationResult, status_code=status.HTTP_201_CREATED)
def create_organization(
    body: CreateOrganizationRequest,
    admin: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    validate_password_strength(body.admin_password)
    org, user = create_organization_with_admin(
        db,
        organization_name=body.name,
        organization_slug=body.organization_slug,
        full_name=body.admin_full_name,
        email=body.admin_email,
        password=body.admin_password,
    )
    db.commit()
    db.refresh(org)
    logger.info("[admin] org %s created by %s", org.slug, admin.email)
    return CreateOrganizationResult(
        organization=_org_out(org, 1),
        login_email=user.email,
    )


@router.get("/operators", response_model=List[UserOut])
def list_operators(
    admin: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    del admin
    rows = db.scalars(
        select(User).where(User.role == "platform_admin").order_by(User.created_at.asc())
    ).all()
    return [UserOut.model_validate(u) for u in rows]


@router.post("/operators", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_operator(
    body: CreateOperatorRequest,
    admin: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    validate_password_strength(body.password)
    existing = db.scalar(select(User).where(User.email == body.email))
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    org = _platform_org(db)
    user = User(
        organization_id=org.id,
        full_name=body.full_name,
        email=body.email,
        password_hash=hash_password(body.password),
        role="platform_admin",
        auth_provider="password",
        is_active=True,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as ex:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email already registered") from ex
    db.refresh(user)
    logger.info("[admin] operator %s created by %s", user.email, admin.email)
    return UserOut.model_validate(user)


@router.patch("/operators/{user_id}", response_model=UserOut)
def patch_operator(
    user_id: UUID,
    body: PatchOperatorRequest,
    admin: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None or user.role != "platform_admin":
        raise HTTPException(status_code=404, detail="Operator not found")
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.password is not None:
        validate_password_strength(body.password)
        user.password_hash = hash_password(body.password)
    if body.is_active is False:
        if user.id == admin.id:
            raise HTTPException(status_code=400, detail="Cannot deactivate your own operator account")
        if _active_operator_count(db) <= 1:
            raise HTTPException(status_code=400, detail="Cannot deactivate the last operator")
        user.is_active = False
    elif body.is_active is True:
        user.is_active = True
    db.commit()
    db.refresh(user)
    logger.info("[admin] operator %s updated by %s", user.email, admin.email)
    return UserOut.model_validate(user)


@router.post("/me/password")
def change_own_password(
    body: ChangeOwnPasswordRequest,
    admin: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    if not verify_password(body.current_password, admin.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    validate_password_strength(body.new_password)
    admin.password_hash = hash_password(body.new_password)
    db.commit()
    logger.info("[admin] operator %s changed own password", admin.email)
    return {"ok": True}
