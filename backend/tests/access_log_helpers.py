"""Building audit events of any age for the access-log tests."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import Table, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import seal
from app.models.audit import AuditEvent

#: Default for `actor_user_id`: a fresh person nobody else shares (pass None for "no actor").
RANDOM: object = object()


async def add_event(
    session: AsyncSession,
    *,
    action: str = "login",
    age_days: float = 0,
    actor_user_id: object = RANDOM,
    actor_kind: str = "user",
    entity_type: str = "user_session",
    entity_id: str | None = "e1",
    workspace_id: uuid.UUID | None = None,
    ip: str | None = "198.51.100.7",
    user_agent: str | None = "Firefox",
    detail: str | None = "password",
    seal_it: bool = True,
) -> uuid.UUID:
    """Insert one event `age_days` old, and (by default) seal it into the chain."""
    event_id = uuid.uuid4()
    actor = uuid.uuid4() if actor_user_id is RANDOM else actor_user_id
    table = AuditEvent.__table__
    assert isinstance(table, Table)
    await session.execute(
        insert(table).values(
            id=event_id,
            occurred_at=datetime.now(timezone.utc) - timedelta(days=age_days),
            actor_user_id=actor,
            actor_kind=actor_kind,
            workspace_id=workspace_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            ip=ip,
            user_agent=user_agent,
            request_id="req-1",
            detail=detail,
        )
    )
    await session.commit()
    if seal_it:
        await seal(session)
    return event_id
