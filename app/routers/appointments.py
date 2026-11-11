"""
Appointment CRUD endpoints with double-booking protection.

THE MOST IMPORTANT FILE in the project for correctness:
- Create and reschedule use DB transactions + catch IntegrityError on
  the partial unique index → 409.
- Cancel sets status='cancelled', freeing the slot for rebooking.
- Role-based filtering ensures patients see only their own data.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import log_audit_event
from app.config import settings
from app.db import get_db
from app.models import Appointment, Doctor, Patient
from app.schemas import AppointmentCreate, AppointmentOut, AppointmentReschedule
from app.security import get_current_user, require_roles

router = APIRouter(prefix="/appointments", tags=["appointments"])
logger = structlog.get_logger()


def _validate_slot_start(slot_start: datetime) -> datetime:
    """Validate slot_start against all business rules.

    WHY server-side validation: clients cannot be trusted.  Every rule
    is checked here; the DB index is the last line of defense.
    """
    tz = ZoneInfo(settings.timezone)

    # Must be timezone-aware
    if slot_start.tzinfo is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="slot_start must be timezone-aware (include UTC offset)",
        )

    # Convert to clinic timezone for business rule checks
    local_time = slot_start.astimezone(tz)

    # Must be aligned to the configured slot grid (e.g., 30-minute intervals)
    if local_time.minute % settings.slot_minutes != 0 or local_time.second != 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"slot_start must be aligned to {settings.slot_minutes}-minute grid",
        )

    # Must be a weekday (Mon=0 .. Sun=6)
    if local_time.weekday() >= 5:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Appointments only available on weekdays (Mon-Fri)",
        )

    # Must be within working hours
    work_start_h, work_start_m = map(int, settings.work_start.split(":"))
    work_end_h, work_end_m = map(int, settings.work_end.split(":"))
    work_start_time = local_time.replace(
        hour=work_start_h, minute=work_start_m, second=0, microsecond=0
    )
    work_end_time = local_time.replace(hour=work_end_h, minute=work_end_m, second=0, microsecond=0)
    slot_end_local = local_time + timedelta(minutes=settings.slot_minutes)

    if local_time < work_start_time or slot_end_local > work_end_time:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"slot_start must be within working hours "
            f"({settings.work_start}-{settings.work_end} {settings.timezone})",
        )

    # Must be in the future
    now = datetime.now(tz)
    if local_time <= now:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="slot_start must be in the future",
        )

    # Must be within 60 days
    max_future = now + timedelta(days=60)
    if local_time > max_future:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="slot_start must be within 60 days from now",
        )

    return slot_start


@router.post("", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
def create_appointment(
    body: AppointmentCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles("patient", "admin")),
):
    """Create an appointment.

    THE CRITICAL PATH for double-booking prevention:
    1. Validate slot_start against all business rules
    2. INSERT into appointments within a transaction
    3. If the partial unique index raises IntegrityError → 409 slot_unavailable
    4. Otherwise commit → 201
    """
    request_id = request.headers.get("x-request-id", "unknown")
    _validate_slot_start(body.slot_start)

    # Determine patient_id: from JWT for patients, from body for admins
    if current_user["role"] == "patient":
        patient_id_str = current_user.get("patient_id")
        if not patient_id_str:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Patient user has no linked patient record",
            )
        patient_id = uuid.UUID(patient_id_str)
    elif current_user["role"] == "admin":
        if body.patient_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Admin must specify patient_id",
            )
        patient_id = body.patient_id
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    # Verify doctor exists
    doctor = db.query(Doctor).filter(Doctor.id == body.doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")

    # Verify patient exists
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    # Compute slot_end server-side (client cannot send it)
    slot_end = body.slot_start + timedelta(minutes=settings.slot_minutes)

    appointment = Appointment(
        doctor_id=body.doctor_id,
        patient_id=patient_id,
        slot_start=body.slot_start,
        slot_end=slot_end,
        reason=body.reason,
        status="confirmed",
    )

    try:
        db.add(appointment)
        db.flush()  # WHY flush (not commit): triggers the unique index check within the txn
    except IntegrityError:
        db.rollback()
        # Audit the conflict attempt
        log_audit_event(
            db,
            action="appointment.create_conflict",
            actor_user_id=current_user["sub"],
            actor_role=current_user["role"],
            entity_type="appointment",
            request_id=request_id,
            details={
                "doctor_id": str(body.doctor_id),
                "slot_start": body.slot_start.isoformat(),
            },
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="slot_unavailable",
        )

    # Audit successful creation
    log_audit_event(
        db,
        action="appointment.create",
        actor_user_id=current_user["sub"],
        actor_role=current_user["role"],
        entity_type="appointment",
        entity_id=appointment.id,
        request_id=request_id,
        details={
            "doctor_id": str(body.doctor_id),
            "patient_id": str(patient_id),
            "slot_start": body.slot_start.isoformat(),
        },
    )
    db.commit()
    db.refresh(appointment)
    return appointment


@router.get("", response_model=list[AppointmentOut])
def list_appointments(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List appointments filtered by role.

    WHY role-based filtering: patients must never see another patient's data.
    """
    query = db.query(Appointment)

    if current_user["role"] == "patient":
        patient_id = current_user.get("patient_id")
        if not patient_id:
            return []
        query = query.filter(Appointment.patient_id == uuid.UUID(patient_id))
    elif current_user["role"] == "doctor":
        doctor_id = current_user.get("doctor_id")
        if not doctor_id:
            return []
        query = query.filter(Appointment.doctor_id == uuid.UUID(doctor_id))
    # admin sees all

    return query.order_by(Appointment.slot_start.desc()).all()


