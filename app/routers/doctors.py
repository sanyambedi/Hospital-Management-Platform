"""
Doctor listing and slot availability endpoints.

WHY compute slots server-side: the client doesn't need to know business
rules (working hours, slot duration, timezone).  The server is the
single source of truth for what slots exist and which are free.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Appointment, Doctor
from app.schemas import DoctorOut, SlotOut
from app.security import get_current_user

router = APIRouter(prefix="/doctors", tags=["doctors"])


@router.get("", response_model=list[DoctorOut])
def list_doctors(
    _current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all doctors.  Any authenticated role can access this."""
    return db.query(Doctor).order_by(Doctor.display_name).all()


@router.get("/{doctor_id}/slots", response_model=list[SlotOut])
def get_available_slots(
    doctor_id: uuid.UUID,
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD"),
    _current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get free 30-minute slots for a doctor on a given date.

    WHY exclude confirmed appointments: shows only bookable slots.
    WHY timezone-aware: all comparisons use the configured clinic timezone.
    """
    # Verify doctor exists
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")

    tz = ZoneInfo(settings.timezone)
    try:
        query_date = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=tz)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid date format, use YYYY-MM-DD",
        )

    # Weekday check (0=Monday, 6=Sunday)
    if query_date.weekday() >= 5:
        return []  # No slots on weekends

    # Parse working hours
    work_start_h, work_start_m = map(int, settings.work_start.split(":"))
    work_end_h, work_end_m = map(int, settings.work_end.split(":"))

    # Generate all possible slots for the day
    slot_duration = timedelta(minutes=settings.slot_minutes)
    current = query_date.replace(hour=work_start_h, minute=work_start_m, second=0, microsecond=0)
    day_end = query_date.replace(hour=work_end_h, minute=work_end_m, second=0, microsecond=0)

    all_slots = []
    while current + slot_duration <= day_end:
        all_slots.append(current)
        current += slot_duration

    # Get confirmed appointments for this doctor on this date
    confirmed = (
        db.query(Appointment.slot_start)
        .filter(
            Appointment.doctor_id == doctor_id,
            Appointment.status == "confirmed",
            Appointment.slot_start >= query_date.replace(hour=0, minute=0),
            Appointment.slot_start < query_date + timedelta(days=1),
        )
        .all()
    )
    booked_starts = {row.slot_start for row in confirmed}

    # Return only free slots
    now = datetime.now(tz)
    free_slots = [
        SlotOut(slot_start=s, slot_end=s + slot_duration)
        for s in all_slots
        if s not in booked_starts and s > now  # exclude past slots
    ]
    return free_slots
