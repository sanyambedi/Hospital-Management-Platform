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

- No rate limiting (spec says "NOT required")
- No frontend (API-only, as specified)
- No /metrics endpoint (stretch goal, skipped for time)
- Single-node deployment (Compose, not Kubernetes — appropriate for scope)
- HTTPS uses internal CA, not production certificates

## Deployment & Evidence

- **CI/CD Run URL**: https://github.com/sanyambedi/Hospital-Management-Platform/actions/runs/43713905755
- **Image Digest**: `sha256:5cc0f68c9351339279781333f63f0cd4243df83dd08fc2cd6edffc5d68af4625`
- **Image Tag**: `ghcr.io/sanyambedi/hospital-management-platform:latest` / `ghcr.io/sanyambedi/hospital-management-platform:v1.0.0`
- **Evidence Files**:
  - Concurrency Proof: [docs/evidence/concurrency-proof.log](evidence/concurrency-proof.log)
  - Backup & Restore Drill: [docs/evidence/backup-restore.log](evidence/backup-restore.log)
  - Failure & Recovery Drill: [docs/evidence/failure-drill.log](evidence/failure-drill.log)
  - Rollback Demo: [docs/evidence/rollback.log](evidence/rollback.log)
  - Deployment Health: [docs/evidence/deployment-health.txt](evidence/deployment-health.txt)

## AI & Attribution

<<FILL: AI tools used and purpose>>

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
