# =============================================================================
# Hospital Appointment API – Makefile
# All operational tasks in one place. Run `make <target>`.
# =============================================================================
.PHONY: init-secrets up down logs test lint fmt seed backup restore \
        drill-backup drill-failure deploy rollback smoke concurrency-proof demo

# WHY: single variable so compose file path is defined once
COMPOSE := docker compose -f deploy/docker-compose.yml

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

## Generate random secrets for local dev (idempotent – won't overwrite existing)
## WHY python fallback: openssl may not be available on all platforms (e.g. Windows)
init-secrets:
	@mkdir -p secrets
	@test -f secrets/db_password.txt    || python -c "import secrets; print(secrets.token_urlsafe(32), end='')" > secrets/db_password.txt
	@test -f secrets/jwt_secret.txt     || python -c "import secrets; print(secrets.token_urlsafe(32), end='')" > secrets/jwt_secret.txt
	@test -f secrets/seed_password.txt  || python -c "import secrets; print(secrets.token_urlsafe(32), end='')" > secrets/seed_password.txt
	@echo "✓ Secrets initialized in secrets/"

# ---------------------------------------------------------------------------
# Docker Compose lifecycle
# ---------------------------------------------------------------------------

## Start the full stack (db + migrate + app + proxy); waits for healthy
up:
	$(COMPOSE) up -d
	@echo "Waiting for services to become healthy..."
	@sleep 8

## Stop all services
down:
	$(COMPOSE) down

## Tail application logs
logs:
	$(COMPOSE) logs -f app

# ---------------------------------------------------------------------------
# Development
# ---------------------------------------------------------------------------

## Run test suite with coverage
test:
	pytest tests/ --cov=app --cov-report=term-missing -v

## Lint and format check (CI uses this)
lint:
	ruff check .
	ruff format --check .

## Auto-fix lint issues and format code
fmt:
	ruff check --fix .
	ruff format .

## Run idempotent seed against running stack
seed:
	$(COMPOSE) exec app python -m app.seed

# ---------------------------------------------------------------------------
# Backup & restore
# ---------------------------------------------------------------------------

## Create a timestamped DB backup
backup:
	bash scripts/backup.sh

## Restore from a dump file: make restore FILE=backups/hospital_20240101_120000.dump
restore:
	bash scripts/restore.sh $(FILE) --yes

## Automated backup/restore drill with evidence log
drill-backup:
	bash scripts/drill_backup_restore.sh

## Automated failure/recovery drill with evidence log
drill-failure:
	bash scripts/drill_failure.sh

# ---------------------------------------------------------------------------
# Deployment
# ---------------------------------------------------------------------------

## Deploy a specific image tag: make deploy TAG=v1.0.0
deploy:
	bash scripts/deploy.sh $(TAG)

## Roll back to the previous deployed tag
rollback:
	bash scripts/rollback.sh

## Run smoke tests against the live stack
smoke:
	bash scripts/smoke_test.sh

# ---------------------------------------------------------------------------
# Evidence & demo
# ---------------------------------------------------------------------------

## Run concurrency proof (50 parallel bookings → exactly 1 success)
concurrency-proof:
	python3 scripts/concurrency_proof.py || python scripts/concurrency_proof.py

## Full demo: secrets → up → seed → smoke → concurrency → drills → summary
demo:
	bash scripts/demo.sh
