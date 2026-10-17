"""The access/portability package (D1): every workspace the person is a member of, their profile,
sessions, API-token metadata (never the secret) and their own access history — one zip, built the same
way `/api/export/backup` builds a single workspace's.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access_log import ACCESS_ACTIONS
from app.models.account import Account
from app.models.api_token import ApiToken
from app.models.asset import Asset
from app.models.asset_value import AssetValue
from app.models.audit import AuditEvent
from app.models.budget import Budget
from app.models.category import Category
from app.models.category_group import CategoryGroup
from app.models.import_log import ImportLog
from app.models.recurring_transaction import RecurringTransaction
from app.models.rule import Rule
from app.models.transaction import Transaction
from app.models.user import User
from app.models.user_session import UserSession
from app.models.workspace import Workspace, WorkspaceMember
from app.services.backup_service import build_backup_archive, collect_workspace, serialize_row

#: Never leaves the server: even in a person's own export, the hash and the credential stay put.
_TOKEN_OMIT = {"token_hash"}
_PROFILE_OMIT = {"hashed_password", "totp_secret", "totp_secret_enc"}
#: Session refresh-token hashes: not the secret itself, but a stolen hash could still be replayed if the
#: rotation-reuse detection ever allowed a stale hash through, so it stays off a person's own export too.
_SESSION_OMIT = {"refresh_hash", "previous_refresh_hash"}


def _profile(user: User) -> dict:
    row = serialize_row(user)
    for key in _PROFILE_OMIT:
        row.pop(key, None)
    return row


async def _workspaces_of(session: AsyncSession, user: User) -> list[Workspace]:
    """Every workspace the person has access to: member workspaces plus workspaces
    they only administer externally (`Workspace.managed_by_user_id`) — a person
    can have effective owner rights in a workspace without ever being a member.

    Queried directly (not via `workspace_service.get_user_workspaces` /
    `get_managed_workspaces`) because this export must also include archived
    (soft-deleted) workspaces: being archived hides a workspace from the UI, but
    it does not erase the person's right to their own historical data in it for
    an LGPD access/portability request. Those two `workspace_service` functions
    intentionally filter out archived workspaces for their own (UI-facing)
    callers, so their filter is deliberately not reused here.
    """
    member_result = await session.execute(
        select(Workspace)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user.id)
        .order_by(Workspace.created_at.asc())
    )
    member_workspaces = list(member_result.scalars().all())

    managed_result = await session.execute(
        select(Workspace)
        .where(Workspace.managed_by_user_id == user.id)
        .order_by(Workspace.created_at.asc())
    )
    managed_workspaces = list(managed_result.scalars().all())

    seen: set = set()
    workspaces: list[Workspace] = []
    for workspace in [*member_workspaces, *managed_workspaces]:
        if workspace.id in seen:
            continue
        seen.add(workspace.id)
        workspaces.append(workspace)
    return workspaces


async def _sessions(session: AsyncSession, user: User) -> list[dict]:
    rows = (await session.execute(select(UserSession).where(UserSession.user_id == user.id))).scalars().all()
    sessions = []
    for row in rows:
        serialized = serialize_row(row)
        for key in _SESSION_OMIT:
            serialized.pop(key, None)
        sessions.append(serialized)
    return sessions


async def _api_tokens(session: AsyncSession, user: User) -> list[dict]:
    rows = (await session.execute(select(ApiToken).where(ApiToken.user_id == user.id))).scalars().all()
    tokens = []
    for row in rows:
        serialized = serialize_row(row)
        for key in _TOKEN_OMIT:
            serialized.pop(key, None)
        tokens.append(serialized)
    return tokens


async def _access_history(session: AsyncSession, user: User) -> list[dict]:
    rows = (
        await session.execute(
            select(AuditEvent)
            .where(
                AuditEvent.action.in_(ACCESS_ACTIONS),
                AuditEvent.purged_at.is_(None),
                AuditEvent.actor_user_id == user.id,
            )
            .order_by(AuditEvent.occurred_at.desc())
        )
    ).scalars().all()
    return [
        {
            "occurred_at": r.occurred_at.isoformat(),
            "action": r.action,
            "detail": r.detail,
            "ip": r.ip,
            "user_agent": r.user_agent,
        }
        for r in rows
    ]


async def _is_sole_member(session: AsyncSession, workspace_id, user_id) -> bool:
    """True only when this person is the workspace's one and only member — the case where the full
    `collect_workspace` collection and "only my own rows" collection are the same set anyway. A workspace
    the person only manages externally (`managed_by_user_id`, not a `workspace_members` row at all) is
    never sole-member: its member list doesn't include them, so it always falls to the scoped path."""
    member_user_ids = (
        await session.execute(select(WorkspaceMember.user_id).where(WorkspaceMember.workspace_id == workspace_id))
    ).scalars().all()
    return member_user_ids == [user_id]


