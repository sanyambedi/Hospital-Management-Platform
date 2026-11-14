"""
Tests for idempotent seed data generation.

Covers:
- run_seed creates doctors, patients, users
- running seed twice is idempotent (does not duplicate rows)
"""

from __future__ import annotations

from app.models import Doctor, Patient, User
from app.seed import run_seed


def test_seed_idempotent(db_session, monkeypatch):
    """Calling run_seed creates expected records and running again is idempotent."""
    monkeypatch.setattr("app.config.settings.seed_password", "TestPass123!")

    # First run
    run_seed()

    doc_count_1 = db_session.query(Doctor).count()
    pat_count_1 = db_session.query(Patient).count()
    user_count_1 = db_session.query(User).count()

    assert doc_count_1 == 3
    assert pat_count_1 == 5
    assert user_count_1 >= 7

    # Second run — idempotent
    run_seed()

    doc_count_2 = db_session.query(Doctor).count()
    pat_count_2 = db_session.query(Patient).count()
    user_count_2 = db_session.query(User).count()

    assert doc_count_1 == doc_count_2
    assert pat_count_1 == pat_count_2
    assert user_count_1 == user_count_2
