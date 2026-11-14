#!/usr/bin/env python3
"""
Concurrency proof: fires 50 parallel bookings at the same doctor+slot.

Expected result: exactly 1x 201, 49x 409, 1 DB row confirmed.
Saves output to docs/evidence/concurrency-proof.log.

WHY this script: proves the DB partial unique index prevents
double-booking even under heavy concurrent load — the single
most important correctness guarantee in the system.
"""

import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

BASE_URL = os.environ.get("BASE_URL", "https://localhost")
N_REQUESTS = 50

# WHY unverified context: Caddy uses internal CA for local dev
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def api_request(method, path, data=None, headers=None):
    """Make an HTTP request and return (status_code, response_body)."""
    url = f"{BASE_URL}{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        resp = urllib.request.urlopen(req, context=ctx, timeout=30)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read()) if e.fp else {}


def main():
    # Read seed password
    seed_password = os.environ.get("SEED_PASSWORD", "")
    if not seed_password:
        try:
            with open("secrets/seed_password.txt") as f:
                seed_password = f.read().strip()
        except FileNotFoundError:
            print("ERROR: SEED_PASSWORD not set and secrets/seed_password.txt not found")
            sys.exit(1)

    # Login
    status, body = api_request(
        "POST",
        "/auth/login",
        {
            "email": "patient01@synthetic.local",
            "password": seed_password,
        },
    )
    if status != 200:
        print(f"ERROR: Login failed with status {status}")
        sys.exit(1)
    token = body["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    # Find a valid future weekday slot
    tz = ZoneInfo("Asia/Kolkata")
    now = datetime.now(tz)
    candidate = now + timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    slot_start = candidate.replace(hour=15, minute=30, second=0, microsecond=0).isoformat()

    # Get first doctor
    status, doctors = api_request("GET", "/doctors", headers=auth_headers)
    if status != 200 or not doctors:
        print("ERROR: Could not list doctors")
        sys.exit(1)
    doctor_id = doctors[0]["id"]

    print("=== Concurrency Proof ===")
    print(f"Doctor: {doctor_id}")
    print(f"Slot:   {slot_start}")
    print(f"Concurrent requests: {N_REQUESTS}")
    print()

    # Fire N_REQUESTS parallel bookings
    results = []

    def book():
        s, b = api_request(
            "POST",
            "/appointments",
            {
                "doctor_id": doctor_id,
                "slot_start": slot_start,
                "reason": "concurrency proof",
            },
            auth_headers,
        )
        return s

    with ThreadPoolExecutor(max_workers=N_REQUESTS) as executor:
        futures = [executor.submit(book) for _ in range(N_REQUESTS)]
        for f in as_completed(futures):
            results.append(f.result())

    # Count results
    count_201 = results.count(201)
    count_409 = results.count(409)
    count_other = len(results) - count_201 - count_409

    print("Results:")
    print(f"  201 (created):  {count_201}")
    print(f"  409 (conflict): {count_409}")
    print(f"  other:          {count_other}")
    print()

    # Check DB (via API - list appointments and count)
    status, appts = api_request("GET", "/appointments", headers=auth_headers)
    # Count confirmed appointments for this doctor+slot
    confirmed = (
        [
            a
            for a in appts
            if a.get("doctor_id") == doctor_id
            and a.get("slot_start", "").startswith(slot_start[:16])
            and a.get("status") == "confirmed"
        ]
        if isinstance(appts, list)
        else []
    )

    print(f"Confirmed DB rows for this slot: {len(confirmed)}")
    print()

    # Verdict
    success = (
        count_201 == 1 and count_409 == N_REQUESTS - 1 and count_other == 0 and len(confirmed) == 1
    )
    if success:
        print("✓ PASS: Exactly 1 booking succeeded, all others got 409")
    else:
        print("✗ FAIL: Unexpected results")

    print()
    print(f"=== Concurrency Proof {'PASS' if success else 'FAIL'} ===")

    # Save to evidence
    os.makedirs("docs/evidence", exist_ok=True)
    with open("docs/evidence/concurrency-proof.log", "w") as f:
        f.write(f"Concurrency Proof - {datetime.now(tz).isoformat()}\n")
        f.write(f"Doctor: {doctor_id}\n")
        f.write(f"Slot: {slot_start}\n")
        f.write(f"Requests: {N_REQUESTS}\n")
        f.write(f"201: {count_201} | 409: {count_409} | other: {count_other}\n")
        f.write(f"Confirmed DB rows: {len(confirmed)}\n")
        f.write(f"Result: {'PASS' if success else 'FAIL'}\n")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
