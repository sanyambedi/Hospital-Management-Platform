#!/usr/bin/env bash
# =============================================================================
# Backup: pg_dump the database to a timestamped file with checksum
#
# WHY custom format (-Fc): compressed, supports selective restore,
# and is the recommended format for pg_restore.
# =============================================================================
set -euo pipefail

COMPOSE="docker compose -f deploy/docker-compose.yml"
BACKUP_DIR="backups"
BACKUP_KEEP="${BACKUP_KEEP:-7}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DUMP_FILE="$BACKUP_DIR/hospital_${TIMESTAMP}.dump"

mkdir -p "$BACKUP_DIR"

echo "=== Database Backup ==="
echo "Timestamp: $TIMESTAMP"

# WHY exec -T: no TTY allocation (works in scripts and CI)
$COMPOSE exec -T db pg_dump -U hospital -Fc hospital > "$DUMP_FILE"

# Generate checksum for integrity verification on restore
sha256sum "$DUMP_FILE" > "${DUMP_FILE}.sha256"

SIZE=$(du -h "$DUMP_FILE" | cut -f1)
echo "✓ Backup saved: $DUMP_FILE ($SIZE)"
echo "✓ Checksum: ${DUMP_FILE}.sha256"

# Rotate old backups: keep only the latest N
# WHY: prevents disk from filling up with old backups
BACKUP_COUNT=$(ls -1 "$BACKUP_DIR"/hospital_*.dump 2>/dev/null | wc -l)
if [ "$BACKUP_COUNT" -gt "$BACKUP_KEEP" ]; then
    REMOVE_COUNT=$((BACKUP_COUNT - BACKUP_KEEP))
    ls -1t "$BACKUP_DIR"/hospital_*.dump | tail -n "$REMOVE_COUNT" | while read -r old; do
        rm -f "$old" "${old}.sha256"
        echo "  Rotated: $old"
    done
fi

echo "=== Backup complete ==="
