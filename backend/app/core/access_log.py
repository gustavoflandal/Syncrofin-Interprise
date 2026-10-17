"""Which audit events are *accesses* to the application, and how long they are kept.

An access is somebody (or a token) getting in, failing to, being held back, or being shown out. These
events live in `audit_events` like every other, and are read through the access-log routes.

Keeping them: the law asks for at least six months (Marco Civil da Internet, art. 15), and the data
protection law asks for no longer than needed. So the instance has a **retention period**
(`access_log_retention_days`, in `app_settings`, never below `ACCESS_MIN_RETENTION_DAYS`), and once it is
over an event is **anonymised**, not deleted: the columns that identify a person are emptied and the row
stays, so the hash chain of the trail still verifies. The database enforces the floor: its trigger refuses
to anonymise anything younger than `ACCESS_MIN_RETENTION_DAYS`.

The action list is repeated in SQL (the trigger, `audit_events_purge_access` and the index
`ix_audit_events_access`). Adding an action means a new migration for all three, and a test compares them.
"""
from __future__ import annotations

ACCESS_ACTIONS: tuple[str, ...] = (
    "login",
    "login_failed",
    "login_blocked",
    "account_locked",
    "account_unlocked",
    "session_revoked",
    "token_access",
    #: A wrong password at the erasure request's re-authentication step (D1) — the same shape as
    #: `login_failed`, just for a second password check while already signed in.
    "erasure_password_failed",
)

ACCESS_MIN_RETENTION_DAYS = 183
ACCESS_MAX_RETENTION_DAYS = 3650

#: What anonymising empties. Everything else on the row (time, action, kind of actor, workspace, hashes) stays.
REDACTED_COLUMNS: tuple[str, ...] = (
    "actor_user_id",
    "entity_id",
    "changes",
    "ip",
    "user_agent",
    "request_id",
    "detail",
)


def sql_list() -> str:
    """The actions as SQL literals: `'login', 'login_failed', ...`."""
    return ", ".join(f"'{action}'" for action in ACCESS_ACTIONS)
