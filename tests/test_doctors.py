"""
Tests for doctor listing and slot availability endpoints.

Covers:
- GET /doctors returns list of doctors (authenticated)
- GET /doctors/{id}/slots returns available free slots
- GET /doctors/{id}/slots on weekend returns empty list
- GET /doctors/{id}/slots for unknown doctor returns 404
- GET /doctors/{id}/slots with invalid date returns 422
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from tests.conftest import _auth_header, _login


def test_list_doctors_authenticated(client, seed_data):
    """Authenticated user can list all doctors."""
    token = _login(client, "testpatient01@test.local", seed_data["password"])
    resp = client.get("/doctors", headers=_auth_header(token))
    assert resp.status_code == 200
    doctors = resp.json()
    assert len(doctors) >= 2
    assert any(d["display_name"] == "Test Doctor 01" for d in doctors)


def test_get_doctor_slots_weekday(client, seed_data):
    """Querying free slots for a future weekday returns 30-min slots."""
    token = _login(client, "testpatient01@test.local", seed_data["password"])
    doctor_id = str(seed_data["doctor"].id)

    tz = ZoneInfo("Asia/Kolkata")
    now = datetime.now(tz)
    candidate = now + timedelta(days=2)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    date_str = candidate.strftime("%Y-%m-%d")

    resp = client.get(
        f"/doctors/{doctor_id}/slots?date={date_str}",
        headers=_auth_header(token),
    )
    assert resp.status_code == 200
    slots = resp.json()
    assert isinstance(slots, list)
    assert len(slots) > 0
    assert "slot_start" in slots[0]
    assert "slot_end" in slots[0]


def test_get_doctor_slots_weekend_empty(client, seed_data):
    """Querying slots on a weekend returns an empty list."""
    token = _login(client, "testpatient01@test.local", seed_data["password"])
    doctor_id = str(seed_data["doctor"].id)

    tz = ZoneInfo("Asia/Kolkata")
    now = datetime.now(tz)
    days_until_sat = (5 - now.weekday()) % 7
    if days_until_sat == 0:
        days_until_sat = 7
    sat = now + timedelta(days=days_until_sat)
    date_str = sat.strftime("%Y-%m-%d")

    resp = client.get(
        f"/doctors/{doctor_id}/slots?date={date_str}",
        headers=_auth_header(token),
    )
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_doctor_slots_unknown_doctor_404(client, seed_data):
    """Querying slots for non-existent doctor returns 404."""
    token = _login(client, "testpatient01@test.local", seed_data["password"])
    resp = client.get(
        "/doctors/00000000-0000-0000-0000-000000000000/slots?date=2026-11-20",
        headers=_auth_header(token),
    )
    assert resp.status_code == 404


def test_get_doctor_slots_invalid_date_422(client, seed_data):
    """Querying slots with invalid date format returns 422."""
    token = _login(client, "testpatient01@test.local", seed_data["password"])
    doctor_id = str(seed_data["doctor"].id)
    resp = client.get(
        f"/doctors/{doctor_id}/slots?date=invalid-date",
        headers=_auth_header(token),
    )
    assert resp.status_code == 422
