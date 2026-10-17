"""The instance's rule about second factors, and who it blocks.

An administrator can require two-factor authentication. Turning it on does not lock anyone out at
once: `mfa_enforced_from` is set `mfa_grace_days` ahead, and until then people are only reminded.
After it, a **session** that has not proved a second factor can do nothing but enrol one.

What counts as proof, per session (`UserSession.mfa_verified`):

- signing in with a code from the authenticator app, or with a passkey (possession plus the phone's
  unlock), or through the company's identity provider (OIDC, which has its own MFA);
- or, for a session that signed in with the password alone, *completing the enrolment*: typing the
  first code from the new authenticator, or registering a passkey, shows the person holds the device.

So the person who is asked to enrol is let in as soon as they have. Nothing here trusts a flag the
client sends.

Two ways to switch it on: the environment (`REQUIRE_MFA=true`, enforced at once, not something the
panel can undo), and the panel (`mfa_required`, with a scope and a grace period).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.app_settings import AppSetting
from app.models.user import User

#: Sessions opened by these methods carry a second factor from the start.
VERIFIED_METHODS = ("2fa", "passkey", "oidc", "saml")

SCOPES = ("all", "admins")
MAX_GRACE_DAYS = 90

#: The one thing a person who is not yet allowed in may do: enrol, look at their sessions, sign out.
#: (method, path); a path ending in "/" matches by prefix.
ENROLMENT_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/api/users/me"),
        ("GET", "/api/auth/mfa-status"),
        ("POST", "/api/auth/2fa/setup"),
        ("POST", "/api/auth/2fa/enable"),
        ("GET", "/api/auth/passkeys"),
        ("POST", "/api/auth/passkeys/register/options"),
        ("POST", "/api/auth/passkeys/register/verify"),
        ("GET", "/api/auth/sessions"),
        ("POST", "/api/auth/sessions/revoke-others"),
        ("DELETE", "/api/auth/sessions/"),
    }
)

_KEYS = ("mfa_required", "mfa_required_scope", "mfa_enforced_from", "mfa_grace_days")


@dataclass(frozen=True)
class MfaPolicy:
    required: bool = False
    scope: str = "all"
    #: None means "already in force".
    enforced_from: datetime | None = None
    grace_days: int = 7
    #: True when `REQUIRE_MFA` is set: the panel cannot lift it.
    from_environment: bool = False

    def applies_to(self, user: User) -> bool:
        if not self.required:
            return False
        return self.scope == "all" or user.is_superuser

    def enforced(self, now: datetime | None = None) -> bool:
        if not self.required:
            return False
        return self.enforced_from is None or (now or datetime.now(timezone.utc)) >= self.enforced_from


@dataclass(frozen=True)
class MfaStatus:
    #: The rule is on and covers this person.
    applies: bool
    #: The rule is in force now (not only announced).
    enforced: bool
    #: This session has proved a second factor.
    session_verified: bool
    #: This person has an authenticator app set up.
    enrolled: bool
    #: When enforcement starts, for the reminder during the grace period.
    enforced_from: datetime | None
    from_environment: bool

    @property
    def blocked(self) -> bool:
        """The person can only enrol: the rule is in force and this session has no second factor."""
        return self.applies and self.enforced and not self.session_verified

    @property
    def reminder(self) -> bool:
        """The rule is announced, not yet in force, and this session has no second factor."""
        return self.applies and not self.enforced and not self.session_verified


async def load_policy(db: AsyncSession) -> MfaPolicy:
    settings = get_settings()
    rows = {
        row.key: row.value
        for row in (await db.execute(select(AppSetting).where(AppSetting.key.in_(_KEYS)))).scalars()
    }
    try:
        grace = max(0, min(int(rows.get("mfa_grace_days", settings.mfa_grace_days)), MAX_GRACE_DAYS))
    except ValueError:
        grace = settings.mfa_grace_days
    scope = rows.get("mfa_required_scope", "all")
    if scope not in SCOPES:
        scope = "all"
    if settings.require_mfa:
        return MfaPolicy(required=True, scope="all", enforced_from=None, grace_days=grace, from_environment=True)
    enforced_from: datetime | None = None
    if raw := rows.get("mfa_enforced_from"):
        try:
            enforced_from = datetime.fromisoformat(raw)
        except ValueError:
            enforced_from = None  # unreadable: treat as in force, the safe reading
    return MfaPolicy(
        required=rows.get("mfa_required", "false").lower() == "true",
        scope=scope,
        enforced_from=enforced_from,
        grace_days=grace,
    )


def status_for(policy: MfaPolicy, user: User, session_verified: bool) -> MfaStatus:
    return MfaStatus(
        applies=policy.applies_to(user),
        enforced=policy.enforced(),
        session_verified=session_verified,
        enrolled=bool(user.is_2fa_enabled),
        enforced_from=policy.enforced_from,
        from_environment=policy.from_environment,
    )


def is_enrolment_route(method: str, path: str) -> bool:
    if (method, path) in ENROLMENT_ROUTES:
        return True
    return any(
        m == method and prefix.endswith("/") and path.startswith(prefix) for m, prefix in ENROLMENT_ROUTES
    )


def enforcement_date(grace_days: int, now: datetime | None = None) -> datetime:
    return (now or datetime.now(timezone.utc)) + timedelta(days=max(0, grace_days))
