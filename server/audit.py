from fastapi import Request
from sqlalchemy.orm import Session

from .models import AuditEvent
from .security.tokens import Principal

SYSTEM_ACTOR = "system:server"


def client_ip(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    return request.client.host


def anonymous_actor(request: Request | None) -> str:
    return f"anonymous:{client_ip(request) or 'unknown'}"


def write(db: Session, *, action: str, message: str, request: Request | None = None,
          principal: Principal | None = None, actor: str | None = None,
          actor_name: str | None = None) -> AuditEvent:
    if principal is not None:
        actor = principal.actor
        actor_name = actor_name or f"{principal.username} ({principal.role})"
    event = AuditEvent(
        actor=actor or anonymous_actor(request),
        actor_name=actor_name,
        source_ip=client_ip(request),
        action=action,
        message=message,
    )
    db.add(event)
    return event


def changes_text(before: dict, after: dict) -> str:
    parts = [f"{k}: {before.get(k)!s} → {after.get(k)!s}"
             for k in after if before.get(k) != after.get(k)]
    return "; ".join(parts) or "без изменений"
