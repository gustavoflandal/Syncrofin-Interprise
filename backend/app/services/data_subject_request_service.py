"""D1: creating and resolving a titular's request. Access/portability resolve on the spot with a
package; correction is self-served or becomes a ticket; erasure re-authenticates, can be blocked by
shared-workspace ownership, and reuses the cascade `user_deletion_service` shares with the admin panel.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models.agent import Agent
from app.agents.models.conversation import Conversation
from app.core.audit import record_event
from app.core.audit_context import set_actor
from app.core.auth import UserManager
from app.models.account import Account
from app.models.asset import Asset
from app.models.asset_group import AssetGroup
from app.models.bank_connection import BankConnection
from app.models.budget import Budget
from app.models.category import Category
from app.models.category_group import CategoryGroup
from app.models.collection import Collection
from app.models.credit_card_bill import CreditCardBill
from app.models.data_subject_request import DataSubjectRequest, generate_protocol
from app.models.goal import Goal
from app.models.group import Group
from app.models.import_log import ImportLog
from app.models.invoice import Invoice
from app.models.invoice_attachment import InvoiceAttachment
from app.models.payee import Payee, PayeeMapping
from app.models.recurring_transaction import RecurringTransaction
from app.models.rule import Rule
from app.models.transaction import Transaction
from app.models.transaction_attachment import TransactionAttachment
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.services import data_subject_export_service, email_service, email_templates, user_deletion_service

#: Every model `user_deletion_service._delete_owned_data` deletes (or attachments it deletes) by its
#: own `user_id` that ALSO carries a `workspace_id` directly (so a workspace can be attributed to a row
#: of this kind). `AssetValue` has no `user_id` column at all (deleted via `asset_id IN (...)`), so it
#: can't appear here. `TransactionAttachment` and `InvoiceAttachment` DO belong here even though most of
#: their rows are deleted by `transaction_id`/`invoice_id IN (...)` — each also carries its own `user_id`
#: for the "uploaded onto someone else's row" case, and that pass is what actually drives deletion when
#: the parent transaction/invoice belongs to a different workspace than the one this loop is trying to
#: find.
_OWNED_DATA_MODELS_WITH_WORKSPACE = (
    Transaction, Budget, RecurringTransaction, ImportLog, Rule, Asset,
    PayeeMapping, Payee, Account, Category, CategoryGroup, BankConnection,
    Goal, Collection, CreditCardBill, AssetGroup, Invoice,
    TransactionAttachment, InvoiceAttachment,
)

#: Models the database cascades away on its own (`ondelete="CASCADE"`) the moment the person is
#: deleted — so they need no entry in `_delete_owned_data` — but that ARE shared, workspace-visible
#: content, not personal to the person leaving: another member can see and rely on the row today, and
#: losing it as a side effect of someone else's self-erasure is exactly the bug class this block query
#: exists to catch. `Group`s are visible to every workspace member (see `group_service.py`); an `Agent`
#: and its `Conversation`s are listed by `workspace_id` alone, with no `user_id` filter, so every member
#: who can open the workspace can see them regardless of who created them.
#:
#: Left out on purpose: `Notification` (CASCADE + workspace_id, but explicitly per-recipient — "must not
#: make it disappear for everyone else"), `ApiToken` (CASCADE + workspace_id, but its own docstring says
#: the token is meant to stop working once its owner leaves), and anything with `ondelete="SET NULL"`
#: whose column is pure attribution rather than the row's own content (`Workspace.created_by_user_id`,
#: `WorkspaceRole.created_by_user_id`, `WorkspaceMember.invited_by_user_id`, `GroupMember.linked_user_id`)
#: — nulling those loses a "who did this" byline, not anything the row is showing other members.
_CASCADE_DELETED_MODELS_WITH_WORKSPACE = (Group, Agent, Conversation)


class WrongPassword(Exception):
    """The re-authentication step of an erasure request did not match the account's password."""


