# ADR-0001: DB partial unique index for double-booking prevention

**Context**: Appointments must not double-book a doctor's time slot. App-level "check then insert" has a TOCTOU race condition under concurrent requests.

**Decision**: Use a PostgreSQL partial unique index: `CREATE UNIQUE INDEX uq_confirmed_doctor_slot ON appointments (doctor_id, slot_start) WHERE status = 'confirmed'`. App catches `IntegrityError` → HTTP 409.

**Consequences**: Double-booking is impossible even under concurrent load, direct SQL access, or app bugs. Proven by `test_concurrency.py` (20+ parallel requests → exactly 1 winner). Requires PostgreSQL (partial indexes are not universal SQL).
