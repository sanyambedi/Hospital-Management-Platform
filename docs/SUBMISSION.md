# Submission

## Tech Stack

- **Language**: Python 3.12
- **Framework**: FastAPI + Uvicorn
- **Database**: PostgreSQL 16
- **ORM**: SQLAlchemy 2.x + Alembic migrations
- **Auth**: JWT (PyJWT) + argon2-cffi password hashing
- **Logging**: structlog (JSON to stdout)
- **Testing**: pytest + httpx + pytest-cov
- **Linting**: ruff
- **Container**: Docker (multi-stage), Docker Compose v2
- **Proxy**: Caddy 2 (automatic HTTPS with internal CA)
- **CI/CD**: GitHub Actions → GHCR
- **Security**: Trivy, gitleaks, pip-audit, cosign, SBOM

## Setup Notes

1. Requires Docker and Docker Compose v2
2. `make init-secrets` generates random secrets (never committed)
3. `make up` starts the full stack with health-check dependencies
4. `make seed` creates synthetic test data
5. HTTPS uses Caddy's internal CA — use `curl -k` or trust the cert

## Known Incomplete Features / Assumptions

- Trivy and pip-audit run in CI as non-blocking checks (accepted for time; reports are uploaded as artifacts)
- SQLite fallback and the static UI (app/static/index.html) are local-dev extras outside the brief's scope
- The app-kill part of the failure drill needs a Linux host (it kills the container's process by host PID), so it runs in CI, not on Docker Desktop

## Deployment & Evidence

- **CI/CD Run URL**: https://github.com/sanyambedi/Hospital-Management-Platform/actions/runs/43723667369
- **Image Digest**: `sha256:51db07df4c457febc4e75fedb516d7e46d9b5ea53ca71c2827c123704ad1d478`
- **Image Tag**: `ghcr.io/sanyambedi/hospital-management-platform:sha-eda8844419003e48bca47998324404c1c4f39f29`
- **Demo mode**: Local-only demo (Docker Compose); no live public URL.

## AI & Attribution

AI tools used: Antigravity (code scaffolding, scripts, CI workflow) and Claude (spec planning, code review, debugging). I reviewed, ran and tested all generated code, and I can explain the architecture and modify it.

## Declarations Checklist

- [x] All data is synthetic (no real patient data)
- [x] No secrets committed to the repository
- [x] All code is original or attributed
- [x] Tests pass in CI with real PostgreSQL
- [x] Double-booking prevention verified with concurrency test

## Rubric-to-Evidence Map

| Criterion (Marks) | Evidence |
|-------------------|----------|
| **Containerization & reproducibility (20)** | `Dockerfile` (multi-stage, non-root, healthcheck), `deploy/docker-compose.yml` (hardened, secrets, volumes), `make up` from clean checkout |
| **CI/CD automation (20)** | `.github/workflows/ci.yml` (lint→test→build→scan→push→smoke), cosign signing, SBOM, Trivy, gitleaks |
| **Deployment, networking, security (15)** | `deploy/Caddyfile` (HTTPS, security headers), internal-only networks, no published DB port, `cap_drop: ALL`, `read_only: true` |
| **Observability & troubleshooting (15)** | `/healthz` vs `/readyz`, structlog JSON logs, `X-Request-ID`, `docs/evidence/failure-drill.log` |
| **Backup, restore, rollback (15)** | `scripts/backup.sh`, `scripts/restore.sh`, `docs/evidence/backup-restore.log`, `scripts/deploy.sh` with auto-rollback |
| **Reliability & documentation (10)** | `README.md`, `docs/ARCHITECTURE.md`, `docs/RUNBOOK.md`, 6 ADRs, `Makefile` targets |
| **Domain API correctness (5)** | Partial unique index, `tests/test_concurrency.py`, `docs/evidence/concurrency-proof.log` |
