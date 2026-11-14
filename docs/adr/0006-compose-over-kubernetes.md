# ADR-0006: Docker Compose instead of Kubernetes

**Context**: The system needs container orchestration. Options: Docker Compose, Kubernetes, Nomad, plain Docker.

**Decision**: Use Docker Compose v2. Single-node deployment is sufficient for this project scope.

**Consequences**: Simple to operate, debug, and explain in an interview. No cluster management overhead. Compose handles service dependencies, health checks, restart policies, and secret mounting. Trade-off: no HA, no auto-scaling, no multi-node. For production scale, migrate to Kubernetes — the Dockerfile, health checks, and secrets pattern transfer directly.
