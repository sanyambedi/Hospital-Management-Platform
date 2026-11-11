"""
Audit event helper.

WHY dual write (DB + log): the DB row is queryable and survives log
rotation; the structured log line enables real-time streaming to ELK/Loki.
Both carry the same request_id for correlation.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy.orm import Session

from app.models import AuditEvent

logger = structlog.get_logger()


def log_audit_event(
    db: Session,
    *,
    action: str,
    actor_user_id: uuid.UUID | str | None = None,
    actor_role: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    request_id: str | None = None,
    details: dict | None = None,
) -> AuditEvent:
    """Write an audit event to the DB and emit a structured log line.

    Parameters match the audit_events table columns.  The caller should
    commit the session (usually happens at the end of the request).
    """
    event = AuditEvent(
        actor_user_id=uuid.UUID(str(actor_user_id)) if actor_user_id else None,
        actor_role=actor_role,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id else None,
        request_id=request_id,
        details=details,
    )
    db.add(event)

    # Also emit a structured log line for real-time observability
    logger.info(
        "audit_event",
        action=action,
        actor_user_id=str(actor_user_id) if actor_user_id else None,
        actor_role=actor_role,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id else None,
        request_id=request_id,
        details=details,
    )

    return event
