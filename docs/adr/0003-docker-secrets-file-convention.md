# ADR-0003: Docker secrets via *_FILE convention

**Context**: Secrets (DB password, JWT key) must be available to the app but not exposed in env vars, docker inspect, or git history.

**Decision**: Use Docker Compose secrets (mounted files at `/run/secrets/`). App config reads `<NAME>_FILE` env vars pointing to file paths. Falls back to direct env var for local dev.

**Consequences**: Secrets are never visible in `docker inspect`, `/proc`, or the compose file. Same config.py works locally (env var) and in Docker (file). Requires the `_FILE` convention in `config.py`, which is 10 lines of code.
