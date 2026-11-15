#!/usr/bin/env bash
# =============================================================================
# Demo: full end-to-end demonstration in one command
#
# Runs on a clean checkout:
# init secrets → compose up → seed → smoke → concurrency proof →
# backup/restore drill → failure drill → summary table
#
# WHY: proves every claim in the README with real script output
# =============================================================================
set -euo pipefail

COMPOSE="docker compose -f deploy/docker-compose.yml"
BASE_URL="${BASE_URL:-https://localhost}"

RESULTS=()
NAMES=()

run_step() {
    local name="$1"
    shift
    echo ""
    echo "╔══════════════════════════════════════════════╗"
    echo "  $name"
    echo "╚══════════════════════════════════════════════╝"
    echo ""
    NAMES+=("$name")
    if "$@"; then
        RESULTS+=("PASS")
        echo ""
        echo "  → $name: PASS"
    else
        RESULTS+=("FAIL")
        echo ""
        echo "  → $name: FAIL"
    fi
}

echo "╔══════════════════════════════════════════════════╗"
echo "║  Hospital Appointment API – Full Demo            ║"
echo "║  $(date -u +%Y-%m-%dT%H:%M:%SZ)                          ║"
echo "╚══════════════════════════════════════════════════╝"

# Step 1: Init secrets
run_step "Init Secrets" make init-secrets

# Step 2: Build and start
echo ""
echo "Building and starting stack..."
$COMPOSE build --quiet 2>/dev/null || true
export RUN_SEED=true
$COMPOSE up -d --wait 2>&1 || true
sleep 10

# Check if services are running
if $COMPOSE ps | grep -q "healthy"; then
    NAMES+=("Stack Up")
    RESULTS+=("PASS")
    echo "  → Stack Up: PASS"
else
    NAMES+=("Stack Up")
    RESULTS+=("FAIL")
    echo "  → Stack Up: FAIL"
fi

# Step 3: Seed data
run_step "Seed Data" $COMPOSE exec -T app python -m app.seed

# Step 4: Smoke test
run_step "Smoke Test" bash scripts/smoke_test.sh

# Step 5: Concurrency proof
run_step "Concurrency Proof" python3 scripts/concurrency_proof.py

# Step 6: Backup/restore drill
run_step "Backup/Restore Drill" bash scripts/drill_backup_restore.sh

# Step 7: Failure drill
run_step "Failure/Recovery Drill" bash scripts/drill_failure.sh

# Print running image info
echo ""
echo "--- Running Image ---"
$COMPOSE ps 2>/dev/null || true

# Summary table
echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║              DEMO SUMMARY                        ║"
echo "╠══════════════════════════════════════════════════╣"
OVERALL="PASS"
for i in "${!NAMES[@]}"; do
    status="${RESULTS[$i]}"
    name="${NAMES[$i]}"
    if [ "$status" == "PASS" ]; then
        printf "║  ✓ %-40s %s ║\n" "$name" "$status"
    else
        printf "║  ✗ %-40s %s ║\n" "$name" "$status"
        OVERALL="FAIL"
    fi
done
echo "╠══════════════════════════════════════════════════╣"
echo "║  OVERALL: $OVERALL                                      ║"
echo "╚══════════════════════════════════════════════════╝"

# Cleanup
echo ""
echo "Cleaning up..."
$COMPOSE down -v 2>/dev/null || true

[ "$OVERALL" == "PASS" ] || exit 1
