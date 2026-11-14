# Runbook

## Deploy

```bash
# Deploy a specific version
make deploy TAG=v1.0.0

# The script:
# 1. Records current tag to .deployed_tags history
# 2. Pulls and starts the new image
# 3. Runs smoke test
# 4. Auto-rolls back if smoke test fails
```

## Restart

```bash
# Restart all services
make down && make up

# Restart just the app
docker compose -f deploy/docker-compose.yml restart app

# Hard restart (recreate containers)
docker compose -f deploy/docker-compose.yml up -d --force-recreate
```

## View Logs

```bash
# Tail all logs
make logs

# App logs only
docker compose -f deploy/docker-compose.yml logs -f app

# Filter by request ID
docker compose -f deploy/docker-compose.yml logs app | jq 'select(.request_id == "abc-123")'

# Filter errors
docker compose -f deploy/docker-compose.yml logs app | jq 'select(.level == "error")'

# Filter by action
docker compose -f deploy/docker-compose.yml logs app | jq 'select(.action == "appointment.create_conflict")'
```

## Health Checks

```bash
# Liveness (is the process alive?)
curl -k https://localhost/healthz

# Readiness (can it serve traffic?)
curl -k https://localhost/readyz

# All services health
docker compose -f deploy/docker-compose.yml ps
```

## Backup

```bash
# Create backup
make backup
# Output: backups/hospital_YYYYMMDD_HHMMSS.dump + .sha256

# List backups
ls -la backups/
```

## Restore

```bash
# Restore from specific backup
make restore FILE=backups/hospital_20240101_120000.dump

# The script:
# 1. Verifies checksum
# 2. Stops app
# 3. Restores database
# 4. Runs migrations
# 5. Starts app
# 6. Runs smoke test
```

## Rollback

```bash
# Roll back to previous deployment
make rollback

# View deployment history
cat .deployed_tags
```

**DB migration rollback policy:**
```bash
# Roll back one migration
alembic downgrade -1

# Rule: migrations must be backward-compatible for one release
# (old app code must work with new schema)
```

## Incident Response

| Symptom | Likely Cause | Check | Fix |
|---------|-------------|-------|-----|
| 503 on /readyz | DB down or unreachable | `docker compose logs db` | `docker compose restart db`, wait for healthy |
| 502 from proxy | App not running or unhealthy | `docker compose logs app` | `docker compose restart app` |
| DB won't start | Corrupted data or disk full | `docker compose logs db`, `df -h` | Restore from backup |
| Disk full | Too many backups or logs | `du -sh backups/ /var/lib/docker` | Rotate backups, prune Docker |
| Cert issues | Caddy internal CA not trusted | `curl -k` to bypass | Trust Caddy CA or use `--cacert` |
| Migration failure | Schema conflict | `alembic current`, `alembic history` | Fix migration, `alembic downgrade -1` |
| 409 spikes | High contention on same slot | Check logs for `appointment.create_conflict` | Expected behavior; inform users |
| App OOM | Memory limit hit | `docker compose logs app`, `docker stats` | Increase memory limit in compose |

## On-Call Checklist

1. Check service health: `curl -k https://localhost/readyz`
2. Check container status: `docker compose -f deploy/docker-compose.yml ps`
3. Check recent logs: `docker compose -f deploy/docker-compose.yml logs --tail=50 app`
4. Check disk space: `df -h`
5. Check backup recency: `ls -lt backups/ | head -5`
6. If DB issue: check `docker compose logs db`
7. If app issue: check for OOM, restart: `docker compose restart app`
8. If data loss: restore from latest backup
9. If bad deploy: `make rollback`
