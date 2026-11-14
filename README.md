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
git clone <repo-url> && cd hospital-appointment-api

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

## Troubleshooting

- **503 on /readyz**: Check DB connectivity (`docker compose logs db`)
- **502 from proxy**: App not healthy (`docker compose logs app`)
- **409 on appointments**: Slot already booked (correct behavior)
- **HTTPS cert warning**: Expected with Caddy internal CA; use `curl -k`

## Known Limitations

- No rate limiting (not required by spec)
- No frontend (API only)
- Single-node deployment (no HA)
- Internal CA for TLS (not production-ready certificates)
- HTTPS cert must be trusted manually for browsers

## License

This project is for educational purposes.
