"""
Local development server runner for the Hospital Appointment API.
Starts Uvicorn on 127.0.0.1:8000 with SQLite fallback and auto-seed.
"""

import os

# Ensure default environment variables for local run
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("DATABASE_URL", "sqlite:///./hospital.db")
os.environ.setdefault("RUN_SEED", "true")
os.environ.setdefault("SEED_PASSWORD", "TestPassword123!")
os.environ.setdefault("JWT_SECRET", "dev-insecure-jwt-secret-key-32chars-min")
os.environ.setdefault("LOG_LEVEL", "info")

if __name__ == "__main__":
    import uvicorn

    print("\n" + "=" * 60)
    print("  Hospital Management Platform API running at:")
    print("  👉 Swagger UI: http://127.0.0.1:8000/docs")
    print("  👉 ReDoc UI:   http://127.0.0.1:8000/redoc")
    print("  👉 Health:     http://127.0.0.1:8000/healthz")
    print("  👉 Ready:      http://127.0.0.1:8000/readyz")
    print("=" * 60 + "\n")
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, log_level="info")
