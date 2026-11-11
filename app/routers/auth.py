"""
Authentication endpoints.

WHY form-based login returning JWT: simple stateless auth that works
with any HTTP client.  The JWT contains all claims needed for
authorization, avoiding a DB lookup on every request.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.audit import log_audit_event
from app.db import get_db
from app.models import User
from app.schemas import LoginRequest, TokenResponse
from app.security import create_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])
logger = structlog.get_logger()


@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Authenticate with email + password, receive a JWT.

    Audit: logs both success and failure (never logs the password).
    """
    request_id = request.headers.get("x-request-id", "unknown")
    user = db.query(User).filter(User.email == body.email).first()

    # WHY generic error for both "no user" and "wrong password":
    # prevents email enumeration attacks.
    if not user or not verify_password(body.password, user.password_hash):
        # Audit the failed login attempt
        log_audit_event(
            db,
            action="login_failed",
            actor_user_id=user.id if user else None,
            actor_role=user.role if user else None,
            entity_type="user",
            entity_id=str(user.id) if user else None,
            request_id=request_id,
            details={"email": body.email, "reason": "invalid_credentials"},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Create JWT with user claims
    token = create_token(
        sub=str(user.id),
        role=user.role,
        patient_id=str(user.patient_id) if user.patient_id else None,
        doctor_id=str(user.doctor_id) if user.doctor_id else None,
    )

    # Audit successful login
    log_audit_event(
        db,
        action="login",
        actor_user_id=user.id,
        actor_role=user.role,
        entity_type="user",
        entity_id=str(user.id),
        request_id=request_id,
        details={"email": body.email},
    )
    db.commit()

    from app.config import settings

    return TokenResponse(
        access_token=token,
        expires_in=settings.jwt_expiry_minutes * 60,
    )
