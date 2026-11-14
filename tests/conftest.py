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
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Set test env vars BEFORE importing app modules
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-do-not-use-in-production")
os.environ.setdefault("SEED_PASSWORD", "test-seed-password")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://hospital:hospital@localhost:5432/hospital_test"
)
os.environ.setdefault("LOG_LEVEL", "warning")

from app.db import get_db
from app.main import create_app
from app.models import Base, Doctor, Patient, User
from app.security import hash_password


@pytest.fixture(scope="session")
def db_engine():
    """Create a test database engine (once per test session).

    WHY session-scoped: creating the engine is expensive; tables are
    created once and transactions are rolled back per test for isolation.
    """
    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)

    # Create all tables
    Base.metadata.create_all(engine)

    yield engine

    # Cleanup: drop all tables after all tests
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def db_session(db_engine) -> Generator[Session, None, None]:
    """Provide a transactional DB session that rolls back after each test.

    WHY rollback: each test gets a clean slate without expensive
    table recreation.
    """
    connection = db_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def client(db_session) -> Generator[TestClient, None, None]:
    """FastAPI test client with DB session override.

    WHY override get_db: ensures all endpoint calls within a test use
    the same transactional session that gets rolled back.
    """
    app = create_app()

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def seed_data(db_session) -> dict:
    """Create minimal seed data for tests.  Returns a dict of created entities."""
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
    db_session.flush()

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