class AlreadyResolved(Exception):
    """The admin tried to resolve a data-subject request that isn't `pending` any more."""


class WorkspacesBlockErasure(Exception):
    """At least one workspace with other active members would lose data this person owns or created —
    either because they are its sole `owner`, or because they hold rows in it (an account, a shared
    group, an invoice they issued…) that erasure would delete or take from other members without asking.
    Either reason blocks; see `_owned_workspaces_with_other_members` for exactly what's checked."""

    def __init__(self, workspace_names: list[str], protocol: str) -> None:
        self.workspace_names = workspace_names
        #: A `rejected` request was still recorded (see `request_erasure`) — this is its protocol, so
        #: the person has something to reference if they write in about it.
        self.protocol = protocol
        super().__init__(f"blocked by shared workspace data or ownership: {', '.join(workspace_names)}")


#: Where a person can already fix each kind of data themselves — the correction request's
#: "I know where to fix it" branch. Paths only: the frontend prefixes its own origin.
SELF_SERVICE_LINKS: dict[str, str] = {
    "profile": "/settings/profile",
    "transactions": "/transactions",
    "accounts": "/accounts",
    "categories": "/categories",
}


async def create_access_or_portability(
    session: AsyncSession, user: User, kind: str
) -> tuple[DataSubjectRequest, bytes]:
    archive = await data_subject_export_service.build_person_archive(session, user)
    row = DataSubjectRequest(
        id=uuid.uuid4(),
        protocol=generate_protocol(),
        user_id=user.id,
        kind=kind,
        status="resolved_auto",
        resolved_at=datetime.now(timezone.utc),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row, archive


async def create_correction(
    session: AsyncSession, user: User, *, self_service: bool, detail: Optional[str]
) -> DataSubjectRequest:
    if not self_service and not detail:
        raise ValueError("detail is required when the person cannot self-serve the correction")
    resolved = self_service
    row = DataSubjectRequest(
        id=uuid.uuid4(),
        protocol=generate_protocol(),
        user_id=user.id,
        kind="correction",
        status="resolved_auto" if resolved else "pending",
        detail=detail,
        resolved_at=datetime.now(timezone.utc) if resolved else None,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def _workspaces_with_the_persons_own_data(session: AsyncSession, user_id: uuid.UUID) -> set[uuid.UUID]:
    """Every workspace the person has at least one `user_id`-owned row in, across the tables
    `user_deletion_service._delete_owned_data` deletes from PLUS the tables the database cascades away
    on its own but that are shared, workspace-visible content (`_CASCADE_DELETED_MODELS_WITH_WORKSPACE`).
    A UNION of one query per table — simplest to get right, and this isn't a hot path (erasure is a
    rare, deliberate action)."""
    workspace_ids: set[uuid.UUID] = set()
    for model in (*_OWNED_DATA_MODELS_WITH_WORKSPACE, *_CASCADE_DELETED_MODELS_WITH_WORKSPACE):
        result = await session.execute(
            select(model.workspace_id).distinct().where(model.user_id == user_id)
        )
        workspace_ids.update(result.scalars().all())
    return workspace_ids


async def _owned_workspaces_with_other_members(session: AsyncSession, user: User) -> list[Workspace]:
    """Workspaces that would block erasure: any workspace where the person either (a) holds `owner`-role
    membership, or (b) has any of their own data rows (per `_delete_owned_data`'s table list) — union of
    both, same as `user_deletion_service`'s cascade would touch — AND that workspace has at least one
    OTHER member. Covers both the sole-owner case (today's original check) and the editor/viewer/external
    manager case, where the person's erasure would otherwise silently destroy other members' shared
    workspace's data with no block and no warning."""
    owner_role_ids = set(
        (
            await session.execute(
                select(WorkspaceMember.workspace_id).where(
                    WorkspaceMember.user_id == user.id, WorkspaceMember.role == "owner"
                )
            )
        ).scalars().all()
    )
    data_ids = await _workspaces_with_the_persons_own_data(session, user.id)
    candidate_ids = owner_role_ids | data_ids
    if not candidate_ids:
        return []

    blocking: list[Workspace] = []
    for workspace_id in candidate_ids:
        others = (
            await session.execute(
                select(func.count())
                .select_from(WorkspaceMember)
                .where(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id != user.id)
            )
        ).scalar() or 0
        if others > 0:
            workspace = await session.get(Workspace, workspace_id)
            if workspace is not None:
                blocking.append(workspace)
    return blocking


async def request_erasure(
    session: AsyncSession, user_manager: UserManager, user: User, password: str
) -> DataSubjectRequest:
    verified, _ = user_manager.password_helper.verify_and_update(password, user.hashed_password)
    if not verified:
        # A failed re-authentication attempt isn't invisible: the same shape as login_guard's
        # `login_failed`, so it is subject to the same access-log retention/anonymisation.
        set_actor(user.id)
        await record_event(session, "erasure_password_failed", "user", entity_id=user.id)
        await session.commit()
        raise WrongPassword()

    blocking = await _owned_workspaces_with_other_members(session, user)
    if blocking:
        names = [w.name for w in blocking]
        rejected = DataSubjectRequest(
            id=uuid.uuid4(),
            protocol=generate_protocol(),
            user_id=user.id,
            kind="erasure",
            status="rejected",
            resolution_note=f"bloqueada por titularidade ou dados em workspace compartilhado: {', '.join(names)}",
            resolved_at=datetime.now(timezone.utc),
        )
        session.add(rejected)
        await session.commit()
        raise WorkspacesBlockErasure(names, rejected.protocol)

    row = DataSubjectRequest(
        id=uuid.uuid4(),
        protocol=generate_protocol(),
        user_id=user.id,
        kind="erasure",
        status="resolved_auto",
        resolved_at=datetime.now(timezone.utc),
    )
    session.add(row)
    # Nothing claims success until the deletion has actually happened: `delete_user_data` does not
    # commit either (its own docstring says so), so this row and the whole cascade share ONE
    # transaction. If the cascade raises (a `ForeignKeyViolation`, e.g.), the commit below never runs,
    # everything here rolls back together, and the caller sees the real exception instead of a
    # fabricated "resolved_auto" row plus an e-mail nobody's data backs up.
    await user_deletion_service.delete_user_data(session, user)
    await session.commit()  # the create event is what survives — see Task 1's docstring
    protocol = row.protocol

    # Only now, after the commit has actually succeeded, do we tell the person it's done. Reading
    # `user.email`/`user.preferences` off the in-memory object post-commit (and post-delete: `user`
    # was removed by `delete_user_data` above, in this same now-committed transaction) is safe because
    # `async_session_maker` sets `expire_on_commit=False` (see `app/core/database.py`) — the attributes
    # stay populated even though the row is gone.
    subject, body = email_templates.erasure_confirmed(
        (user.preferences or {}).get("language"),
        protocol=protocol,
        when=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
    )
    email_service.send_in_background(user.email, subject, body)

    return row


async def resolve(
    session: AsyncSession, request_id: uuid.UUID, status: str, resolution_note: Optional[str]
) -> Optional[DataSubjectRequest]:
    row = await session.get(DataSubjectRequest, request_id)
    if row is None:
        return None
    if row.status != "pending":
        raise AlreadyResolved()
    row.status = status
    row.resolution_note = resolution_note
    row.resolved_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(row)
    return row


async def list_own(session: AsyncSession, user: User) -> list[DataSubjectRequest]:
    rows = (
        await session.execute(
            select(DataSubjectRequest)
            .where(DataSubjectRequest.user_id == user.id)
            .order_by(DataSubjectRequest.created_at.desc(), DataSubjectRequest.id.desc())
        )
    ).scalars().all()
    return list(rows)
