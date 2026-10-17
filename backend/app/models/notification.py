"""Something the system wants a person to know, kept until they have seen it.

One row per recipient. A budget that goes over is a fact about the
workspace, but *being told* is a fact about a person: one member can have
read it while another has not, and dismissing it for yourself must not make
it disappear for everyone else.

`dedupe_key` is what makes the generators safe to run every hour. It names
the *situation*, not the moment: `budget:<category>:2026-03:over` is the same
situation on the first run and the twentieth, so the second run finds the row
and says nothing. When the situation changes (a new month, a new due date)
the key changes and the person is told again, which is the point.
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

#: Severities, in the order the UI ranks them.
SEVERITIES = ("info", "warning", "critical")


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "dedupe_key", name="uq_notification_user_dedupe"),
        # The bell asks one question: what is unread for me, newest first.
        Index("ix_notifications_inbox", "user_id", "workspace_id", "read_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    #: budget_over | budget_warning | invoice_due | invoice_overdue |
    #: sync_failed | cashflow_negative
    kind: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(10), default="info")
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    #: Where the UI should send the person: a route plus any ids.
    data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True, default=dict)
    dedupe_key: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Set once the external channels (e-mail / webhook) have been attempted,
    #: so a retry of the job never sends the same message twice.
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
