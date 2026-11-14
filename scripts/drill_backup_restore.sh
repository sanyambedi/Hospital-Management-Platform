#!/usr/bin/env bash
# =============================================================================
# Automated Backup/Restore Drill with Evidence Logging
#
# Proves: backup → destroy → restore → data intact (matching checksums)
# Writes evidence to docs/evidence/backup-restore.log
#
# WHY automated: reviewers can re-run this to verify the claim themselves.
# =============================================================================
set -euo pipefail

COMPOSE="docker compose -f deploy/docker-compose.yml"
LOG_FILE="docs/evidence/backup-restore.log"
BASE_URL="${BASE_URL:-https://localhost}"
CURL_OPTS="-k --silent --show-error --max-time 10"

mkdir -p docs/evidence

exec > >(tee "$LOG_FILE") 2>&1

echo "=============================================="
echo "  BACKUP/RESTORE DRILL"
echo "  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "=============================================="
echo ""

# Step 1: Capture baseline data
echo "--- Step 1: Capture baseline ---"
ROW_COUNT_BEFORE=$($COMPOSE exec -T db psql -U hospital -d hospital -t -c \
    "SELECT COUNT(*) FROM appointments;" 2>/dev/null | tr -d ' \n\r')
CHECKSUM_BEFORE=$($COMPOSE exec -T db psql -U hospital -d hospital -t -c \
    "SELECT COALESCE(md5(string_agg(id::text, ',' ORDER BY id)), 'empty') FROM appointments;" 2>/dev/null | tr -d ' \n\r')
echo "Appointments before: $ROW_COUNT_BEFORE"
echo "Checksum before:     $CHECKSUM_BEFORE"
echo ""

# Step 2: Run backup
echo "--- Step 2: Run backup ---"
bash scripts/backup.sh
LATEST_DUMP=$(ls -1t backups/hospital_*.dump 2>/dev/null | head -1)
echo "Latest dump: $LATEST_DUMP"
echo ""

# Step 3: Destroy data
echo "--- Step 3: Destroy data (TRUNCATE appointments) ---"
$COMPOSE exec -T db psql -U hospital -d hospital -c "TRUNCATE appointments CASCADE;" 2>/dev/null
ROW_COUNT_DESTROYED=$($COMPOSE exec -T db psql -U hospital -d hospital -t -c \
    "SELECT COUNT(*) FROM appointments;" 2>/dev/null | tr -d ' \n\r')
echo "Appointments after destroy: $ROW_COUNT_DESTROYED"
echo ""

# Step 4: Show broken state
echo "--- Step 4: Show broken state ---"
READYZ_CODE=$(curl $CURL_OPTS -o /dev/null -w "%{http_code}" "$BASE_URL/readyz") || READYZ_CODE="000"
echo "/readyz status: $READYZ_CODE (app still running, data gone)"
echo ""

# Step 5: Restore
echo "--- Step 5: Restore from backup ---"
bash scripts/restore.sh "$LATEST_DUMP" --yes
echo ""

# Step 6: Verify data integrity
echo "--- Step 6: Verify data integrity ---"
ROW_COUNT_AFTER=$($COMPOSE exec -T db psql -U hospital -d hospital -t -c \
    "SELECT COUNT(*) FROM appointments;" 2>/dev/null | tr -d ' \n\r')
CHECKSUM_AFTER=$($COMPOSE exec -T db psql -U hospital -d hospital -t -c \
    "SELECT COALESCE(md5(string_agg(id::text, ',' ORDER BY id)), 'empty') FROM appointments;" 2>/dev/null | tr -d ' \n\r')
echo "Appointments after restore:  $ROW_COUNT_AFTER"
echo "Checksum after restore:      $CHECKSUM_AFTER"
echo ""

# Step 7: Assert
echo "--- Result ---"
if [ "$ROW_COUNT_BEFORE" == "$ROW_COUNT_AFTER" ] && [ "$CHECKSUM_BEFORE" == "$CHECKSUM_AFTER" ]; then
    echo "✓ PASS: Row count and checksum match"
    echo "  Before:  count=$ROW_COUNT_BEFORE checksum=$CHECKSUM_BEFORE"
    echo "  After:   count=$ROW_COUNT_AFTER  checksum=$CHECKSUM_AFTER"
    RESULT="PASS"
else
    echo "✗ FAIL: Data mismatch"
    echo "  Before:  count=$ROW_COUNT_BEFORE checksum=$CHECKSUM_BEFORE"
    echo "  After:   count=$ROW_COUNT_AFTER  checksum=$CHECKSUM_AFTER"
    RESULT="FAIL"
fi

echo ""
echo "=============================================="
echo "  DRILL RESULT: $RESULT"
echo "  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "=============================================="

[ "$RESULT" == "PASS" ] || exit 1
