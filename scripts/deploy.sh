#!/usr/bin/env bash
# =============================================================================
# Deploy: pull and run a specific IMAGE_TAG, with rollback on failure
#
# Records deployment history so rollback.sh can revert to the previous tag.
# WHY explicit tag: never rely on :latest for production deploys.
# =============================================================================
set -euo pipefail

COMPOSE="docker compose -f deploy/docker-compose.yml"
HISTORY_FILE=".deployed_tags"

if [ $# -lt 1 ]; then
    echo "Usage: $0 <image_tag>"
    echo "Example: $0 v1.0.0"
    exit 1
fi

NEW_TAG="$1"
CURRENT_TAG=""

# Read current tag from history
if [ -f "$HISTORY_FILE" ]; then
    CURRENT_TAG=$(tail -1 "$HISTORY_FILE" | cut -d'|' -f2)
fi

echo "=== Deploying IMAGE_TAG=$NEW_TAG ==="
echo "Previous tag: ${CURRENT_TAG:-none}"

# Record deployment
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)|$NEW_TAG" >> "$HISTORY_FILE"

# Deploy with new tag
export IMAGE_TAG="$NEW_TAG"
export APP_IMAGE="ghcr.io/sanyambedi/hospital-management-platform:$NEW_TAG"
$COMPOSE up -d 2>/dev/null || true

# Wait for services to be healthy
echo "Waiting for services to become healthy..."
for i in $(seq 1 30); do
    STATUS=$(curl -ks https://localhost/healthz | jq -r .status 2>/dev/null || true)
    if [ "$STATUS" = "ok" ]; then break; fi
    sleep 1
done

# Run smoke test
echo "Running smoke test..."
if bash scripts/smoke_test.sh; then
    echo "✓ Deploy successful: $NEW_TAG"
    # Print running image info
    $COMPOSE ps
else
    echo "✗ Smoke test FAILED for $NEW_TAG"
    if [ -n "$CURRENT_TAG" ]; then
        echo "Auto-rolling back to $CURRENT_TAG..."
        export IMAGE_TAG="$CURRENT_TAG"
        export APP_IMAGE="ghcr.io/sanyambedi/hospital-management-platform:$CURRENT_TAG"
        $COMPOSE up -d 2>/dev/null || true
        for i in $(seq 1 30); do
            STATUS=$(curl -ks https://localhost/healthz | jq -r .status 2>/dev/null || true)
            if [ "$STATUS" = "ok" ]; then break; fi
            sleep 1
        done
        if bash scripts/smoke_test.sh; then
            echo "✓ Rollback to $CURRENT_TAG successful"
        else
            echo "✗ Rollback also failed! Manual intervention needed."
            exit 1
        fi
    else
        echo "No previous tag to roll back to."
        exit 1
    fi
fi

echo "=== Deploy complete ==="
