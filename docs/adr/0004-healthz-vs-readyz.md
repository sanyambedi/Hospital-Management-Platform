# ADR-0004: Separate /healthz (liveness) and /readyz (readiness)

**Context**: Container orchestrators and load balancers need to know: (a) is the process alive? (b) can it serve traffic?

**Decision**: Two endpoints: `/healthz` always returns 200 (no DB call); `/readyz` checks DB connectivity and returns 503 if unreachable.

**Consequences**: If DB goes down, the app stays running (no unnecessary restarts) but stops receiving traffic until DB recovers. Proven by the failure drill: DB stop → `/readyz` 503, `/healthz` 200, DB start → `/readyz` 200 (auto-recovery).
