"""
Tests for health check endpoints.

Covers:
- /healthz returns 200 (liveness, no DB dependency)
- /readyz returns 200 when DB is reachable
- /readyz returns 503 when DB is unreachable (monkeypatch)
"""

from __future__ import annotations

from unittest.mock import patch


def test_healthz_returns_ok(client):
    """Liveness probe always returns 200 — no DB call involved."""
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_readyz_returns_ok_when_db_healthy(client):
    """Readiness probe returns 200 when DB is reachable."""
    resp = client.get("/readyz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert data["checks"]["db"] == "ok"


def test_readyz_returns_503_when_db_unreachable(client):
    """Readiness probe returns 503 when DB check fails.

    WHY this test: proves the liveness vs readiness distinction —
    the app is alive but not ready to serve traffic.
    """
    with patch("app.routers.health.check_db", return_value=False):
        resp = client.get("/readyz")
    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "not_ready"
    assert data["checks"]["db"] == "fail"


def test_healthz_has_request_id(client):
    """Every response includes X-Request-ID for traceability."""
    resp = client.get("/healthz")
    assert "x-request-id" in resp.headers
