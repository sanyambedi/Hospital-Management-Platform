"""
Test fixtures shared across all test modules.

WHY separate test database: tests must never touch production data.
We use SQLAlchemy to create all tables in a test DB, and the FastAPI
test client uses httpx for synchronous HTTP calls.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# Set test env vars BEFORE importing app modules
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-do-not-use-in-production")
os.environ.setdefault("SEED_PASSWORD", "test-seed-password")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://hospital:hospital@localhost:5432/hospital_test"
)
os.environ.setdefault("LOG_LEVEL", "warning")

from app.main import create_app
from app.models import Base, Doctor, Patient, User
from app.security import hash_password


@pytest.fixture(scope="session")
def db_engine():
    """Create a test database engine (once per test session).

    Tries PostgreSQL first (as in CI); if unreachable, falls back to
    SQLite in-memory so local development and test runs succeed cleanly.
    """
    db_url = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://hospital:hospital@localhost:5432/hospital_test"
    )
    engine = None
    if db_url.startswith("postgresql"):
        try:
            eng = create_engine(db_url, pool_pre_ping=True, connect_args={"connect_timeout": 3})
            with eng.connect() as conn:
                conn.execute(text("SELECT 1"))
            engine = eng
        except Exception:
            pass

    if engine is None:
        import contextlib
        import tempfile

        from sqlalchemy import event

        db_path = os.path.join(tempfile.gettempdir(), "hospital_test.db")
        if os.path.exists(db_path):
            with contextlib.suppress(Exception):
                os.remove(db_path)

        engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False, "timeout": 30.0},
        )

        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()

    # Create all tables
    Base.metadata.create_all(engine)

    yield engine

    # Cleanup: drop all tables after all tests
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(autouse=True)
def bind_test_db(db_engine):
    """Ensure the application db engine and sessionmaker use the test database."""
    from app import db as app_db

    old_engine = app_db.engine
    old_session = app_db.SessionLocal
    app_db.engine = db_engine
    app_db.SessionLocal = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    yield
    app_db.engine = old_engine
    app_db.SessionLocal = old_session


@pytest.fixture(autouse=True)
def clean_tables(db_engine):
    """Wipe data between test runs for complete test isolation."""
    yield
    with db_engine.connect() as conn:
        conn.execute(text("DELETE FROM audit_events;"))
        conn.execute(text("DELETE FROM appointments;"))
        conn.execute(text("DELETE FROM users;"))
        conn.execute(text("DELETE FROM patients;"))
        conn.execute(text("DELETE FROM doctors;"))
        conn.commit()


@pytest.fixture()
def db_session(db_engine) -> Generator[Session, None, None]:
    """Provide a DB session for test setup and verification."""
    session_factory = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    session = session_factory()
    yield session
    session.close()


@pytest.fixture()
def client(monkeypatch) -> Generator[TestClient, None, None]:
    """FastAPI test client.

    Uses app.db.get_db naturally, providing separate sessions per request
    and per thread for full concurrency support.
    """
    app = create_app()
    monkeypatch.setattr("app.routers.health.check_db", lambda: True)

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def seed_data(db_session) -> dict:
    """Create minimal seed data for tests. Returns a dict of created entities."""
    pw_hash = hash_password("testpassword123")

    # Create a doctor
    doctor = Doctor(display_name="Test Doctor 01", specialty="Testing")
    db_session.add(doctor)
    db_session.flush()

    # Create a second doctor for cross-doctor tests
    doctor2 = Doctor(display_name="Test Doctor 02", specialty="Testing2")
    db_session.add(doctor2)
    db_session.flush()

    # Create patients
    patient1 = Patient(display_name="Test Patient 01")
    patient2 = Patient(display_name="Test Patient 02")
    db_session.add_all([patient1, patient2])
    db_session.flush()

    # Create users
    patient_user1 = User(
        email="testpatient01@test.local",
        password_hash=pw_hash,
        role="patient",
        patient_id=patient1.id,
    )
    patient_user2 = User(
        email="testpatient02@test.local",
        password_hash=pw_hash,
        role="patient",
        patient_id=patient2.id,
    )
    doctor_user = User(
        email="testdoctor01@test.local",
        password_hash=pw_hash,
        role="doctor",
        doctor_id=doctor.id,
    )
    admin_user = User(
        email="testadmin@test.local",
        password_hash=pw_hash,
        role="admin",
    )
    db_session.add_all([patient_user1, patient_user2, doctor_user, admin_user])
    db_session.commit()

    return {
        "doctor": doctor,
        "doctor2": doctor2,
        "patient1": patient1,
        "patient2": patient2,
        "patient_user1": patient_user1,
        "patient_user2": patient_user2,
        "doctor_user": doctor_user,
        "admin_user": admin_user,
        "password": "testpassword123",
    }


def _login(client: TestClient, email: str, password: str) -> str:
    """Helper: log in and return the access token."""
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


def _auth_header(token: str) -> dict:
    """Helper: return Authorization header dict."""
    return {"Authorization": f"Bearer {token}"}


def _next_weekday_slot() -> str:
    """Helper: return an ISO datetime string for the next available weekday slot.

    WHY: tests need a valid future slot that passes all validation rules.
    """
    tz = ZoneInfo("Asia/Kolkata")
    now = datetime.now(tz)
    # Find next weekday
    candidate = now + timedelta(days=1)
    while candidate.weekday() >= 5:  # Skip weekends
        candidate += timedelta(days=1)
    # Set to 10:00 AM (within working hours, on the 30-min grid)
    slot = candidate.replace(hour=10, minute=0, second=0, microsecond=0)
    return slot.isoformat()


def _next_weekday_slot_offset(days: int = 1, hour: int = 10, minute: int = 0) -> str:
    """Helper: return a slot datetime string with configurable offset."""
    tz = ZoneInfo("Asia/Kolkata")
    now = datetime.now(tz)
    candidate = now + timedelta(days=days)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    slot = candidate.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return slot.isoformat()
