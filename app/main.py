"""
FastAPI application factory and startup wiring.

WHY app factory pattern: allows different configurations for testing vs
production (the test suite can import create_app() with overrides).
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse

from app.config import settings
from app.logging_config import RequestIdMiddleware, setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle.

    WHY lifespan over on_event: FastAPI recommends lifespan context
    managers as the modern replacement for @app.on_event decorators.
    """
    logger = structlog.get_logger()
    logger.info(
        "app_starting",
        version=settings.app_version,
        env=settings.app_env,
        timezone=settings.timezone,
    )

    # For local standalone / demo mode on SQLite: ensure tables exist
    if settings.database_url.startswith("sqlite"):
        from app.db import engine
        from app.models import Base

        Base.metadata.create_all(engine)

    # Optional auto-seed in dev/demo mode
    if settings.run_seed:
        logger.info("auto_seed_enabled", run_seed=True)
        try:
            from app.seed import run_seed

            run_seed()
            logger.info("auto_seed_complete")
        except Exception:
            logger.exception("auto_seed_failed")

    yield  # App runs here

    logger.info("app_shutting_down")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    # Setup structured logging before anything else
    setup_logging(settings.log_level)

    app = FastAPI(
        title="Hospital Appointment API",
        description="A small hospital appointment service delivered like a production system",
        version=settings.app_version,
        lifespan=lifespan,
    )

    # WHY RequestIdMiddleware: every log line gets a request_id for tracing
    app.add_middleware(RequestIdMiddleware)

    # Wire routers
    from app.routers import appointments, auth, doctors, health

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(doctors.router)
    app.include_router(appointments.router)

    portal_html = os.path.join(os.path.dirname(__file__), "static", "index.html")

    @app.get("/", include_in_schema=False)
    @app.get("/portal", include_in_schema=False)
    def root():
        """Serve the hospital appointment web portal."""
        if os.path.exists(portal_html):
            return FileResponse(portal_html)
        return RedirectResponse(url="/docs")

    return app


# Module-level app instance for uvicorn to discover: `uvicorn app.main:app`
app = create_app()
