#!/usr/bin/env bash
# =============================================================================
# Automated Failure/Recovery Drill with Evidence Logging
#
# Tests: DB failure → readyz 503, healthz 200 → DB recovery → auto-heal
# Also: app kill → Docker restart policy recovery
# Writes evidence to docs/evidence/failure-drill.log
# =============================================================================
set -euo pipefail

COMPOSE="docker compose -f deploy/docker-compose.yml"
LOG_FILE="docs/evidence/failure-drill.log"
BASE_URL="${BASE_URL:-https://localhost}"
CURL_OPTS="-k --silent --show-error --max-time 10"

mkdir -p docs/evidence

exec > >(tee "$LOG_FILE") 2>&1

echo "=============================================="
echo "  FAILURE/RECOVERY DRILL"
echo "  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "=============================================="
echo ""

PASS=0
FAIL=0

check_status() {
    local name="$1"
    local url="$2"
    local expected="$3"
    local actual
    actual=$(curl $CURL_OPTS -o /dev/null -w "%{http_code}" "$url") || actual="000"
    if [ "$actual" == "$expected" ]; then
        echo "  ✓ $name: HTTP $actual (expected $expected)"
        PASS=$((PASS + 1))
    else
        echo "  ✗ $name: HTTP $actual (expected $expected)"
        FAIL=$((FAIL + 1))
    fi
}

# --- Step 1: Baseline ---
echo "--- Step 1: Baseline checks ---"
echo "Services:"
$COMPOSE ps 2>/dev/null || true
echo ""
check_status "healthz" "$BASE_URL/healthz" "200"
check_status "readyz" "$BASE_URL/readyz" "200"
echo ""

# --- Step 2: Kill DB ---
echo "--- Step 2: Kill database ---"
$COMPOSE stop db
echo "DB stopped at $(date -u +%H:%M:%S)"
sleep 3

echo "After DB kill:"
check_status "healthz (should still be 200)" "$BASE_URL/healthz" "200"
check_status "readyz (should be 503)" "$BASE_URL/readyz" "503"
echo ""

# Show app logs with DB error
echo "App logs showing DB error:"
$COMPOSE logs --tail=5 app 2>/dev/null || true
echo ""

# --- Step 3: Restart DB, verify recovery ---
echo "--- Step 3: Restart database ---"
$COMPOSE start db
echo "DB started at $(date -u +%H:%M:%S)"
echo "Waiting for DB to become healthy..."
for i in $(seq 1 30); do
    code=$($COMPOSE exec -T db pg_isready -U hospital -d hospital 2>/dev/null && echo "ok" || echo "not_ok")
    if [ "$code" = "ok" ]; then
        break
    fi
    sleep 1
done
sleep 2

echo "After DB recovery:"
check_status "readyz (should recover to 200)" "$BASE_URL/readyz" "200"

# Verify data is still intact (persistent volume)
ROW_COUNT=$($COMPOSE exec -T db psql -U hospital -d hospital -t -c \
    "SELECT COUNT(*) FROM doctors;" 2>/dev/null | tr -d ' \n\r')
if [ -n "$ROW_COUNT" ] && [ "$ROW_COUNT" -gt 0 ] 2>/dev/null; then
    echo "  ✓ Data intact after DB restart ($ROW_COUNT doctors)"
    PASS=$((PASS + 1))
else
    echo "  ✗ Data check failed after DB restart"
    FAIL=$((FAIL + 1))
fi
echo ""

# --- Step 4: Kill app container ---
echo "--- Step 4: Kill app container ---"
APP_CONTAINER=$($COMPOSE ps -q app 2>/dev/null)
if [ -n "$APP_CONTAINER" ]; then
    # WHY kill from the HOST: the slim image has no `kill` binary, and `docker kill`/`docker stop`
    # are treated by Docker as an intentional stop (restart policy would not fire). SIGKILL on
    # the container's main process simulates a real crash, so the restart policy must recover it.
    APP_PID=$(docker inspect -f '{{.State.Pid}}' "$APP_CONTAINER")
    RESTARTS_BEFORE=$(docker inspect -f '{{.RestartCount}}' "$APP_CONTAINER")
    echo "App container main PID (host): $APP_PID | restart count before: $RESTARTS_BEFORE"
    if sudo -n kill -9 "$APP_PID" 2>/dev/null || kill -9 "$APP_PID" 2>/dev/null; then
        echo "App process SIGKILLed at $(date -u +%H:%M:%S)"
    else
        echo "  ✗ Could not kill app process"
        FAIL=$((FAIL + 1))
    fi

    echo "Waiting for Docker restart policy (unless-stopped) to bring it back. No manual restart..."
    RECOVERED=false
    for i in $(seq 1 60); do
        code_h=$(curl $CURL_OPTS -o /dev/null -w "%{http_code}" "$BASE_URL/healthz" 2>/dev/null || echo "000")
        code_r=$(curl $CURL_OPTS -o /dev/null -w "%{http_code}" "$BASE_URL/readyz" 2>/dev/null || echo "000")
        if [ "$code_h" = "200" ] && [ "$code_r" = "200" ]; then
            echo "  ✓ App restarted by Docker and healthy after ~${i}s"
            RECOVERED=true
            break
        fi
        sleep 1
    done

    RESTARTS_AFTER=$(docker inspect -f '{{.RestartCount}}' "$APP_CONTAINER" 2>/dev/null || echo "?")
    echo "Restart count after: $RESTARTS_AFTER (before: $RESTARTS_BEFORE)"
    if [ "$RECOVERED" = true ] && [ "$RESTARTS_AFTER" != "$RESTARTS_BEFORE" ]; then
        echo "  ✓ Docker restart policy recovered the app automatically"
        PASS=$((PASS + 1))
    else
        echo "  ✗ App was NOT recovered by the restart policy"
        FAIL=$((FAIL + 1))
    fi

    echo "After app restart:"
    check_status "healthz (should recover)" "$BASE_URL/healthz" "200"
    check_status "readyz (should recover)" "$BASE_URL/readyz" "200"

    RECOVERY_TIME=$(date -u +%H:%M:%S)
    echo "  Recovery detected at $RECOVERY_TIME"
else
    echo "  ⚠ Could not find app container to kill"
fi
echo ""

# --- Summary ---
echo "=============================================="
echo "  DRILL RESULTS"
echo "  Passed: $PASS"
echo "  Failed: $FAIL"
if [ "$FAIL" -eq 0 ]; then
    echo "  OVERALL: PASS"
else
    echo "  OVERALL: FAIL"
fi
echo "  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "=============================================="

[ "$FAIL" -eq 0 ] || exit 1
