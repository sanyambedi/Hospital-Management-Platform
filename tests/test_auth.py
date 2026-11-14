"""
Tests for authentication endpoints.

Covers:
- Successful login returns JWT
- Failed login (wrong password, unknown email) returns 401
- Missing token returns 401
- Wrong role returns 403
- Patient cannot read another patient's appointment (privacy)
"""

from __future__ import annotations

from tests.conftest import _auth_header, _login, _next_weekday_slot


def test_login_success(client, seed_data):
    """Valid credentials return a JWT token."""
    resp = client.post(
        "/auth/login",
        json={"email": "testpatient01@test.local", "password": seed_data["password"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0


def test_login_wrong_password(client, seed_data):
    """Wrong password returns 401."""
    resp = client.post(
        "/auth/login",
        json={"email": "testpatient01@test.local", "password": "wrong_password"},
    )
    assert resp.status_code == 401


def test_login_unknown_email(client, seed_data):
    """Unknown email returns 401 (same error as wrong password to prevent enumeration)."""
    resp = client.post(
        "/auth/login",
        json={"email": "nonexistent@test.local", "password": "anything"},
    )
    assert resp.status_code == 401


def test_missing_token_returns_401(client):
    """Accessing a protected endpoint without a token returns 401."""
    resp = client.get("/doctors")
    assert resp.status_code == 401


def test_invalid_token_returns_401(client):
    """An invalid/corrupted token returns 401."""
    resp = client.get("/doctors", headers={"Authorization": "Bearer invalid.token.here"})
    assert resp.status_code == 401


def test_wrong_role_returns_403(client, seed_data):
    """Doctor role cannot create an appointment (requires patient or admin)."""
    token = _login(client, "testdoctor01@test.local", seed_data["password"])
    slot = _next_weekday_slot()
    resp = client.post(
        "/appointments",
        json={
            "doctor_id": str(seed_data["doctor"].id),
            "slot_start": slot,
            "reason": "test",
        },
        headers=_auth_header(token),
    )
    assert resp.status_code == 403


def test_patient_cannot_see_other_patients_appointment(client, seed_data):
    """Patient 1's appointment must not be visible to Patient 2.

    WHY this test: proves data isolation between patients — a critical
    security requirement.
    """
    # Patient 1 creates an appointment
    token1 = _login(client, "testpatient01@test.local", seed_data["password"])
    slot = _next_weekday_slot()
    create_resp = client.post(
        "/appointments",
        json={
            "doctor_id": str(seed_data["doctor"].id),
            "slot_start": slot,
            "reason": "patient 1 appt",
        },
        headers=_auth_header(token1),
    )
    assert create_resp.status_code == 201
    appt_id = create_resp.json()["id"]

    # Patient 2 tries to access Patient 1's appointment
    token2 = _login(client, "testpatient02@test.local", seed_data["password"])
    get_resp = client.get(f"/appointments/{appt_id}", headers=_auth_header(token2))
    assert get_resp.status_code == 403


def test_patient_list_shows_only_own(client, seed_data):
    """Patient listing only returns their own appointments."""
    # Patient 1 creates an appointment
    token1 = _login(client, "testpatient01@test.local", seed_data["password"])
    slot = _next_weekday_slot()
    client.post(
        "/appointments",
        json={
            "doctor_id": str(seed_data["doctor"].id),
            "slot_start": slot,
            "reason": "patient 1 appt",
        },
        headers=_auth_header(token1),
    )

    # Patient 2 should see no appointments
    token2 = _login(client, "testpatient02@test.local", seed_data["password"])
    list_resp = client.get("/appointments", headers=_auth_header(token2))
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 0
