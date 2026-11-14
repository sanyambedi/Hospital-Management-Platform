# ADR-0005: Deploy by immutable tag/digest with rollback history

**Context**: Deploying with `:latest` is unpredictable — you don't know what version is running. Rollback requires knowing what was running before.

**Decision**: `deploy.sh` takes an explicit `IMAGE_TAG`, records it in `.deployed_tags` history (timestamped), and auto-rolls back if the smoke test fails. `rollback.sh` reads the previous tag from history.

**Consequences**: Every deployment is traceable. Rollback is one command. Auto-rollback on failure prevents broken deploys from staying live. The `:latest` tag exists for convenience but is never used for production deploys.
