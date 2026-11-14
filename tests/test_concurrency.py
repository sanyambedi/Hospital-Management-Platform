"""
Concurrency test: THE key correctness test.

Fires ≥20 simultaneous appointment requests for the SAME doctor+slot
using threads.  Asserts exactly ONE 201 and all others 409, and
exactly ONE confirmed row in the DB.

WHY threads (not asyncio): the TestClient is synchronous; threads
are the simplest way to simulate concurrent requests in pytest.

WHY this matters: proves the DB partial unique index handles race
conditions correctly — "check then insert" alone would fail this test.
"""

from __future__ import annotations

import concurrent.futures

from tests.conftest import _auth_header, _login, _next_weekday_slot_offset


def test_concurrent_booking_exactly_one_wins(client, seed_data, db_session):
    """Fire 20+ concurrent bookings at the same slot.

    Expected: exactly 1x 201, rest 409, exactly 1 confirmed DB row.
    """
    token = _login(client, "testpatient01@test.local", seed_data["password"])
    slot = _next_weekday_slot_offset(days=8, hour=10, minute=0)
    doctor_id = str(seed_data["doctor"].id)
    headers = _auth_header(token)

    n_requests = 20
    results = []

    def _book():
        """Make a single booking request."""
        resp = client.post(
            "/appointments",
            json={
                "doctor_id": doctor_id,
                "slot_start": slot,
                "reason": "concurrency test",
            },
            headers=headers,
        )
        return resp.status_code

    # Fire all requests concurrently using a thread pool
    with concurrent.futures.ThreadPoolExecutor(max_workers=n_requests) as executor:
        futures = [executor.submit(_book) for _ in range(n_requests)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    # Count results
    count_201 = results.count(201)
    count_409 = results.count(409)

    # THE ASSERTION: exactly one winner
    assert count_201 == 1, f"Expected exactly 1x 201, got {count_201}"
    assert count_409 == n_requests - 1, f"Expected {n_requests - 1}x 409, got {count_409}"

    # Verify in DB: exactly one confirmed appointment for this slot
    from datetime import datetime

    from app.models import Appointment

    slot_dt = datetime.fromisoformat(slot)

    confirmed_count = (
        db_session.query(Appointment)
        .filter(
            Appointment.doctor_id == seed_data["doctor"].id,
            Appointment.slot_start == slot_dt,
            Appointment.status == "confirmed",
        )
        .count()
    )
    assert confirmed_count == 1, f"Expected 1 confirmed row in DB, got {confirmed_count}"


def test_concurrent_reschedule_collision(client, seed_data, db_session):
    """Two concurrent reschedules to the same target slot: one wins, one 409."""
    token = _login(client, "testpatient01@test.local", seed_data["password"])
    doctor_id = str(seed_data["doctor"].id)
    headers = _auth_header(token)

    slot_a = _next_weekday_slot_offset(days=9, hour=10, minute=0)
    slot_b = _next_weekday_slot_offset(days=9, hour=11, minute=0)
    target_slot = _next_weekday_slot_offset(days=9, hour=14, minute=0)

    # Create two appointments at different slots
    resp_a = client.post(
        "/appointments",
        json={"doctor_id": doctor_id, "slot_start": slot_a, "reason": "a"},
        headers=headers,
    )
    resp_b = client.post(
        "/appointments",
        json={"doctor_id": doctor_id, "slot_start": slot_b, "reason": "b"},
        headers=headers,
    )
    assert resp_a.status_code == 201
    assert resp_b.status_code == 201
    id_a = resp_a.json()["id"]
    id_b = resp_b.json()["id"]

    # Try to reschedule both to the same target slot concurrently
    results = []

    def _reschedule(appt_id):
        resp = client.patch(
            f"/appointments/{appt_id}/reschedule",
            json={"slot_start": target_slot},
            headers=headers,
        )
        return resp.status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(_reschedule, id_a),
            executor.submit(_reschedule, id_b),
        ]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    count_200 = results.count(200)
    count_409 = results.count(409)

    assert count_200 == 1, f"Expected exactly 1x 200, got {count_200}"
    assert count_409 == 1, f"Expected exactly 1x 409, got {count_409}"
