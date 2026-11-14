#!/usr/bin/env bash
# =============================================================================
# Restore: restore a pg_dump file after verifying its checksum
#
# WHY explicit file + --yes flag: prevents accidental restores.
# WHY checksum verification: ensures the dump hasn't been corrupted.
# =============================================================================
set -euo pipefail

COMPOSE="docker compose -f deploy/docker-compose.yml"

if [ $# -lt 2 ] || [ "$2" != "--yes" ]; then
    echo "Usage: $0 <dump_file> --yes"
    echo "Refuses to run without an explicit file and --yes confirmation."
    exit 1
fi

DUMP_FILE="$1"

if [ ! -f "$DUMP_FILE" ]; then
    echo "ERROR: Dump file not found: $DUMP_FILE"
    exit 1
fi

# Verify checksum if .sha256 file exists
if [ -f "${DUMP_FILE}.sha256" ]; then
    echo "Verifying checksum..."
    if sha256sum -c "${DUMP_FILE}.sha256"; then
        echo "✓ Checksum verified"
    else
        echo "✗ CHECKSUM MISMATCH — aborting restore!"
        exit 1
    fi
else
    echo "⚠ No .sha256 file found, skipping checksum verification"
fi

echo "=== Database Restore ==="
echo "File: $DUMP_FILE"

# Stop app (keep db up for restore)
echo "Stopping app..."
$COMPOSE stop app 2>/dev/null || true

# Restore using pg_restore with --clean to drop and recreate objects
echo "Restoring database..."
cat "$DUMP_FILE" | $COMPOSE exec -T db pg_restore -U hospital -d hospital --clean --if-exists 2>/dev/null || true

# Run migrations to ensure schema is at head (in case restore is from an older version)
echo "Running migrations..."
$COMPOSE run --rm migrate

# Start app
echo "Starting app..."
$COMPOSE start app

# Wait for app to become healthy
echo "Waiting for app to become healthy..."
sleep 5

# Run smoke test to verify
echo "Running smoke test..."
bash scripts/smoke_test.sh && echo "✓ Restore verified by smoke test" || echo "✗ Smoke test failed after restore"

echo "=== Restore complete ==="
