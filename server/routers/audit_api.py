import asyncio
import contextlib

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select

from ..db import SessionLocal, get_db
from ..deps import require
from ..models import AuditEvent, utcnow
from ..schemas import AuditOut
from ..security.permissions import Perm
from ..security.tokens import Principal, TokenError, decode_access
from ..settings import settings

router = APIRouter(tags=["admin: audit"])

POLL_INTERVAL_S = 1.0
AUTH_TIMEOUT_S = 5.0

WS_UNAUTHORIZED = 4401
WS_FORBIDDEN = 4403


@router.get("/api/admin/audit", response_model=list[AuditOut])
def list_audit(limit: int = Query(300, ge=1, le=2000), before_seq: int | None = None,
               db=Depends(get_db), _: Principal = Depends(require(Perm.ADMIN))):
    q = select(AuditEvent).order_by(AuditEvent.seq.desc()).limit(limit)
    if before_seq is not None:
        q = q.where(AuditEvent.seq < before_seq)
    return list(reversed(db.scalars(q).all()))


def _events_after(seq: int) -> list[dict]:
    with SessionLocal() as db:
        rows = db.scalars(select(AuditEvent).where(AuditEvent.seq > seq)
                          .order_by(AuditEvent.seq).limit(500)).all()
        return [AuditOut.model_validate(r).model_dump(mode="json") for r in rows]


def _authorize(token: str) -> Principal:
    principal = decode_access(token)
    if not principal.can(Perm.ADMIN):
        raise PermissionError
    return principal


@router.websocket("/api/ws/audit")
async def audit_ws(ws: WebSocket):
    origin = ws.headers.get("origin")
    if origin is not None and origin not in settings.client_origins:
        await ws.close(code=WS_FORBIDDEN)
        return
    await ws.accept()

    try:
        first = await asyncio.wait_for(ws.receive_json(), AUTH_TIMEOUT_S)
        state = {"principal": _authorize(first.get("token", ""))}
        last_seq = int(first.get("after_seq") or 0)
    except PermissionError:
        await ws.close(code=WS_FORBIDDEN)
        return
    except (asyncio.TimeoutError, TokenError, ValueError, TypeError, AttributeError):
        await ws.close(code=WS_UNAUTHORIZED)
        return
    except WebSocketDisconnect:
        return
    await ws.send_json({"type": "ready"})

    async def reader():
        while True:
            msg = await ws.receive_json()
            if isinstance(msg, dict) and msg.get("type") == "auth":
                state["principal"] = _authorize(msg.get("token", ""))

    async def sender():
        nonlocal last_seq
        while True:
            if utcnow() >= state["principal"].expires_at:
                raise TokenError("expired")
            events = await run_in_threadpool(_events_after, last_seq)
            if events:
                await ws.send_json({"type": "events", "items": events})
                last_seq = events[-1]["seq"]
            await asyncio.sleep(POLL_INTERVAL_S)

    tasks = [asyncio.create_task(reader()), asyncio.create_task(sender())]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()
    exc = next(iter(done)).exception()
    code = WS_FORBIDDEN if isinstance(exc, PermissionError) else WS_UNAUTHORIZED
    if not isinstance(exc, WebSocketDisconnect):
        with contextlib.suppress(Exception):
            await ws.close(code=code)
