#!/usr/bin/env bash
# =============================================================================
# Rollback: redeploy the previous image tag from deployment history
#
# WHY: quick recovery when a deploy breaks something.
# =============================================================================
set -euo pipefail

COMPOSE="docker compose -f deploy/docker-compose.yml"
HISTORY_FILE=".deployed_tags"

if [ ! -f "$HISTORY_FILE" ] || [ $(wc -l < "$HISTORY_FILE") -lt 2 ]; then
    echo "ERROR: No previous deployment to roll back to."
    echo "Need at least 2 entries in $HISTORY_FILE"
    exit 1
fi

CURRENT_TAG=$(tail -1 "$HISTORY_FILE" | cut -d'|' -f2)
PREV_TAG=$(tail -2 "$HISTORY_FILE" | head -1 | cut -d'|' -f2)

echo "=== Rollback ==="
echo "Current: $CURRENT_TAG"
echo "Rolling back to: $PREV_TAG"

# Deploy previous tag
export IMAGE_TAG="$PREV_TAG"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)|$PREV_TAG" >> "$HISTORY_FILE"

$COMPOSE up -d --wait 2>/dev/null || true
sleep 5

# Verify with smoke test
if bash scripts/smoke_test.sh; then
    echo "✓ Rollback to $PREV_TAG successful"
    echo ""
    echo "Running image:"
    $COMPOSE ps
else
    echo "✗ Rollback to $PREV_TAG FAILED. Manual intervention needed."
    exit 1
fi

echo "=== Rollback complete ==="
