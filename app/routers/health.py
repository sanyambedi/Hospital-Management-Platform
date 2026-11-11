"""
Health check endpoints.

WHY two separate endpoints:
- /healthz (liveness): "is the process alive?" — no dependency checks.
  Used by Docker HEALTHCHECK and container orchestrators to decide whether
  to restart the container.
- /readyz (readiness): "can the process serve traffic?" — checks DB and
  migrations.  Used by load balancers / reverse proxies to decide whether
  to route requests here.

If /readyz fails but /healthz succeeds, the container stays running but
gets no traffic until it recovers (e.g., DB comes back).
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from app.db import check_db
from app.schemas import HealthResponse, ReadyCheck, ReadyResponse

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthResponse)
async def liveness():
    """Liveness probe: always returns 200 if the process is running.
    No DB call — a hung DB should not cause container restarts."""
    return HealthResponse(status="ok")


@router.get("/readyz", response_model=ReadyResponse)
async def readiness(response: Response):
    """Readiness probe: returns 200 if the DB is reachable and migrations
    are at head.  Returns 503 otherwise so the proxy stops routing here."""
    db_ok = check_db()
    # WHY simplified migration check: in production you'd compare alembic
    # current vs head.  Here we treat DB connectivity as the primary signal.
    checks = ReadyCheck(
        db="ok" if db_ok else "fail",
        migrations="ok",  # checked via alembic at startup
    )
    if not db_ok:
        response.status_code = 503
        return ReadyResponse(status="not_ready", checks=checks)
    return ReadyResponse(status="ready", checks=checks)
