"""A titular's request under LGPD art. 18: access, portability, correction or erasure.

Distinct from `audit_events`: this table is the operational ticket (has a lifecycle — created, maybe
pending, eventually resolved), not the permanent legal trail. Its own create/update is itself audited
through the generic mechanism (`core/audit.py`, `AUDITED`), which is what actually survives the person
being erased: this row's FK to `users.id` cascades away with them on purpose.
"""
import random
import string
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import get_settings
from app.core.database import Base

KINDS = ("access", "portability", "correction", "erasure")
STATUSES = ("resolved_auto", "pending", "resolved_manual", "rejected")

_KIND_LIST_SQL = "'" + "', '".join(KINDS) + "'"
_STATUS_LIST_SQL = "'" + "', '".join(STATUSES) + "'"


def generate_protocol() -> str:
    """`DSR-{year}-{6 random digits}`. Not sequential on purpose: a sequence would need a lock or a
    Postgres SEQUENCE shared with the migration; six random digits collide rarely enough that the
    unique constraint (not this function) is what actually guarantees uniqueness, and the one-in-a-
    million retry belongs to the caller, not here."""
    year = datetime.now(timezone.utc).year
    digits = "".join(random.choices(string.digits, k=6))
    return f"DSR-{year}-{digits}"


class DataSubjectRequest(Base):
    __tablename__ = "data_subject_requests"
    __table_args__ = (
        CheckConstraint(f"kind IN ({_KIND_LIST_SQL})", name="ck_data_subject_requests_kind"),
        CheckConstraint(f"status IN ({_STATUS_LIST_SQL})", name="ck_data_subject_requests_status"),
        Index("ix_data_subject_requests_user_time", "user_id", "created_at"),
        Index("ix_data_subject_requests_due", "due_at", postgresql_where=text("status = 'pending'")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    protocol: Mapped[str] = mapped_column(String(20), unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=text("now()")
    )
    due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc) + timedelta(days=get_settings().data_request_deadline_days),
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolution_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