async def collect_workspace_for_person(workspace, user_id, session: AsyncSession) -> dict[str, object]:
    """A person-scoped mirror of `backup_service.collect_workspace`: every entity in the workspace that
    belongs to `user_id`, not the whole workspace. D1-specific (used only for the access/portability
    archive) — `collect_workspace` itself stays untouched and full-workspace, since `/api/export/backup`
    still needs that shape."""
    ws_id = workspace.id

    accounts = (
        await session.execute(select(Account).where(Account.workspace_id == ws_id, Account.user_id == user_id))
    ).scalars().all()
    transactions = (
        await session.execute(select(Transaction).where(Transaction.workspace_id == ws_id, Transaction.user_id == user_id))
    ).scalars().all()
    categories = (
        await session.execute(select(Category).where(Category.workspace_id == ws_id, Category.user_id == user_id))
    ).scalars().all()
    category_groups = (
        await session.execute(
            select(CategoryGroup).where(CategoryGroup.workspace_id == ws_id, CategoryGroup.user_id == user_id)
        )
    ).scalars().all()
    rules = (
        await session.execute(select(Rule).where(Rule.workspace_id == ws_id, Rule.user_id == user_id))
    ).scalars().all()
    recurring_transactions = (
        await session.execute(
            select(RecurringTransaction).where(
                RecurringTransaction.workspace_id == ws_id, RecurringTransaction.user_id == user_id
            )
        )
    ).scalars().all()
    budgets = (
        await session.execute(select(Budget).where(Budget.workspace_id == ws_id, Budget.user_id == user_id))
    ).scalars().all()
    assets = (
        await session.execute(select(Asset).where(Asset.workspace_id == ws_id, Asset.user_id == user_id))
    ).scalars().all()
    import_logs = (
        await session.execute(select(ImportLog).where(ImportLog.workspace_id == ws_id, ImportLog.user_id == user_id))
    ).scalars().all()

    # `AssetValue` has no `user_id` of its own — scoped the same way `collect_workspace` derives it,
    # via the person's own asset ids in this workspace.
    asset_ids = [a.id for a in assets]
    if asset_ids:
        asset_values = (
            await session.execute(select(AssetValue).where(AssetValue.asset_id.in_(asset_ids)))
        ).scalars().all()
    else:
        asset_values = []

    entities = {
        "accounts": accounts,
        "transactions": transactions,
        "categories": categories,
        "category_groups": category_groups,
        "rules": rules,
        "recurring_transactions": recurring_transactions,
        "budgets": budgets,
        "assets": assets,
        "asset_values": asset_values,
        "import_logs": import_logs,
    }

    files: dict[str, object] = {}
    entity_counts = {}
    for name, rows in entities.items():
        serialized = [serialize_row(r) for r in rows]
        entity_counts[name] = len(serialized)
        files[f"{name}.json"] = serialized

    files["metadata.json"] = {
        "export_date": datetime.now(timezone.utc).isoformat(),
        "format_version": "1.0",
        "workspace_id": str(ws_id),
        "workspace_name": workspace.name,
        "entity_counts": entity_counts,
        "scope": "own_records_only",
    }
    return files


async def build_person_archive(session: AsyncSession, user: User) -> bytes:
    files: dict[str, object] = {
        "profile.json": _profile(user),
        "sessions.json": await _sessions(session, user),
        "api_tokens.json": await _api_tokens(session, user),
        "access_history.json": await _access_history(session, user),
    }
    workspaces = await _workspaces_of(session, user)
    for workspace in workspaces:
        if await _is_sole_member(session, workspace.id, user.id):
            entities = await collect_workspace(workspace, session)
            metadata = entities["metadata.json"]
            assert isinstance(metadata, dict)
            metadata["scope"] = "full_workspace"
        else:
            entities = await collect_workspace_for_person(workspace, user.id, session)
        for name, payload in entities.items():
            files[f"{workspace.id}/{name}"] = payload
    files["metadata.json"] = {
        "export_date": datetime.now(timezone.utc).isoformat(),
        "format_version": "1.0",
        "user_id": str(user.id),
        "workspace_count": len(workspaces),
    }
    return build_backup_archive(files)
