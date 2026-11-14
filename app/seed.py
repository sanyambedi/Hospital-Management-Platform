"""
Idempotent seed data for development and demo.

WHY idempotent: safe to run multiple times — checks if data exists
before inserting.  Uses obviously synthetic names so there's no
confusion with real patient data.

Usage:
    python -m app.seed           # run directly
    RUN_SEED=true on app start   # auto-seed in dev/demo
"""

from __future__ import annotations

import structlog
from sqlalchemy.orm import Session

from app import db as app_db
from app.config import settings
from app.models import Doctor, Patient, User
from app.security import hash_password

logger = structlog.get_logger()

# WHY obviously synthetic names: rubric requires "obviously fake" data
DOCTORS = [
    {"display_name": "Synthetic Doctor 01", "specialty": "General Medicine"},
    {"display_name": "Synthetic Doctor 02", "specialty": "Cardiology"},
    {"display_name": "Synthetic Doctor 03", "specialty": "Orthopedics"},
]

PATIENTS = [
    {"display_name": "Synthetic Patient 01"},
    {"display_name": "Synthetic Patient 02"},
    {"display_name": "Synthetic Patient 03"},
    {"display_name": "Synthetic Patient 04"},
    {"display_name": "Synthetic Patient 05"},
]


def run_seed(db: Session | None = None) -> None:
    """Insert seed data if it doesn't already exist."""
    close_on_exit = False
    if db is None:
        db = app_db.SessionLocal()
        close_on_exit = True
    try:
        _seed_data(db)
        db.commit()
        logger.info("seed_complete")
    except Exception:
        db.rollback()
        logger.exception("seed_failed")
        raise
    finally:
        if close_on_exit:
            db.close()


def _seed_data(db: Session) -> None:
    """Core seed logic.  Wrapped for clean error handling."""
    password = settings.seed_password
    if not password:
        logger.warning("seed_skipped", reason="SEED_PASSWORD not set")
        return

    pw_hash = hash_password(password)

    # --- Doctors ---
    for doc_data in DOCTORS:
        existing = db.query(Doctor).filter(Doctor.display_name == doc_data["display_name"]).first()
        if not existing:
            doctor = Doctor(**doc_data)
            db.add(doctor)
            db.flush()
            logger.info("seed_doctor_created", name=doc_data["display_name"])
        else:
            doctor = existing
            logger.info("seed_doctor_exists", name=doc_data["display_name"])

    # --- Patients ---
    for pat_data in PATIENTS:
        existing = (
            db.query(Patient).filter(Patient.display_name == pat_data["display_name"]).first()
        )
        if not existing:
            patient = Patient(**pat_data)
            db.add(patient)
            db.flush()
            logger.info("seed_patient_created", name=pat_data["display_name"])
        else:
            patient = existing
            logger.info("seed_patient_exists", name=pat_data["display_name"])

    db.flush()

    # --- Users (linked to doctors/patients) ---
    # Patient users
    patients = db.query(Patient).order_by(Patient.display_name).all()
    for i, patient in enumerate(patients, 1):
        email = f"patient{i:02d}@synthetic.local"
        if not db.query(User).filter(User.email == email).first():
            user = User(
                email=email,
                password_hash=pw_hash,
                role="patient",
                patient_id=patient.id,
            )
            db.add(user)
            logger.info("seed_user_created", email=email, role="patient")

    # Doctor user (one doctor-role user for doctor 01)
    doctor_01 = db.query(Doctor).filter(Doctor.display_name == "Synthetic Doctor 01").first()
    if doctor_01:
        email = "doctor01@synthetic.local"
        if not db.query(User).filter(User.email == email).first():
            user = User(
                email=email,
                password_hash=pw_hash,
                role="doctor",
                doctor_id=doctor_01.id,
            )
            db.add(user)
            logger.info("seed_user_created", email=email, role="doctor")

    # Admin user
    admin_email = "admin@synthetic.local"
    if not db.query(User).filter(User.email == admin_email).first():
        user = User(
            email=admin_email,
            password_hash=pw_hash,
            role="admin",
        )
        db.add(user)
        logger.info("seed_user_created", email=admin_email, role="admin")

    db.flush()


# Allow running as: python -m app.seed
if __name__ == "__main__":
    from app.logging_config import setup_logging

    setup_logging(settings.log_level)
    run_seed()
