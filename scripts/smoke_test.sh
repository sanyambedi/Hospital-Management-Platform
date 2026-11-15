#!/usr/bin/env bash
# =============================================================================
# Smoke test: quick health checks against the running stack
# Used by CI, drills, and make smoke
#
# WHY: automated verification that the stack is working end-to-end
# =============================================================================
set -euo pipefail

BASE_URL="${BASE_URL:-https://localhost}"
CURL_OPTS="${CURL_OPTS:--k --silent --show-error --max-time 10}"

PASS=0
FAIL=0

check() {
    local name="$1"
    local expected_code="$2"
    local method="${3:-GET}"
    local url="$4"
    local data="${5:-}"
    local extra_headers="${6:-}"

    local args=($CURL_OPTS -o /dev/null -w "%{http_code}" -X "$method")

    if [ -n "$extra_headers" ]; then
        args+=(-H "$extra_headers")
    fi
    if [ -n "$data" ]; then
        args+=(-H "Content-Type: application/json" -d "$data")
    fi

    local actual_code
    actual_code=$(curl "${args[@]}" "$url") || actual_code="000"

    if [ "$actual_code" == "$expected_code" ]; then
        echo "  ✓ $name (HTTP $actual_code)"
        PASS=$((PASS + 1))
    else
        echo "  ✗ $name (expected $expected_code, got $actual_code)"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== Smoke Test ==="
echo ""

# Health endpoints
check "healthz" "200" "GET" "$BASE_URL/healthz"
check "readyz"  "200" "GET" "$BASE_URL/readyz"

# Auth: login with seed credentials
SEED_PASSWORD="${SEED_PASSWORD:-$(cat secrets/seed_password.txt 2>/dev/null || echo '')}"
if [ -n "$SEED_PASSWORD" ]; then
    # Login
    LOGIN_RESP=$(curl $CURL_OPTS -X POST "$BASE_URL/auth/login" \
        -H "Content-Type: application/json" \
        -d "{\"email\":\"patient01@synthetic.local\",\"password\":\"$SEED_PASSWORD\"}" 2>/dev/null) || LOGIN_RESP=""

    TOKEN=$(echo "$LOGIN_RESP" | python -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null) || TOKEN=""

    if [ -n "$TOKEN" ]; then
        echo "  ✓ login (got token)"
        PASS=$((PASS + 1))

        # List doctors
        check "list_doctors" "200" "GET" "$BASE_URL/doctors" "" "Authorization: Bearer $TOKEN"

        # Get a doctor ID
        DOCTOR_ID=$(curl $CURL_OPTS "$BASE_URL/doctors" \
            -H "Authorization: Bearer $TOKEN" 2>/dev/null \
            | python -c "import sys,json; docs=json.load(sys.stdin); print(docs[0]['id'] if docs else '')" 2>/dev/null) || DOCTOR_ID=""

        # Create appointment (query an available weekday slot dynamically)
        DATE_CANDIDATE=$(python -c "
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
tz = ZoneInfo('Asia/Kolkata')
now = datetime.now(tz)
candidate = now + timedelta(days=1)
while candidate.weekday() >= 5:
    candidate += timedelta(days=1)
print(candidate.strftime('%Y-%m-%d'))
" 2>/dev/null)

        SLOT_START=""
        if [ -n "$DOCTOR_ID" ] && [ -n "$DATE_CANDIDATE" ]; then
            SLOT_START=$(curl $CURL_OPTS "$BASE_URL/doctors/$DOCTOR_ID/slots?date=$DATE_CANDIDATE" \
                -H "Authorization: Bearer $TOKEN" 2>/dev/null \
                | python -c "import sys,json; slots=json.load(sys.stdin); print(slots[0]['slot_start'] if slots else '')" 2>/dev/null) || SLOT_START=""
        fi

        if [ -z "$SLOT_START" ]; then
            SLOT_START=$(python -c "
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import random
tz = ZoneInfo('Asia/Kolkata')
candidate = datetime.now(tz) + timedelta(days=random.randint(5, 25))
while candidate.weekday() >= 5:
    candidate += timedelta(days=1)
print(candidate.replace(hour=14, minute=0, second=0, microsecond=0).isoformat())
" 2>/dev/null)
        fi

        if [ -n "$DOCTOR_ID" ] && [ -n "$SLOT_START" ]; then
            # Create appointment
            CREATE_CODE=$(curl $CURL_OPTS -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/appointments" \
                -H "Authorization: Bearer $TOKEN" \
                -H "Content-Type: application/json" \
                -d "{\"doctor_id\":\"$DOCTOR_ID\",\"slot_start\":\"$SLOT_START\",\"reason\":\"smoke test\"}" 2>/dev/null) || CREATE_CODE="000"

            if [ "$CREATE_CODE" == "201" ]; then
                echo "  ✓ create_appointment (HTTP 201)"
                PASS=$((PASS + 1))

                # Try to book the same slot again → should get 409
                check "double_booking_409" "409" "POST" "$BASE_URL/appointments" \
                    "{\"doctor_id\":\"$DOCTOR_ID\",\"slot_start\":\"$SLOT_START\",\"reason\":\"duplicate\"}" \
                    "Authorization: Bearer $TOKEN"
            else
                echo "  ✗ create_appointment (expected 201, got $CREATE_CODE)"
                FAIL=$((FAIL + 1))
            fi
        else
            echo "  ⚠ skipped appointment tests (no doctor or slot)"
        fi
    else
        echo "  ✗ login (no token received)"
        FAIL=$((FAIL + 1))
    fi
else
    echo "  ⚠ skipped auth tests (SEED_PASSWORD not available)"
fi

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