@router.get("/{appointment_id}", response_model=AppointmentOut)
def get_appointment(
    appointment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get a single appointment with role-based access control."""
    appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

    # Role-based access: patient sees only own, doctor sees own schedule
    if current_user["role"] == "patient":
        if str(appt.patient_id) != current_user.get("patient_id"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not your appointment",
            )
    elif current_user["role"] == "doctor":
        if str(appt.doctor_id) != current_user.get("doctor_id"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not your appointment",
            )
    # admin sees all
    return appt


@router.patch("/{appointment_id}/reschedule", response_model=AppointmentOut)
def reschedule_appointment(
    appointment_id: uuid.UUID,
    body: AppointmentReschedule,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles("patient", "admin")),
):
    """Reschedule: update slot_start/slot_end within one transaction.

    Same unique index protects against conflicts; 409 on collision.
    """
    request_id = request.headers.get("x-request-id", "unknown")
    _validate_slot_start(body.slot_start)

    appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

    # Only owner patient or admin can reschedule
    if current_user["role"] == "patient":
        if str(appt.patient_id) != current_user.get("patient_id"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Not your appointment"
            )

    if appt.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Cannot reschedule a cancelled appointment"
        )

    old_start = appt.slot_start.isoformat()
    slot_end = body.slot_start + timedelta(minutes=settings.slot_minutes)

    appt.slot_start = body.slot_start
    appt.slot_end = slot_end

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        log_audit_event(
            db,
            action="appointment.reschedule_conflict",
            actor_user_id=current_user["sub"],
            actor_role=current_user["role"],
            entity_type="appointment",
            entity_id=appointment_id,
            request_id=request_id,
            details={"new_slot_start": body.slot_start.isoformat()},
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="slot_unavailable")

    log_audit_event(
        db,
        action="appointment.reschedule",
        actor_user_id=current_user["sub"],
        actor_role=current_user["role"],
        entity_type="appointment",
        entity_id=appointment_id,
        request_id=request_id,
        details={
            "old_slot_start": old_start,
            "new_slot_start": body.slot_start.isoformat(),
        },
    )
    db.commit()
    db.refresh(appt)
    return appt


@router.post("/{appointment_id}/cancel", response_model=AppointmentOut)
def cancel_appointment(
    appointment_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles("patient", "admin")),
):
    """Cancel an appointment.  Idempotent: cancelling twice returns 200.

    WHY idempotent: avoids confusing error messages for retried requests
    (network hiccups, double-clicks).  No duplicate audit spam either.
    """
    request_id = request.headers.get("x-request-id", "unknown")

    appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

    # Only owner patient or admin can cancel
    if current_user["role"] == "patient":
        if str(appt.patient_id) != current_user.get("patient_id"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Not your appointment"
            )

    # Idempotent: if already cancelled, just return it (no duplicate audit)
    if appt.status == "cancelled":
        return appt

    appt.status = "cancelled"

    log_audit_event(
        db,
        action="appointment.cancel",
        actor_user_id=current_user["sub"],
        actor_role=current_user["role"],
        entity_type="appointment",
        entity_id=appointment_id,
        request_id=request_id,
    )
    db.commit()
    db.refresh(appt)
    return appt
