# =============================================================================
# Hospital Appointment API – Multi-stage Dockerfile
#
# WHY multi-stage: separates build dependencies (compilers, pip) from the
# runtime image, resulting in a smaller, more secure final image.
# WHY non-root: principle of least privilege — if the process is
# compromised, the attacker cannot modify system files.
# =============================================================================

# --- Stage 1: Builder ---
# WHY python:3.12-slim: smallest official Python image that still has
# enough OS packages for pip to compile C extensions (argon2-cffi).
FROM python:3.12-slim AS builder

WORKDIR /build

# WHY separate COPY for requirements: Docker layer caching means we
# only re-install deps when requirements.txt changes, not on every
# code change.
COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# --- Stage 2: Runtime ---
FROM python:3.12-slim AS runtime

# Build args for OCI labels and version tracking
ARG APP_VERSION=0.1.0
ARG GIT_SHA=unknown

# OCI standard labels for image metadata
LABEL org.opencontainers.image.title="Hospital Appointment API" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.source="https://github.com/sanyambedi/Hospital-Management-Platform" \
      org.opencontainers.image.description="Small hospital appointment service with production-grade delivery"

# WHY these env vars:
# PYTHONDONTWRITEBYTECODE: prevents .pyc files (smaller image, read-only FS)
# PYTHONUNBUFFERED: ensures logs appear immediately in Docker logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_VERSION=${APP_VERSION}

WORKDIR /srv

# Copy only the virtualenv from the builder stage (no pip, no compilers)
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy only what's needed at runtime (no tests, docs, .git)
COPY app/ ./app/
COPY migrations/ ./migrations/
COPY alembic.ini .

# WHY create a non-root user with a fixed UID: security best practice.
# UID 10001 avoids conflicts with system users.
RUN groupadd -r appuser -g 10001 && \
    useradd -r -u 10001 -g appuser -s /usr/sbin/nologin appuser

USER 10001

# WHY Python-based healthcheck: no curl/wget in the slim image, so we
# use Python stdlib which is always available.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2); sys.exit(0)"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
