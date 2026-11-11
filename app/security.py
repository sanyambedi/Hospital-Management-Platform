"""
Password hashing, JWT creation/verification, and role-based access dependencies.

WHY argon2: winner of the Password Hashing Competition, resistant to GPU
and ASIC attacks. Better than bcrypt for new projects.

WHY HS256 JWT: simple symmetric signing; appropriate when the API server
is both issuer and verifier.  For microservices, RS256 would be better.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import structlog
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

logger = structlog.get_logger()

# WHY module-level instance: PasswordHasher is stateless and thread-safe
_ph = PasswordHasher()

# WHY HTTPBearer: extracts "Bearer <token>" from Authorization header
_bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    """Hash a plaintext password using argon2id."""
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its argon2 hash.  Returns False on mismatch."""
    try:
        return _ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------


def create_token(
    sub: str,
    role: str,
    patient_id: str | None = None,
    doctor_id: str | None = None,
) -> str:
    """Create a signed JWT with user claims.

    WHY claims include patient_id/doctor_id: the API needs to know which
    patient/doctor record the user represents for authorization, without
    an extra DB lookup on every request.
    """
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": sub,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expiry_minutes),
        "jti": str(uuid.uuid4()),  # unique token ID for audit trails
    }
    if patient_id:
        payload["patient_id"] = patient_id
    if doctor_id:
        payload["doctor_id"] = doctor_id
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict:
    """Decode and validate a JWT.  Raises HTTPException on failure."""
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict:
    """Dependency: extract and validate JWT from the Authorization header.

    Returns the decoded claims dict with keys: sub, role, patient_id, doctor_id.
    Raises 401 if the token is missing or invalid.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
        )
    claims = decode_token(credentials.credentials)

    # Bind user_id to structlog context so all downstream logs include it
    structlog.contextvars.bind_contextvars(user_id=claims.get("sub"))

    return claims


def require_roles(*allowed_roles: str):
    """Dependency factory: restrict access to specific roles.

    Usage in a route:
        current_user: dict = Depends(require_roles("patient", "admin"))

    WHY factory pattern: lets each endpoint declare its allowed roles
    declaratively; the check is reusable and testable.
    """

    async def _role_checker(
        current_user: dict = Depends(get_current_user),
    ) -> dict:
        if current_user.get("role") not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.get('role')}' not allowed. "
                f"Required: {', '.join(allowed_roles)}",
            )
        return current_user

    return _role_checker
