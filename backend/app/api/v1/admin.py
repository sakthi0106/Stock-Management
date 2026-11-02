"""
Administrator Management Endpoints
User administration, role assignments, audit logs.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.session import get_db
from app.models.models import User, AuditLog
from app.schemas.schemas import UserResponse, UserCreate, AuditLogResponse
from app.core.security import require_roles, hash_password, UserRole, normalize_role

router = APIRouter(prefix="/admin", tags=["Administration"])

@router.get("/users", response_model=List[UserResponse])
def list_users(
    current_user: dict = Depends(require_roles([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    return db.query(User).order_by(User.id).all()

@router.post("/users", response_model=UserResponse)
def create_user(
    payload: UserCreate,
    current_user: dict = Depends(require_roles([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    existing = db.query(User).filter(User.email == payload.email.lower()).first()
    if existing:
        raise HTTPException(status_code=400, detail="User with this email already exists.")

    normalized_role = normalize_role(payload.role)
    if not normalized_role:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of {UserRole.ALL}")

    user = User(
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=normalized_role,
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    audit = AuditLog(
        user_id=int(current_user["sub"]),
        user_email=current_user.get("email"),
        action="CREATE_USER",
        resource_type="USER",
        resource_id=str(user.id),
        details=f"Created user {user.email} with role {user.role}"
    )
    db.add(audit)
    db.commit()

    return user

@router.put("/users/{user_id}/status", response_model=UserResponse)
def toggle_user_status(
    user_id: int,
    is_active: bool,
    current_user: dict = Depends(require_roles([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    if user_id == int(current_user["sub"]) and not is_active:
        raise HTTPException(status_code=400, detail="Administrators cannot deactivate their own account.")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    user.is_active = is_active
    db.commit()

    audit = AuditLog(
        user_id=int(current_user["sub"]),
        user_email=current_user.get("email"),
        action="UPDATE_USER_STATUS",
        resource_type="USER",
        resource_id=str(user.id),
        details=f"Updated active status to {is_active}"
    )
    db.add(audit)
    db.commit()

    return user

@router.get("/audit-logs", response_model=List[AuditLogResponse])
def get_audit_logs(
    action: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(require_roles([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    return query.order_by(desc(AuditLog.created_at)).limit(limit).all()
