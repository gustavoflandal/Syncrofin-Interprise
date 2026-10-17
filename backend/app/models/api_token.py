"""A credential for a program, not a person: an integration, a script, an accountant's tool.

It is tied to **one workspace** and to the **person who made it**, and it can do at most what that
person can do in that workspace, narrowed to the `scopes` it was given (permissions from
`core/permissions.py`, never the administrative ones). It always expires, and it can be revoked at any
moment. The token itself is shown once, when it is made: only its SHA-256 is stored, plus the first
characters (`prefix`) so a person can tell tokens apart in a list.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

TOKEN_PREFIX = "sfn_"


class ApiToken(Base):
    __tablename__ = "api_tokens"
    __table_args__ = (Index("ix_api_tokens_token_hash", "token_hash", unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    #: Who it acts as. If they leave the workspace or are deactivated, the token stops working.
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    #: `sfn_` and eight hex digits: enough to recognise a token, not to use it.
    prefix: Mapped[str] = mapped_column(String(20))
    token_hash: Mapped[str] = mapped_column(String(64))
    #: Permission keys the token may use, a subset of what its owner can do.
    scopes: Mapped[list[str]] = mapped_column(JSONB, default=list)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
