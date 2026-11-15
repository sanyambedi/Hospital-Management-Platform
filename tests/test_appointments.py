"""
Tests for appointment CRUD and business rule validation.

Covers:
- Create appointment → 201
- Unknown doctor → 404
- Past time → 422
- Off-grid time → 422
- Outside working hours → 422
- Weekend → 422
- Reschedule → 200
- Reschedule into occupied slot → 409
- Cancel frees slot (rebook succeeds)
- Client cannot spoof patient_id
"""

from __future__ import annotations

from datetime import datetime

from tests.conftest import _auth_header, _login, _next_weekday_slot, _next_weekday_slot_offset


def test_create_appointment_ok(client, seed_data):
    """Valid appointment creation returns 201."""
    token = _login(client, "testpatient01@test.local", seed_data["password"])
    slot = _next_weekday_slot()
    resp = client.post(
        "/appointments",
        json={
            "doctor_id": str(seed_data["doctor"].id),
            "slot_start": slot,
            "reason": "Synthetic checkup",
        },
        headers=_auth_header(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "confirmed"
    assert data["doctor_id"] == str(seed_data["doctor"].id)
    assert data["patient_id"] == str(seed_data["patient1"].id)


def test_unknown_doctor_404(client, seed_data):
    """Booking with a non-existent doctor_id returns 404."""
    token = _login(client, "testpatient01@test.local", seed_data["password"])
    slot = _next_weekday_slot()
    resp = client.post(
        "/appointments",
        json={
            "doctor_id": "00000000-0000-0000-0000-000000000000",
            "slot_start": slot,
            "reason": "test",
        },
        headers=_auth_header(token),
    )
    assert resp.status_code == 404


def test_past_time_422(client, seed_data):
    """Booking in the past returns 422."""
    token = _login(client, "testpatient01@test.local", seed_data["password"])
    resp = client.post(
        "/appointments",
        json={
            "doctor_id": str(seed_data["doctor"].id),
            "slot_start": "2020-01-06T10:00:00+05:30",  # Monday in the past
            "reason": "test",
        },
        headers=_auth_header(token),
    )
    assert resp.status_code == 422


def test_off_grid_time_422(client, seed_data):
    """Booking at :15 (not on the 30-min grid) returns 422."""
    token = _login(client, "testpatient01@test.local", seed_data["password"])
    slot = _next_weekday_slot_offset(days=2, hour=10, minute=15)
    resp = client.post(
        "/appointments",
        json={
            "doctor_id": str(seed_data["doctor"].id),
            "slot_start": slot,
            "reason": "test",
        },
        headers=_auth_header(token),
    )
    assert resp.status_code == 422


def test_outside_working_hours_422(client, seed_data):
    """Booking at 07:00 (before work_start 09:00) returns 422."""
    token = _login(client, "testpatient01@test.local", seed_data["password"])
    slot = _next_weekday_slot_offset(days=2, hour=7, minute=0)
    resp = client.post(
        "/appointments",
        json={
            "doctor_id": str(seed_data["doctor"].id),
            "slot_start": slot,
            "reason": "test",
        },
        headers=_auth_header(token),
    )
    assert resp.status_code == 422


def test_weekend_422(client, seed_data):
    """Booking on a Saturday returns 422."""
    token = _login(client, "testpatient01@test.local", seed_data["password"])
    # Find next Saturday
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Asia/Kolkata")
    now = datetime.now(tz)
    days_until_saturday = (5 - now.weekday()) % 7
    if days_until_saturday == 0:
        days_until_saturday = 7
    saturday = now + timedelta(days=days_until_saturday)
    slot = saturday.replace(hour=10, minute=0, second=0, microsecond=0).isoformat()

    resp = client.post(
        "/appointments",
        json={
            "doctor_id": str(seed_data["doctor"].id),
            "slot_start": slot,
            "reason": "test",
        },
        headers=_auth_header(token),
    )
    assert resp.status_code == 422


def test_reschedule_ok(client, seed_data):
    """Rescheduling to a free slot succeeds."""
    token = _login(client, "testpatient01@test.local", seed_data["password"])
    slot1 = _next_weekday_slot_offset(days=2, hour=10, minute=0)
    slot2 = _next_weekday_slot_offset(days=2, hour=11, minute=0)

    # Create appointment at slot1
    create_resp = client.post(
        "/appointments",
        json={
            "doctor_id": str(seed_data["doctor"].id),
            "slot_start": slot1,
            "reason": "original",
        },
        headers=_auth_header(token),
    )
    assert create_resp.status_code == 201
    appt_id = create_resp.json()["id"]

    # Reschedule to slot2
    reschedule_resp = client.patch(
        f"/appointments/{appt_id}/reschedule",
        json={"slot_start": slot2},
        headers=_auth_header(token),
    )
    assert reschedule_resp.status_code == 200
    from zoneinfo import ZoneInfo

    resched_raw = reschedule_resp.json()["slot_start"]
    if resched_raw.endswith("Z"):
        resched_slot = datetime.fromisoformat(resched_raw.replace("Z", "+00:00"))
    else:
        resched_slot = datetime.fromisoformat(resched_raw)
        if resched_slot.tzinfo is None:
            resched_slot = resched_slot.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
    expected_slot = datetime.fromisoformat(slot2)
    assert resched_slot == expected_slot


def test_reschedule_into_occupied_slot_409(client, seed_data):
    """Rescheduling into an already-booked slot returns 409."""
    token = _login(client, "testpatient01@test.local", seed_data["password"])
    slot1 = _next_weekday_slot_offset(days=3, hour=10, minute=0)
    slot2 = _next_weekday_slot_offset(days=3, hour=11, minute=0)

    # Create appointment 1 at slot1
    client.post(
        "/appointments",
        json={
            "doctor_id": str(seed_data["doctor"].id),
            "slot_start": slot1,
            "reason": "appt1",
        },
        headers=_auth_header(token),
    )

    # Create appointment 2 at slot2
    create2 = client.post(
        "/appointments",
        json={
            "doctor_id": str(seed_data["doctor"].id),
            "slot_start": slot2,
            "reason": "appt2",
        },
        headers=_auth_header(token),
    )
    assert create2.status_code == 201
    appt2_id = create2.json()["id"]

    # Try to reschedule appt2 to slot1 (occupied)
    resp = client.patch(
        f"/appointments/{appt2_id}/reschedule",
        json={"slot_start": slot1},
        headers=_auth_header(token),
    )
    assert resp.status_code == 409


def test_cancel_frees_slot(client, seed_data):
    """Cancelling an appointment frees the slot for rebooking."""
    token = _login(client, "testpatient01@test.local", seed_data["password"])
    slot = _next_weekday_slot_offset(days=4, hour=14, minute=0)

    # Create appointment
    create_resp = client.post(
        "/appointments",
        json={
            "doctor_id": str(seed_data["doctor"].id),
            "slot_start": slot,
            "reason": "will cancel",
        },
        headers=_auth_header(token),
    )
    assert create_resp.status_code == 201
    appt_id = create_resp.json()["id"]

    # Cancel it
    cancel_resp = client.post(
        f"/appointments/{appt_id}/cancel",
        headers=_auth_header(token),
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"

    # Rebook the same slot — should succeed because cancel freed it
    rebook_resp = client.post(
        "/appointments",
        json={
            "doctor_id": str(seed_data["doctor"].id),
            "slot_start": slot,
            "reason": "rebooked after cancel",
        },
        headers=_auth_header(token),
    )
    assert rebook_resp.status_code == 201


def test_cancel_idempotent(client, seed_data):
    """Cancelling twice returns 200 (idempotent)."""
    token = _login(client, "testpatient01@test.local", seed_data["password"])
    slot = _next_weekday_slot_offset(days=5, hour=9, minute=30)

    create_resp = client.post(
        "/appointments",
        json={
            "doctor_id": str(seed_data["doctor"].id),
            "slot_start": slot,
            "reason": "test",
        },
        headers=_auth_header(token),
    )
    appt_id = create_resp.json()["id"]

    # Cancel once
    client.post(f"/appointments/{appt_id}/cancel", headers=_auth_header(token))
    # Cancel again — should be idempotent
    resp = client.post(f"/appointments/{appt_id}/cancel", headers=_auth_header(token))
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


def test_patient_cannot_spoof_patient_id(client, seed_data):
    """Patient role user cannot set patient_id in the request body.

    WHY: patient_id comes from the JWT token, not the body.
    Even if a patient sends another patient_id, it should be ignored.
    """
    token = _login(client, "testpatient01@test.local", seed_data["password"])
    slot = _next_weekday_slot_offset(days=6, hour=10, minute=0)

    # Patient 1 tries to book as Patient 2
    resp = client.post(
        "/appointments",
        json={
            "doctor_id": str(seed_data["doctor"].id),
            "slot_start": slot,
            "reason": "spoofed",
            "patient_id": str(seed_data["patient2"].id),  # trying to spoof
        },
        headers=_auth_header(token),
    )
    # Should still create for patient1 (body patient_id ignored for patient role)
    assert resp.status_code == 201
    assert resp.json()["patient_id"] == str(seed_data["patient1"].id)


def test_double_booking_returns_409(client, seed_data):
    """Booking the same doctor+slot twice returns 409.

    THE CORE CORRECTNESS TEST for the partial unique index.
    """
    token = _login(client, "testpatient01@test.local", seed_data["password"])
    slot = _next_weekday_slot_offset(days=7, hour=10, minute=0)

    # First booking succeeds
    resp1 = client.post(
        "/appointments",
        json={
            "doctor_id": str(seed_data["doctor"].id),
            "slot_start": slot,
            "reason": "first",
        },
        headers=_auth_header(token),
    )
    assert resp1.status_code == 201

    # Second booking at same doctor+slot should fail with 409
    resp2 = client.post(
        "/appointments",
        json={
            "doctor_id": str(seed_data["doctor"].id),
            "slot_start": slot,
            "reason": "second",
        },
        headers=_auth_header(token),
    )
    assert resp2.status_code == 409
    assert resp2.json()["detail"] == "slot_unavailable"
