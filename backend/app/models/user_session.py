"""A signed-in device: what makes a login revocable.

The browser (or the phone) holds two things. A short-lived **access token**, a JWT that
carries this row's id (`sid`) and is checked against it on every request, and a long-lived
**refresh token**, opaque, of which only the SHA-256 is stored here. The access token is what
authorises a request; the refresh token only buys a new one.

Because every request looks the session up, ending it (logout, "sign out that device", a
password change, a stolen refresh token replayed) takes effect on the next request, not when a
24-hour token happens to expire.

Rotation: each refresh replaces the refresh token. The previous hash is kept for a few seconds
so two tabs refreshing at once do not look like theft, and for long enough after that to
recognise a token that was replayed: that revokes the whole session.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class UserSession(Base):
    __tablename__ = "user_sessions"
    __table_args__ = (
        Index("ix_user_sessions_refresh_hash", "refresh_hash", unique=True),
        Index("ix_user_sessions_previous_refresh_hash", "previous_refresh_hash"),
        Index("ix_user_sessions_user_active", "user_id", "revoked_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    refresh_hash: Mapped[str] = mapped_column(String(64))
    previous_refresh_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    rotated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    #: The last time a request used this session (updated at most once a minute).
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    #: The last time the refresh token was used: what the idle timeout counts from.
    last_refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    #: Absolute end of life, however active the session is.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    #: logout | revoked_by_user | password_changed | refresh_reuse | expired
    revoked_reason: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

    ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    #: "Firefox on Windows": something a person recognises in a list of their devices.
    device_label: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    #: password | 2fa | passkey | oidc | setup
    auth_method: Mapped[str] = mapped_column(String(20), default="password")
    #: This session has proved a second factor (see services/mfa_policy.py). A password-only session
    #: becomes verified when its owner completes enrolling an authenticator or a passkey.
    mfa_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
