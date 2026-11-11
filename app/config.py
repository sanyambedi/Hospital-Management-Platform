"""
Application settings loaded from environment variables.

WHY env-based config: 12-factor app pattern — same image in every environment,
behaviour controlled entirely by env vars. The _FILE convention lets Docker
secrets be mounted as files, which is more secure than passing secrets as env
vars (visible in /proc, docker inspect, etc.).
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings


def _read_secret_file(env_var_file: str) -> str | None:
    """Read a secret from a file path specified by an env var.

    WHY: Docker secrets mount as files at /run/secrets/<name>.
    The *_FILE convention lets the same config.py work both locally
    (env var with the value) and in Docker (env var pointing to a file).
    """
    file_path = os.environ.get(env_var_file)
    if file_path:
        return Path(file_path).read_text().strip()
    return None


class Settings(BaseSettings):
    """Central configuration.  Every field maps to an env var of the same name
    (case-insensitive).  For secrets, check <NAME>_FILE first."""

    # --- Application ---
    app_env: str = "development"
    log_level: str = "info"
    app_version: str = "0.1.0"

    # --- Database ---
    # If DATABASE_URL is set directly, it wins.  Otherwise we build it from
    # component vars (DB_HOST, DB_PORT, etc.) — see model_validator below.
    database_url: str = ""
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "hospital"
    db_user: str = "hospital"
    db_password: str = ""  # read from DB_PASSWORD_FILE or DB_PASSWORD

    # --- Auth ---
    jwt_secret: str = ""  # read from JWT_SECRET_FILE or JWT_SECRET
    jwt_expiry_minutes: int = 30

    # --- Seed ---
    seed_password: str = ""  # read from SEED_PASSWORD_FILE or SEED_PASSWORD
    run_seed: bool = False

    # --- Slot configuration ---
    slot_minutes: int = 30
    work_start: str = "09:00"
    work_end: str = "17:00"
    timezone: str = "Asia/Kolkata"

    # --- Deployment ---
    image_tag: str = "latest"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # --- Read secrets from _FILE paths (Docker secrets) ---
        # WHY after __init__: pydantic-settings has already loaded env vars;
        # now we override with file-based secrets which take priority.
        self.db_password = _read_secret_file("DB_PASSWORD_FILE") or self.db_password
        self.jwt_secret = _read_secret_file("JWT_SECRET_FILE") or self.jwt_secret
        self.seed_password = _read_secret_file("SEED_PASSWORD_FILE") or self.seed_password

        # --- Build DATABASE_URL from components if not set directly ---
        if not self.database_url:
            self.database_url = (
                f"postgresql+psycopg://{self.db_user}:{self.db_password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}"
            )


# Singleton — imported throughout the app
settings = Settings()
