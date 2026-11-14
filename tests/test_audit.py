"""
Tests for audit event logging.

Covers:
- Login success creates audit event
- Login failure creates audit event
- Appointment create creates audit event
- Appointment conflict creates audit event
- Appointment cancel creates audit event
"""

from __future__ import annotations

from app.models import AuditEvent
from tests.conftest import _auth_header, _login, _next_weekday_slot_offset


def test_audit_login_success(client, seed_data, db_session):
    """Successful login creates an audit event with action='login'."""
    client.post(
        "/auth/login",
        json={"email": "testpatient01@test.local", "password": seed_data["password"]},
    )
    events = db_session.query(AuditEvent).filter(AuditEvent.action == "login").all()
    assert len(events) >= 1
    assert events[-1].actor_role == "patient"


def test_audit_login_failed(client, seed_data, db_session):
    """Failed login creates an audit event with action='login_failed'."""
    client.post(
        "/auth/login",
        json={"email": "testpatient01@test.local", "password": "wrong"},
    )
    events = db_session.query(AuditEvent).filter(AuditEvent.action == "login_failed").all()
    assert len(events) >= 1


def test_audit_appointment_create(client, seed_data, db_session):
    """Creating an appointment creates an audit event."""
    token = _login(client, "testpatient01@test.local", seed_data["password"])
    slot = _next_weekday_slot_offset(days=10, hour=10, minute=0)
    client.post(
        "/appointments",
        json={
            "doctor_id": str(seed_data["doctor"].id),
            "slot_start": slot,
            "reason": "audit test",
        },
        headers=_auth_header(token),
    )
    events = db_session.query(AuditEvent).filter(AuditEvent.action == "appointment.create").all()
    assert len(events) >= 1
    assert events[-1].entity_type == "appointment"


def test_audit_appointment_conflict(client, seed_data, db_session):
    """Double-booking attempt creates a conflict audit event."""
    token = _login(client, "testpatient01@test.local", seed_data["password"])
    slot = _next_weekday_slot_offset(days=11, hour=10, minute=0)
    doctor_id = str(seed_data["doctor"].id)

    # First booking
    client.post(
        "/appointments",
        json={"doctor_id": doctor_id, "slot_start": slot, "reason": "first"},
        headers=_auth_header(token),
    )
    # Second booking (conflict)
    client.post(
        "/appointments",
        json={"doctor_id": doctor_id, "slot_start": slot, "reason": "second"},
        headers=_auth_header(token),
    )

    events = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.action == "appointment.create_conflict")
        .all()
    )
    assert len(events) >= 1


def test_audit_appointment_cancel(client, seed_data, db_session):
    """Cancelling an appointment creates an audit event."""
    token = _login(client, "testpatient01@test.local", seed_data["password"])
    slot = _next_weekday_slot_offset(days=12, hour=10, minute=0)

    create_resp = client.post(
        "/appointments",
        json={
            "doctor_id": str(seed_data["doctor"].id),
            "slot_start": slot,
            "reason": "will cancel",
        },
        headers=_auth_header(token),
    )
    appt_id = create_resp.json()["id"]

    client.post(f"/appointments/{appt_id}/cancel", headers=_auth_header(token))

    events = db_session.query(AuditEvent).filter(AuditEvent.action == "appointment.cancel").all()
    assert len(events) >= 1
