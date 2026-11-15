# Hospital Appointment API

A small hospital appointment booking service delivered with production-grade infrastructure: containerized, CI/CD automated, HTTPS-secured, with backup/restore, rollback, and observability.

## Architecture

```
Client → Caddy (HTTPS/TLS) → FastAPI → PostgreSQL
           port 443              port 8000      port 5432
         [frontend net]      [frontend+backend]  [backend net]
```

- **Double-booking prevention**: DB-level partial unique index (not just app checks)
- **Structured JSON logs** with request IDs for tracing
- **Non-root containers**, read-only filesystems, dropped capabilities

## Prerequisites

- Docker Engine 24+ with Docker Compose v2
- Python 3.12+ (for local dev/tests)
- `openssl` (for generating secrets)
- `curl` (for smoke tests)

## Quick Start (Clean Machine)

```bash
# 1. Clone
git clone https://github.com/sanyambedi/Hospital-Management-Platform.git && cd Hospital-Management-Platform

# 2. Generate secrets (idempotent)
make init-secrets

# 3. Start the full stack (db → migrate → app → proxy)
make up

# 4. Seed synthetic data
make seed

# 5. Verify everything works
make smoke
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_ENV` | `development` | Environment name |
| `LOG_LEVEL` | `info` | Log level (debug/info/warning/error) |
| `DATABASE_URL` | `postgresql+psycopg://...` | Full DB connection string |
| `DB_PASSWORD_FILE` | — | Path to file containing DB password |
| `JWT_SECRET` / `JWT_SECRET_FILE` | — | HMAC signing key for JWTs |
| `JWT_EXPIRY_MINUTES` | `30` | Token lifetime |
| `SEED_PASSWORD` / `SEED_PASSWORD_FILE` | — | Password for synthetic users |
| `RUN_SEED` | `false` | Auto-seed on startup |
| `SLOT_MINUTES` | `30` | Appointment slot duration |
| `WORK_START` | `09:00` | Clinic opening time |
| `WORK_END` | `17:00` | Clinic closing time |
| `TIMEZONE` | `Asia/Kolkata` | Timezone for slot validation |
| `IMAGE_TAG` | `latest` | Docker image tag for deploys |

## Port Map

| Port | Service | Exposure |
|------|---------|----------|
| 443 | Caddy (HTTPS) | **Public** |
| 80 | Caddy (HTTP→HTTPS redirect) | **Public** |
| 8000 | FastAPI app | Internal only |
| 5432 | PostgreSQL | Internal only |

## API Endpoints

### Public
- `GET /healthz` — Liveness probe (always 200)
- `GET /readyz` — Readiness probe (200 if DB reachable)
- `POST /auth/login` — Get JWT token

### Authenticated (Bearer JWT)
- `GET /doctors` — List all doctors
- `GET /doctors/{id}/slots?date=YYYY-MM-DD` — Available slots
- `POST /appointments` — Book an appointment
- `GET /appointments` — List (filtered by role)
- `GET /appointments/{id}` — Get single appointment
- `PATCH /appointments/{id}/reschedule` — Reschedule
- `POST /appointments/{id}/cancel` — Cancel

### Example curl Commands

```bash
# Login
curl -k -X POST https://localhost/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"patient01@synthetic.local","password":"<SEED_PASSWORD>"}'

# List doctors
curl -k https://localhost/doctors -H "Authorization: Bearer <TOKEN>"

# Book appointment
curl -k -X POST https://localhost/appointments \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"doctor_id":"<UUID>","slot_start":"2024-01-15T10:00:00+05:30","reason":"Checkup"}'
```

## CI/CD

GitHub Actions pipeline on every push:
1. **Secret scan** (gitleaks) — fails if secrets found
2. **Lint** (ruff) + **security audit** (pip-audit)
3. **Test** (pytest with Postgres service container, coverage ≥80%)
4. **Build, scan, push** — Buildx, Trivy scan, SBOM, cosign signing
5. **Smoke test** — docker compose up → smoke_test.sh

Image tags: `sha-<short>`, branch name, `vX.Y.Z`, `latest` (on main).

## Deploy & Rollback

```bash
# Deploy a specific version
make deploy TAG=v1.0.0

# Roll back to previous version
make rollback
```

## Backup & Restore

```bash
# Create backup
make backup

# Restore from backup
make restore FILE=backups/hospital_20240101_120000.dump

# Automated drill with evidence
make drill-backup
```

## Testing

```bash
# Run all tests with coverage
make test

# Lint
make lint

# Concurrency proof (against running stack)
make concurrency-proof
```

## Evidence & Verification

All operational claims are verified with reproducible logs from real containerized stack runs:
- [Concurrency Proof Log](docs/evidence/concurrency-proof.log): 50 parallel requests competing for the exact same slot; DB-level unique partial index guarantees 1x 201 Created and 49x 409 Conflict.
- [Backup & Restore Drill Log](docs/evidence/backup-restore.log): Full backup, drop database, restore, and table checksum verification (PASS).
- [Failure & Recovery Drill Log](docs/evidence/failure-drill.log): Database outage detection (`/healthz` 200, `/readyz` 503), recovery, and app container kill with Docker restart policy auto-recovery.
- [Rollback Drill Log](docs/evidence/rollback.log): Bad image deployment failure detection and automated rollback to previous known-good tag.
- [Deployment Health Report](docs/evidence/deployment-health.txt): Running container health statuses, image digest, non-root user verification, and internal port isolation.

## Troubleshooting

- **503 on /readyz**: Check DB connectivity (`docker compose logs db`)
- **502 from proxy**: App not healthy (`docker compose logs app`)
- **409 on appointments**: Slot already booked (correct behavior)
- **HTTPS cert warning**: Expected with Caddy internal CA; use `curl -k`

## Known Limitations

- **SQLite Fallback**: The SQLite fallback engine is strictly for local dev/unit testing; production deployments require PostgreSQL 16+.
- **Static UI**: The static frontend UI (`app/static/index.html`) is a convenience interface outside the core project brief scope.
- **Metrics Endpoint**: `/metrics` Prometheus scrape endpoint was skipped for project scope and deadline constraints.
- **Single-Node Deployment**: Docker Compose single-node deployment (sufficient for project scope; Kubernetes avoided per ADR-006).
- **Internal CA for TLS**: Uses Caddy's internal ACME CA; self-signed certificate must be accepted or trusted manually with `curl -k`.
- **No Rate Limiting**: Application-level rate limiting was omitted as per project specification.

## License

This project is for educational purposes.
