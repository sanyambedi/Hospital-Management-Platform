"""
Pydantic v2 schemas for request/response validation.

WHY separate from SQLAlchemy models: decouples API contract from DB schema.
Pydantic handles validation, serialization, and OpenAPI doc generation.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    """Credentials for POST /auth/login."""

    email: str = Field(..., examples=["patient01@synthetic.local"])
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    """JWT token returned on successful login."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Token lifetime in seconds")


# ---------------------------------------------------------------------------
# Doctors
# ---------------------------------------------------------------------------


class DoctorOut(BaseModel):
    """Doctor record returned by GET /doctors."""

    id: uuid.UUID
    display_name: str
    specialty: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SlotOut(BaseModel):
    """A single available time slot."""

    slot_start: datetime
    slot_end: datetime


# ---------------------------------------------------------------------------
# Appointments
# ---------------------------------------------------------------------------


class AppointmentCreate(BaseModel):
    """Body for POST /appointments."""

    doctor_id: uuid.UUID
    slot_start: datetime  # must be timezone-aware, aligned to 30-min grid
    reason: str = Field(default="", max_length=500)
    # patient_id is NEVER accepted from the body for patient role (taken from JWT)
    patient_id: uuid.UUID | None = Field(
        default=None,
        description="Only admin may specify; patients use their own ID from JWT",
    )


class AppointmentReschedule(BaseModel):
    """Body for PATCH /appointments/{id}/reschedule."""

    slot_start: datetime  # new slot start; same validations apply


class AppointmentOut(BaseModel):
    """Appointment record returned by the API."""

    id: uuid.UUID
    doctor_id: uuid.UUID
    patient_id: uuid.UUID
    slot_start: datetime
    slot_end: datetime
    status: str
    reason: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """Response for GET /healthz."""

    status: str = "ok"


class ReadyCheck(BaseModel):
    """Individual readiness check result."""

    db: str = "ok"
    migrations: str = "ok"


class ReadyResponse(BaseModel):
    """Response for GET /readyz."""

    status: str = "ready"
    checks: ReadyCheck = ReadyCheck()


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ErrorResponse(BaseModel):
    """Standard error response body."""

    error: str
    detail: str | None = None
    request_id: str | None = None
