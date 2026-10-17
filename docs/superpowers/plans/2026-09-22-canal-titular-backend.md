# Canal do titular (D1) — Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every person a channel to request access, portability, correction and erasure of their own
data (LGPD art. 18), with a protocol, a deadline, and an audit trail — the backend half of D1.

**Architecture:** A new table `data_subject_requests` (protocol, kind, status, deadline) drives the flow.
Access/portability build a person-wide export package (extends the existing per-workspace `export.py`
backup). Correction is self-served with links, or becomes a `pending` ticket. Erasure re-authenticates with
a password, blocks when the person is the sole owner of a workspace with other active members, and reuses
a cascade extracted from `admin_service.delete_user` into a shared `user_deletion_service`. Every
create/update of a request is audited automatically through the existing generic ORM-audit mechanism
(`core/audit.py`), the same way almost every other model in this codebase is audited.

**Tech Stack:** FastAPI, SQLAlchemy (async), Alembic, pytest + pytest-asyncio, PostgreSQL (tests run
against real Postgres per `docs/FASE1.md` — see `docker-compose.test.yml`).

## Global Constraints

- Migration revision `100`, `down_revision = "099"`.
- `data_subject_requests.user_id` is a **real FK** to `users.id`, `ON DELETE CASCADE` — deliberately
  different from `audit_events.actor_user_id` (which has no FK): the audit event is the permanent evidence,
  this row is operational and is allowed to disappear with the person.
- `DataSubjectRequest` is added to `AUDITED` in `app/core/audit.py`, not to `EXEMPT` — its create/update
  already produces a C1 event with no extra code.
- Deadline default: 15 days, overridable via `DATA_REQUEST_DEADLINE_DAYS` env var (`Settings.data_request_deadline_days`).
- No new entry in the C2 permission catalog: every route in this plan uses `current_active_user` (own data)
  or `current_superuser` (admin), exactly like the D3 access-log routes — neither needs `require_permission`.
- Every new mutating route needs an entry in `tests/test_write_permission_coverage.py::ALLOWLIST`, reason
  `"the requester's own data-subject request"` (self routes) or `"superuser-gated instance administration"`
  (admin route) — copy the exact wording already used for `/me`, `/2fa/*` and `/api/admin/access-log/retention`.
- Money/PII in code comments and docstrings follow the file's existing voice (see `access_log_service.py`,
  `admin_service.py`) — prose comments explaining *why*, not *what*.
- Every step that touches the database runs against the real test Postgres: `docker compose -f
  docker-compose.test.yml up -d` must be running before any `pytest` command in this plan.

---

### Task 1: Migration + model for `data_subject_requests`

**Files:**
- Create: `backend/alembic/versions/100_data_subject_requests.py`
- Create: `backend/app/models/data_subject_request.py`
- Modify: `backend/app/models/__init__.py` (export `DataSubjectRequest`)
- Modify: `backend/app/core/audit.py:29-68` (import + add to `AUDITED`)
- Modify: `backend/app/core/config.py:51` area (add `data_request_deadline_days: int = 15`)
- Test: `backend/tests/test_data_subject_request_model.py`

**Interfaces:**
- Produces: `app.models.data_subject_request.DataSubjectRequest` (columns below), `KINDS = ("access",
  "portability", "correction", "erasure")`, `STATUSES = ("resolved_auto", "pending", "resolved_manual",
  "rejected")`, `generate_protocol() -> str` (module-level function, format `DSR-{year}-{6-digit sequence}`).

- [ ] **Step 1: Write the failing model test**

```python
# backend/tests/test_data_subject_request_model.py
"""The data_subject_requests table: columns, cascade on user deletion, protocol format."""
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_subject_request import DataSubjectRequest, generate_protocol
from app.models.user import User

pytestmark = pytest.mark.asyncio


class TestTheModel:
    async def test_it_saves_and_reads_back(self, session: AsyncSession, test_user: User, clean_db):
        row = DataSubjectRequest(
            id=uuid.uuid4(),
            protocol=generate_protocol(),
            user_id=test_user.id,
            kind="access",
            status="resolved_auto",
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        assert row.due_at > row.created_at
        assert row.protocol.startswith("DSR-")

    async def test_it_rejects_an_unknown_kind(self, session: AsyncSession, test_user: User, clean_db):
        row = DataSubjectRequest(
            id=uuid.uuid4(), protocol=generate_protocol(), user_id=test_user.id,
            kind="not-a-kind", status="resolved_auto",
        )
        session.add(row)
        with pytest.raises(Exception):
            await session.commit()

    async def test_deleting_the_user_cascades(self, session: AsyncSession, test_user: User, clean_db):
        row = DataSubjectRequest(
            id=uuid.uuid4(), protocol=generate_protocol(), user_id=test_user.id,
            kind="access", status="resolved_auto",
        )
        session.add(row)
        await session.commit()
        await session.delete(test_user)
        await session.commit()
        remaining = (await session.execute(select(DataSubjectRequest).where(DataSubjectRequest.id == row.id))).scalar_one_or_none()
        assert remaining is None


class TestProtocol:
    def test_it_has_the_year_and_is_unique_across_calls(self):
        import datetime
        first = generate_protocol()
        second = generate_protocol()
        assert first != second
        assert str(datetime.datetime.now().year) in first
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && python -m pytest tests/test_data_subject_request_model.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models.data_subject_request'`

- [ ] **Step 3: Write the model**

```python
# backend/app/models/data_subject_request.py
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
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc) + timedelta(days=get_settings().data_request_deadline_days),
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolution_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
```

- [ ] **Step 4: Register the model**

In `backend/app/models/__init__.py`, add the import next to the other model exports (follow the existing
alphabetised list — find where `Collection` or `CreditCardBill` is imported and insert nearby):

```python
from app.models.data_subject_request import DataSubjectRequest
```

Add `"DataSubjectRequest"` to `__all__` if that file defines one (check the file first — if it does not
define `__all__`, the import alone is enough).

- [ ] **Step 5: Add the setting**

In `backend/app/core/config.py`, near `access_log_retention_days: int = 183` (around line 51), add:

```python
    # LGPD art. 18: how long a data-subject request stays open before it counts as overdue.
    data_request_deadline_days: int = 15
```

- [ ] **Step 6: Wire the model into the generic audit mechanism**

In `backend/app/core/audit.py`, add the import at line ~30 (alphabetised with the other model imports) and
add `DataSubjectRequest` to the `AUDITED` tuple (alphabetised, so between `CreditCardBill` and `Goal`):

```python
from app.models import (
    Account,
    ApiToken,
    AppSetting,
    Asset,
    AssetGroup,
    AssetTransaction,
    AssetValue,
    BankConnection,
    Budget,
    Category,
    CategoryGroup,
    Collection,
    CreditCardBill,
    DataSubjectRequest,
    Goal,
    ...
```

```python
AUDITED: tuple[type, ...] = (
    Account,
    Agent,
    ApiToken,
    AppSetting,
    Asset,
    AssetGroup,
    AssetTransaction,
    AssetValue,
    BankConnection,
    Budget,
    Category,
    CategoryGroup,
    Collection,
    CreditCardBill,
    DataSubjectRequest,
    Goal,
    ...
```

- [ ] **Step 7: Write the migration**

```python
# backend/alembic/versions/100_data_subject_requests.py
"""data subject requests: the D1 titular's-channel table

Revision ID: 100
Revises: 099
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "100"
down_revision: Union[str, None] = "099"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "data_subject_requests",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("protocol", sa.String(20), unique=True, nullable=False),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('access', 'portability', 'correction', 'erasure')",
            name="ck_data_subject_requests_kind",
        ),
        sa.CheckConstraint(
            "status IN ('resolved_auto', 'pending', 'resolved_manual', 'rejected')",
            name="ck_data_subject_requests_status",
        ),
    )
    op.create_index(
        "ix_data_subject_requests_user_time", "data_subject_requests", ["user_id", "created_at"]
    )
    op.create_index(
        "ix_data_subject_requests_due",
        "data_subject_requests",
        ["due_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("ix_data_subject_requests_due", table_name="data_subject_requests")
    op.drop_index("ix_data_subject_requests_user_time", table_name="data_subject_requests")
    op.drop_table("data_subject_requests")
```

- [ ] **Step 8: Run the migration against the test database**

Run: `cd backend && docker compose -f docker-compose.test.yml up -d && alembic upgrade head`
Expected: `... -> 100, data subject requests: the D1 titular's-channel table` with no error.

- [ ] **Step 9: Run the model test to verify it passes**

Run: `cd backend && python -m pytest tests/test_data_subject_request_model.py -v`
Expected: PASS (3 tests in `TestTheModel`, 1 in `TestProtocol`)

- [ ] **Step 10: Run the audit and migration-chain guard tests**

Run: `cd backend && python -m pytest tests/test_audit_coverage.py tests/test_migration_chain.py -v`
(if the migration-chain test file has a different name, run `python -m pytest -k migration_chain -v`
first to find it — `check_migration_chain.py` is referenced as a standalone script in `docs/FASE1.md`;
run that too: `python scripts/check_migration_chain.py` if it exists)
Expected: PASS — `test_audit_coverage` fails loudly if `DataSubjectRequest` were left out of both
`AUDITED` and `EXEMPT`, which confirms Step 7 was necessary, not optional.

- [ ] **Step 11: Commit**

```bash
git add backend/alembic/versions/100_data_subject_requests.py backend/app/models/data_subject_request.py \
        backend/app/models/__init__.py backend/app/core/audit.py backend/app/core/config.py \
        backend/tests/test_data_subject_request_model.py
git commit -m "feat: data_subject_requests table, audited automatically (D1)"
```

---

### Task 2: Extract the shared user-deletion cascade

The existing `admin_service.delete_user` cascade (transactions, budgets, recurring transactions, import
logs, rules, assets/asset values, payees, accounts, categories, category groups, bank connections, then
the user row) needs to be reusable from the new erasure flow, without duplicating the table list. This task
only extracts and adds one improvement (orphaned-workspace cleanup); it does not change existing behaviour
for the admin route beyond that.

**Files:**
- Create: `backend/app/services/user_deletion_service.py`
- Modify: `backend/app/services/admin_service.py:164-233` (call the extracted function)
- Test: `backend/tests/test_user_deletion_service.py`
- Existing tests that must keep passing: `backend/tests/test_admin_service.py`, `backend/tests/test_admin_api.py`

**Interfaces:**
- Produces: `async def delete_user_data(session: AsyncSession, user: User) -> None` — deletes every owned
  financial entity, the user row, and any workspace that becomes memberless as a result. Does **not**
  check "last superuser" or "sole owner of a shared workspace" — those are the caller's business rules.
- Consumes (Task 1): nothing yet.

- [ ] **Step 1: Write the failing test for orphaned-workspace cleanup**

```python
# backend/tests/test_user_deletion_service.py
"""The cascade shared by admin deletion and self-service erasure: owned data, the user, and any
workspace that becomes memberless as a result."""
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.services import user_deletion_service

pytestmark = pytest.mark.asyncio


class TestDeleteUserData:
    async def test_it_deletes_the_user_and_their_owned_data(
        self, session: AsyncSession, test_user: User, test_workspace: Workspace, clean_db
    ):
        account = Account(
            id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id,
            name="Conta", type="checking", balance=0, currency="BRL",
        )
        session.add(account)
        await session.commit()

        await user_deletion_service.delete_user_data(session, test_user)
        await session.commit()

        assert (await session.execute(select(User).where(User.id == test_user.id))).scalar_one_or_none() is None
        assert (await session.execute(select(Account).where(Account.id == account.id))).scalar_one_or_none() is None

    async def test_it_removes_a_workspace_that_becomes_memberless(
        self, session: AsyncSession, test_user: User, test_workspace: Workspace, clean_db
    ):
        """test_user is the workspace's only member (see the `test_user` fixture): once they're gone,
        nobody can ever see this workspace again, so it should not linger as an orphan."""
        await user_deletion_service.delete_user_data(session, test_user)
        await session.commit()

        remaining = (await session.execute(select(Workspace).where(Workspace.id == test_workspace.id))).scalar_one_or_none()
        assert remaining is None

    async def test_it_keeps_a_workspace_that_still_has_other_members(
        self, session: AsyncSession, test_user: User, test_workspace: Workspace, clean_db
    ):
        other = User(
            id=uuid.uuid4(), email="other@example.com", hashed_password="x",
            is_active=True, is_superuser=False, is_verified=True,
        )
        session.add(other)
        await session.flush()
        session.add(WorkspaceMember(id=uuid.uuid4(), workspace_id=test_workspace.id, user_id=other.id, role="editor"))
        await session.commit()

        await user_deletion_service.delete_user_data(session, test_user)
        await session.commit()

        remaining = (await session.execute(select(Workspace).where(Workspace.id == test_workspace.id))).scalar_one_or_none()
        assert remaining is not None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && python -m pytest tests/test_user_deletion_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.user_deletion_service'`

- [ ] **Step 3: Read the current cascade before moving it**

Re-read `backend/app/services/admin_service.py:164-233` in full (already reviewed during planning) so the
extracted function is a faithful copy — every table in the existing cascade must stay, in the same order.

- [ ] **Step 4: Write the extracted service**

```python
# backend/app/services/user_deletion_service.py
"""The cascade a person's data goes through when their account is deleted — shared by the admin's
'Delete user' action and the self-service erasure request (D1). Business rules about *whether* a
deletion may proceed (last superuser standing, sole owner of a shared workspace) belong to the caller;
this module only does the deleting, faithfully, for both callers.
"""
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.asset import Asset
from app.models.asset_value import AssetValue
from app.models.bank_connection import BankConnection
from app.models.budget import Budget
from app.models.category import Category
from app.models.category_group import CategoryGroup
from app.models.import_log import ImportLog
from app.models.payee import Payee, PayeeMapping
from app.models.recurring_transaction import RecurringTransaction
from app.models.rule import Rule
from app.models.transaction import Transaction
from app.models.transaction_attachment import TransactionAttachment
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember


async def _delete_owned_data(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Every financial entity keyed directly by `user_id`, in dependency order. Faithful copy of what
    `admin_service.delete_user` did inline before this module existed — do not reorder without checking
    which tables reference which (attachments before transactions, asset values before assets)."""
    tx_ids_query = select(Transaction.id).where(Transaction.user_id == user_id)
    await session.execute(delete(TransactionAttachment).where(TransactionAttachment.transaction_id.in_(tx_ids_query)))
    await session.execute(delete(Transaction).where(Transaction.user_id == user_id))
    await session.execute(delete(Budget).where(Budget.user_id == user_id))
    await session.execute(delete(RecurringTransaction).where(RecurringTransaction.user_id == user_id))
    await session.execute(delete(ImportLog).where(ImportLog.user_id == user_id))
    await session.execute(delete(Rule).where(Rule.user_id == user_id))

    asset_ids_query = select(Asset.id).where(Asset.user_id == user_id)
    await session.execute(delete(AssetValue).where(AssetValue.asset_id.in_(asset_ids_query)))
    await session.execute(delete(Asset).where(Asset.user_id == user_id))

    await session.execute(delete(PayeeMapping).where(PayeeMapping.user_id == user_id))
    await session.execute(delete(Payee).where(Payee.user_id == user_id))
    await session.execute(delete(Account).where(Account.user_id == user_id))
    await session.execute(delete(Category).where(Category.user_id == user_id))
    await session.execute(delete(CategoryGroup).where(CategoryGroup.user_id == user_id))
    await session.execute(delete(BankConnection).where(BankConnection.user_id == user_id))


async def _workspace_ids_of(session: AsyncSession, user_id: uuid.UUID) -> list[uuid.UUID]:
    result = await session.execute(select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user_id))
    return [row for row in result.scalars().all()]


async def _delete_orphaned_workspaces(session: AsyncSession, workspace_ids: list[uuid.UUID]) -> None:
    """A workspace whose last member just left (their `workspace_members` row cascades away with the
    user, at the database level, before this runs) is unreachable forever — nobody can be added to a
    workspace they cannot see. Deleting it here is a cleanup the admin cascade never did; see the D1
    plan's Task 2 for why it's added now rather than left as a pre-existing gap."""
    if not workspace_ids:
        return
    still_has_members = (
        await session.execute(
            select(WorkspaceMember.workspace_id).where(WorkspaceMember.workspace_id.in_(workspace_ids)).distinct()
        )
    ).scalars().all()
    orphaned = set(workspace_ids) - set(still_has_members)
    if orphaned:
        await session.execute(delete(Workspace).where(Workspace.id.in_(orphaned)))


async def delete_user_data(session: AsyncSession, user: User) -> None:
    """Delete `user`'s owned financial data, the user row itself, and any workspace left with no
    members. Does not commit — the caller commits, after any of its own last write (e.g. sending a
    confirmation e-mail while `user.email` is still readable)."""
    workspace_ids = await _workspace_ids_of(session, user.id)
    await _delete_owned_data(session, user.id)
    await session.delete(user)
    await session.flush()  # so the `workspace_members` cascade from the FK has actually happened
    await _delete_orphaned_workspaces(session, workspace_ids)
```

- [ ] **Step 5: Run the new test to verify it passes**

Run: `cd backend && python -m pytest tests/test_user_deletion_service.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Point `admin_service.delete_user` at the extracted function**

In `backend/app/services/admin_service.py`, replace the inline cascade (the block from the `# Cascade
delete user data in correct order` comment through the last `delete(BankConnection...)` call, and the
`await session.delete(user)` right after it — keep everything *before* that block: the self-delete guard
and the last-superuser guard) with:

```python
    from app.services.user_deletion_service import delete_user_data

    await delete_user_data(session, user)
    await session.commit()
    return True
```

The full function should now read (guards unchanged, cascade delegated):

```python
async def delete_user(
    session: AsyncSession,
    user_id: uuid.UUID,
    current_user_id: uuid.UUID,
) -> bool:
    if user_id == current_user_id:
        raise ValueError("Cannot delete your own account")

    user = await get_user(session, user_id)
    if not user:
        return False

    # Check last superuser protection
    if user.is_superuser:
        count_result = await session.execute(
            select(func.count()).select_from(User).where(
                User.is_superuser == True,  # noqa: E712
                User.is_active == True,  # noqa: E712
            )
        )
        superuser_count = count_result.scalar() or 0
        if superuser_count <= 1:
            raise ValueError("Cannot delete the last admin user")

    from app.services.user_deletion_service import delete_user_data

    await delete_user_data(session, user)
    await session.commit()
    return True
```

Remove the now-unused per-table imports at the top of `admin_service.py` that were only used by the
deleted inline block (`TransactionAttachment`, `Transaction`, `Budget`, `RecurringTransaction`, `ImportLog`,
`Rule`, `AssetValue`, `Asset`, `PayeeMapping`, `Payee`, `Account`, `Category`, `CategoryGroup`,
`BankConnection` — check each is not used elsewhere in the file before removing; `delete` from `sqlalchemy`
may also become unused).

- [ ] **Step 7: Run the existing admin tests to confirm nothing broke**

Run: `cd backend && python -m pytest tests/test_admin_service.py tests/test_admin_api.py -v`
Expected: PASS, same test count as before this task (the extraction must be behaviour-preserving for the
admin path — this is the regression check).

- [ ] **Step 8: Run ruff**

Run: `cd backend && python -m ruff check app/services/admin_service.py app/services/user_deletion_service.py`
Expected: `All checks passed!`

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/user_deletion_service.py backend/app/services/admin_service.py \
        backend/tests/test_user_deletion_service.py
git commit -m "refactor: extract user_deletion_service from admin_service, clean up orphaned workspaces"
```

---

### Task 3: Person-wide export package (access / portability)

Extends `export.py`'s per-workspace collection into a per-*person* archive covering every workspace they
belong to, plus profile, sessions, API-token metadata and their own access history. Moves the collection
helpers out of the API module and into `backup_service.py` on the way, so a service can call them without
reaching into an API router.

**Files:**
- Modify: `backend/app/services/backup_service.py` (add `serialize_row`, `collect_workspace`)
- Modify: `backend/app/api/export.py` (remove `_serialize`/`_collect`, call the service instead)
- Create: `backend/app/services/data_subject_export_service.py`
- Test: `backend/tests/test_data_subject_export_service.py`

**Interfaces:**
- Consumes (Task 1): none directly (queries `DataSubjectRequest` is Task 4's job, not this one).
- Produces: `async def build_person_archive(session: AsyncSession, user: User) -> bytes` — a zip, built with
  the existing `build_backup_archive` from `backup_service.py`.
- Produces (from `backup_service.py`): `serialize_row(obj) -> dict`, `async def collect_workspace(workspace,
  session) -> dict[str, object]` — both now reusable outside `export.py`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_data_subject_export_service.py
"""The person-wide export package: every workspace, profile, sessions, tokens, access history."""
import io
import json
import zipfile

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.workspace import Workspace
from app.services import data_subject_export_service

pytestmark = pytest.mark.asyncio


class TestBuildPersonArchive:
    async def test_it_includes_the_workspace_and_profile_and_metadata(
        self, session: AsyncSession, test_user: User, test_workspace: Workspace, clean_db
    ):
        archive = await data_subject_export_service.build_person_archive(session, test_user)
        zf = zipfile.ZipFile(io.BytesIO(archive))
        names = zf.namelist()

        assert any(name.endswith("profile.json") for name in names)
        assert any(name.endswith("access_history.json") for name in names)
        assert any(name.endswith("sessions.json") for name in names)
        assert any(name.endswith("api_tokens.json") for name in names)
        assert any(f"{test_workspace.id}" in name and name.endswith("accounts.json") for name in names)

        profile = json.loads(zf.read(next(n for n in names if n.endswith("profile.json"))))
        assert profile["email"] == test_user.email
        assert "hashed_password" not in profile

    async def test_it_covers_every_workspace_the_person_is_a_member_of(
        self, session: AsyncSession, test_user: User, clean_db
    ):
        import uuid
        from app.models.workspace import WorkspaceMember

        second = Workspace(id=uuid.uuid4(), name="Segunda", kind="business", created_by_user_id=test_user.id)
        session.add(second)
        await session.flush()
        session.add(WorkspaceMember(id=uuid.uuid4(), workspace_id=second.id, user_id=test_user.id, role="owner"))
        await session.commit()

        archive = await data_subject_export_service.build_person_archive(session, test_user)
        names = zipfile.ZipFile(io.BytesIO(archive)).namelist()
        workspace_folders = {name.split("/")[0] for name in names if "/" in name}
        assert len(workspace_folders) == 2
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && python -m pytest tests/test_data_subject_export_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.data_subject_export_service'`

- [ ] **Step 3: Move `_serialize`/`_collect` into `backup_service.py`, as `serialize_row`/`collect_workspace`**

`_serialize` and `_collect` currently live in the API module `export.py`. The new export service is a
*service*, and a service importing private helpers out of an API router is the wrong direction — move
both into `backup_service.py` (which already holds `build_backup_archive`, so this keeps everything about
building an archive in one service module) and make `export.py` call the service instead.

In `backend/app/services/backup_service.py`, add above `build_backup_archive`:

```python
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.asset import Asset
from app.models.asset_value import AssetValue
from app.models.budget import Budget
from app.models.category import Category
from app.models.category_group import CategoryGroup
from app.models.import_log import ImportLog
from app.models.recurring_transaction import RecurringTransaction
from app.models.rule import Rule
from app.models.transaction import Transaction


def serialize_row(obj) -> dict:
    """Convert a SQLAlchemy model instance to a JSON-serializable dict."""
    d = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.key)
        if isinstance(val, UUID):
            val = str(val)
        elif isinstance(val, (datetime, date)):
            val = val.isoformat()
        elif isinstance(val, Decimal):
            val = str(val)
        d[col.key] = val
    return d


async def collect_workspace(workspace, session: AsyncSession) -> dict[str, object]:
    """Every entity in the workspace, keyed by the file it becomes."""
    ws_id = workspace.id

    accounts = (await session.execute(select(Account).where(Account.workspace_id == ws_id))).scalars().all()
    transactions = (await session.execute(select(Transaction).where(Transaction.workspace_id == ws_id))).scalars().all()
    categories = (await session.execute(select(Category).where(Category.workspace_id == ws_id))).scalars().all()
    category_groups = (await session.execute(select(CategoryGroup).where(CategoryGroup.workspace_id == ws_id))).scalars().all()
    rules = (await session.execute(select(Rule).where(Rule.workspace_id == ws_id))).scalars().all()
    recurring_transactions = (await session.execute(select(RecurringTransaction).where(RecurringTransaction.workspace_id == ws_id))).scalars().all()
    budgets = (await session.execute(select(Budget).where(Budget.workspace_id == ws_id))).scalars().all()
    assets = (await session.execute(select(Asset).where(Asset.workspace_id == ws_id))).scalars().all()
    import_logs = (await session.execute(select(ImportLog).where(ImportLog.workspace_id == ws_id))).scalars().all()

    asset_ids = [a.id for a in assets]
    if asset_ids:
        asset_values = (await session.execute(select(AssetValue).where(AssetValue.asset_id.in_(asset_ids)))).scalars().all()
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
    }
    return files
```

In `backend/app/api/export.py`, delete the now-moved `_serialize` and `_collect` function bodies (lines
31-93) and replace the single call site inside the existing `_collect` usages with the service function.
Concretely: remove the `_serialize` function entirely, remove the `_collect` function entirely, and change
its two call sites —

```python
    return _as_download(build_backup_archive(await _collect(ctx, session)))
```

and

```python
    return _as_download(build_backup_archive(await _collect(ctx, session), password))
```

— to:

```python
    return _as_download(build_backup_archive(await backup_service.collect_workspace(ctx.workspace, session)))
```

and

```python
    return _as_download(build_backup_archive(await backup_service.collect_workspace(ctx.workspace, session), password))
```

Update the import at the top of `export.py` from `from app.services.backup_service import
build_backup_archive` to:

```python
from app.services import backup_service
from app.services.backup_service import build_backup_archive
```

Also remove the now-unused per-model imports at the top of `export.py` (`Account`, `Asset`, `AssetValue`,
`Budget`, `Category`, `CategoryGroup`, `ImportLog`, `RecurringTransaction`, `Rule`, `Transaction`, `date`,
`Decimal`) — check each is not used elsewhere in the file (the accountant-export code path uses its own
service and does not touch these) before removing.

- [ ] **Step 4: Run the existing export tests to confirm the refactor is behaviour-preserving**

Run: `cd backend && python -m pytest tests/test_export_api.py -v`
Expected: PASS, same test count as before.

- [ ] **Step 5: Write the export service**

```python
# backend/app/services/data_subject_export_service.py
"""The access/portability package (D1): every workspace the person is a member of, their profile,
sessions, API-token metadata (never the secret) and their own access history — one zip, built the same
way `/api/export/backup` builds a single workspace's.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access_log import ACCESS_ACTIONS
from app.models.api_token import ApiToken
from app.models.audit import AuditEvent
from app.models.user import User
from app.models.user_session import UserSession
from app.models.workspace import Workspace, WorkspaceMember
from app.services.backup_service import build_backup_archive, collect_workspace, serialize_row

#: Never leaves the server: even in a person's own export, the hash and the credential stay put.
_TOKEN_OMIT = {"token_hash"}
_PROFILE_OMIT = {"hashed_password", "totp_secret"}


def _profile(user: User) -> dict:
    row = serialize_row(user)
    for key in _PROFILE_OMIT:
        row.pop(key, None)
    return row


async def _workspaces_of(session: AsyncSession, user: User) -> list[Workspace]:
    result = await session.execute(
        select(Workspace).join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user.id)
    )
    return list(result.scalars().all())


async def _sessions(session: AsyncSession, user: User) -> list[dict]:
    rows = (await session.execute(select(UserSession).where(UserSession.user_id == user.id))).scalars().all()
    return [serialize_row(r) for r in rows]


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


async def build_person_archive(session: AsyncSession, user: User) -> bytes:
    files: dict[str, object] = {
        "profile.json": _profile(user),
        "sessions.json": await _sessions(session, user),
        "api_tokens.json": await _api_tokens(session, user),
        "access_history.json": await _access_history(session, user),
    }
    workspaces = await _workspaces_of(session, user)
    for workspace in workspaces:
        entities = await collect_workspace(workspace, session)
        for name, payload in entities.items():
            files[f"{workspace.id}/{name}"] = payload
    files["metadata.json"] = {
        "export_date": datetime.now(timezone.utc).isoformat(),
        "format_version": "1.0",
        "user_id": str(user.id),
        "workspace_count": len(workspaces),
    }
    return build_backup_archive(files)
```

- [ ] **Step 6: Run the new test to verify it passes**

Run: `cd backend && python -m pytest tests/test_data_subject_export_service.py -v`
Expected: PASS (2 tests). If `test_it_includes_the_workspace_and_profile_and_metadata` fails on the
`hashed_password` assertion, check `serialize_row`'s column iteration in `backup_service.py` — it
serializes every mapped column, so `_PROFILE_OMIT` must run *after* `serialize_row`, which it does; if it
still fails, print `row.keys()` to see the actual column name fastapi-users gives the password hash.

- [ ] **Step 7: Run ruff and the full export test file once more**

Run: `cd backend && python -m ruff check app/api/export.py app/services/backup_service.py app/services/data_subject_export_service.py && python -m pytest tests/test_export_api.py tests/test_data_subject_export_service.py -v`
Expected: `All checks passed!` and all tests PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/api/export.py backend/app/services/backup_service.py \
        backend/app/services/data_subject_export_service.py backend/tests/test_data_subject_export_service.py
git commit -m "feat: person-wide export package for access/portability requests (D1)"
```

---

### Task 4: Email template for erasure confirmation

**Files:**
- Modify: `backend/app/services/email_templates.py` (add `_ERASURE_CONFIRMED` dict + `erasure_confirmed`
  function, following the exact shape of `_NEW_DEVICE`/`new_device_login` at lines 154-190)
- Test: `backend/tests/test_email_templates.py` (extend if it exists; create if not, mirroring whatever
  the existing tests for `account_locked`/`new_device_login` look like — read the current test file for
  those two functions before writing this test, and match its structure)

**Interfaces:**
- Produces: `def erasure_confirmed(language: Optional[str], *, protocol: str, when: str) -> tuple[str,
  str]` (subject, body).

- [ ] **Step 1: Read the existing email-template test file**

Run: `cd backend && python -m pytest --collect-only tests/test_email_templates.py -q` (or search for
`account_locked(` across `tests/` if the file has a different name) to find the exact test structure to
copy — the goal is one test per language plus one for the placeholder substitution, matching whatever
pattern `test_account_locked_email` or similar already uses.

- [ ] **Step 2: Write the failing test**

Add to the discovered test file (or create `backend/tests/test_email_templates.py` if none covers this
module yet, importing `from app.services import email_templates`):

```python
class TestErasureConfirmed:
    def test_it_has_all_three_languages(self):
        for lang in ("en", "pt-BR", "es"):
            subject, body = email_templates.erasure_confirmed(lang, protocol="DSR-2026-000123", when="2026-09-22 10:00")
            assert subject
            assert "DSR-2026-000123" in body

    def test_it_falls_back_to_a_known_language_for_an_unknown_one(self):
        subject, body = email_templates.erasure_confirmed("xx-XX", protocol="DSR-2026-000123", when="now")
        assert subject
```

- [ ] **Step 3: Run it to verify it fails**

Run: `cd backend && python -m pytest tests/test_email_templates.py -k ErasureConfirmed -v`
Expected: FAIL with `AttributeError: module 'app.services.email_templates' has no attribute 'erasure_confirmed'`

- [ ] **Step 4: Add the template**

In `backend/app/services/email_templates.py`, add near `_NEW_DEVICE` (after line 176):

```python
_ERASURE_CONFIRMED = {
    "en": (
        "Your SyncroFin account has been deleted",
        "As requested (protocol {protocol}), your SyncroFin account and its data were deleted on "
        "{when} (UTC).\n\nIf you did not request this, it is too late to recover the account — "
        "contact support immediately so we can investigate.\n",
    ),
    "pt-BR": (
        "Sua conta do SyncroFin foi excluída",
        "Conforme solicitado (protocolo {protocol}), sua conta do SyncroFin e seus dados foram "
        "excluídos em {when} (UTC).\n\nSe você não pediu isso, já não é possível recuperar a conta — "
        "entre em contato com o suporte imediatamente para que possamos investigar.\n",
    ),
    "es": (
        "Tu cuenta de SyncroFin fue eliminada",
        "Según lo solicitado (protocolo {protocol}), tu cuenta de SyncroFin y sus datos fueron "
        "eliminados el {when} (UTC).\n\nSi no lo pediste, ya no es posible recuperar la cuenta — "
        "contacta al soporte de inmediato para que podamos investigar.\n",
    ),
}


def erasure_confirmed(language: Optional[str], *, protocol: str, when: str) -> tuple[str, str]:
    subject, body = _ERASURE_CONFIRMED[resolve_lang(language)]
    return subject, body.format(protocol=protocol, when=when)
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd backend && python -m pytest tests/test_email_templates.py -k ErasureConfirmed -v`
Expected: PASS

- [ ] **Step 6: Run i18n/text-quality checks if the project has them for backend strings**

Run: `cd backend && python -m ruff check app/services/email_templates.py`
Expected: `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/email_templates.py backend/tests/test_email_templates.py
git commit -m "feat: erasure-confirmation e-mail template, 3 languages (D1)"
```

---

### Task 5: The request service — creation, correction, erasure

**Files:**
- Create: `backend/app/services/data_subject_request_service.py`
- Test: `backend/tests/test_data_subject_request_service.py`

**Interfaces:**
- Consumes (Task 1): `DataSubjectRequest`, `KINDS`, `STATUSES`, `generate_protocol`.
- Consumes (Task 2): `user_deletion_service.delete_user_data(session, user)`.
- Consumes (Task 3): `data_subject_export_service.build_person_archive(session, user)`.
- Consumes (Task 4): `email_templates.erasure_confirmed(...)`.
- Produces:
  - `class WrongPassword(Exception)`
  - `class WorkspacesBlockErasure(Exception)` — carries `.workspace_names: list[str]` and `.protocol: str`
    (the `rejected` request is still persisted before this is raised)
  - `async def create_access_or_portability(session, user, kind: str) -> tuple[DataSubjectRequest, bytes]`
  - `async def create_correction(session, user, *, self_service: bool, detail: str | None) ->
    DataSubjectRequest`
  - `async def request_erasure(session, user_manager, user, password: str) -> DataSubjectRequest` (raises
    `WrongPassword` or `WorkspacesBlockErasure`)
  - `async def list_own(session, user) -> list[DataSubjectRequest]`
  - `SELF_SERVICE_LINKS: dict[str, str]` (correction targets, path only — frontend prefixes the origin)

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_data_subject_request_service.py
"""Creating and resolving a data-subject request: access/portability build a package on the spot,
correction is self-served or becomes a ticket, erasure re-authenticates and can be blocked."""
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import UserManager, get_user_db
from app.models.data_subject_request import DataSubjectRequest
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.services import data_subject_request_service as svc

pytestmark = pytest.mark.asyncio


async def _user_manager(session: AsyncSession) -> UserManager:
    from fastapi_users.db import SQLAlchemyUserDatabase
    return UserManager(SQLAlchemyUserDatabase(session, User))


class TestAccessAndPortability:
    async def test_it_resolves_on_the_spot_and_returns_a_package(
        self, session: AsyncSession, test_user: User, test_workspace: Workspace, clean_db
    ):
        for kind in ("access", "portability"):
            row, archive = await svc.create_access_or_portability(session, test_user, kind)
            assert row.status == "resolved_auto"
            assert row.kind == kind
            assert row.protocol.startswith("DSR-")
            assert row.resolved_at is not None
            assert len(archive) > 0


class TestCorrection:
    async def test_self_service_resolves_immediately_without_detail(
        self, session: AsyncSession, test_user: User, clean_db
    ):
        row = await svc.create_correction(session, test_user, self_service=True, detail=None)
        assert row.status == "resolved_auto"

    async def test_non_self_service_requires_detail_and_stays_pending(
        self, session: AsyncSession, test_user: User, clean_db
    ):
        row = await svc.create_correction(session, test_user, self_service=False, detail="meu nome está errado")
        assert row.status == "pending"

    async def test_non_self_service_without_detail_is_rejected(
        self, session: AsyncSession, test_user: User, clean_db
    ):
        with pytest.raises(ValueError):
            await svc.create_correction(session, test_user, self_service=False, detail=None)


class TestErasure:
    async def test_wrong_password_is_refused_and_nothing_is_deleted(
        self, session: AsyncSession, test_user: User, clean_db
    ):
        manager = await _user_manager(session)
        with pytest.raises(svc.WrongPassword):
            await svc.request_erasure(session, manager, test_user, "not-the-password")
        still_there = (await session.execute(select(User).where(User.id == test_user.id))).scalar_one_or_none()
        assert still_there is not None

    async def test_sole_ownership_of_a_shared_workspace_blocks_it(
        self, session: AsyncSession, test_user: User, test_workspace: Workspace, clean_db
    ):
        other = User(
            id=uuid.uuid4(), email="other2@example.com", hashed_password="x",
            is_active=True, is_superuser=False, is_verified=True,
        )
        session.add(other)
        await session.flush()
        session.add(WorkspaceMember(id=uuid.uuid4(), workspace_id=test_workspace.id, user_id=other.id, role="editor"))
        await session.commit()

        manager = await _user_manager(session)
        with pytest.raises(svc.WorkspacesBlockErasure) as exc_info:
            await svc.request_erasure(session, manager, test_user, "testpass123")
        assert test_workspace.name in exc_info.value.workspace_names
        assert exc_info.value.protocol.startswith("DSR-")
        still_there = (await session.execute(select(User).where(User.id == test_user.id))).scalar_one_or_none()
        assert still_there is not None

        rejected = (
            await session.execute(
                select(DataSubjectRequest).where(
                    DataSubjectRequest.user_id == test_user.id, DataSubjectRequest.kind == "erasure"
                )
            )
        ).scalar_one()
        assert rejected.status == "rejected"
        assert test_workspace.name in rejected.resolution_note

    async def test_correct_password_and_no_shared_workspace_deletes_the_account(
        self, session: AsyncSession, test_user: User, test_workspace: Workspace, clean_db
    ):
        manager = await _user_manager(session)
        row = await svc.request_erasure(session, manager, test_user, "testpass123")
        assert row.status == "resolved_auto"
        gone = (await session.execute(select(User).where(User.id == test_user.id))).scalar_one_or_none()
        assert gone is None

    async def test_the_protocol_survives_as_a_create_event_after_the_row_cascades_away(
        self, session: AsyncSession, test_user: User, test_workspace: Workspace, clean_db
    ):
        from app.models.audit import AuditEvent

        manager = await _user_manager(session)
        row = await svc.request_erasure(session, manager, test_user, "testpass123")
        protocol = row.protocol

        event = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.entity_type == "data_subject_requests",
                    AuditEvent.action == "create",
                )
            )
        ).scalars().first()
        assert event is not None
        assert event.changes["protocol"][1] == protocol


class TestListOwn:
    async def test_it_lists_only_the_persons_own_requests_newest_first(
        self, session: AsyncSession, test_user: User, clean_db
    ):
        await svc.create_correction(session, test_user, self_service=True, detail=None)
        await svc.create_correction(session, test_user, self_service=True, detail=None)
        rows = await svc.list_own(session, test_user)
        assert len(rows) == 2
        assert rows[0].created_at >= rows[1].created_at
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && python -m pytest tests/test_data_subject_request_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.data_subject_request_service'`

- [ ] **Step 3: Write the service**

```python
# backend/app/services/data_subject_request_service.py
"""D1: creating and resolving a titular's request. Access/portability resolve on the spot with a
package; correction is self-served or becomes a ticket; erasure re-authenticates, can be blocked by
shared-workspace ownership, and reuses the cascade `user_deletion_service` shares with the admin panel.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import UserManager
from app.models.data_subject_request import DataSubjectRequest, generate_protocol
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.services import data_subject_export_service, email_service, email_templates, user_deletion_service


class WrongPassword(Exception):
    """The re-authentication step of an erasure request did not match the account's password."""


class WorkspacesBlockErasure(Exception):
    """The person is the sole owner of at least one workspace that still has other active members."""

    def __init__(self, workspace_names: list[str], protocol: str) -> None:
        self.workspace_names = workspace_names
        #: A `rejected` request was still recorded (see `request_erasure`) — this is its protocol, so
        #: the person has something to reference if they write in about it.
        self.protocol = protocol
        super().__init__(f"sole owner of: {', '.join(workspace_names)}")


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
        protocol=generate_protocol(),
        user_id=user.id,
        kind=kind,
        status="resolved_auto",
        resolved_at=datetime.now(timezone.utc),
    )
    import uuid as _uuid

    row.id = _uuid.uuid4()
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row, archive


async def create_correction(
    session: AsyncSession, user: User, *, self_service: bool, detail: Optional[str]
) -> DataSubjectRequest:
    import uuid as _uuid

    if not self_service and not detail:
        raise ValueError("detail is required when the person cannot self-serve the correction")
    resolved = self_service
    row = DataSubjectRequest(
        id=_uuid.uuid4(),
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


async def _owned_workspaces_with_other_members(session: AsyncSession, user: User) -> list[Workspace]:
    owned = (
        await session.execute(
            select(Workspace)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .where(WorkspaceMember.user_id == user.id, WorkspaceMember.role == "owner")
        )
    ).scalars().all()
    blocking = []
    for workspace in owned:
        others = (
            await session.execute(
                select(func.count())
                .select_from(WorkspaceMember)
                .where(WorkspaceMember.workspace_id == workspace.id, WorkspaceMember.user_id != user.id)
            )
        ).scalar() or 0
        if others > 0:
            blocking.append(workspace)
    return blocking


async def request_erasure(
    session: AsyncSession, user_manager: UserManager, user: User, password: str
) -> DataSubjectRequest:
    verified, _ = user_manager.password_helper.verify_and_update(password, user.hashed_password)
    if not verified:
        raise WrongPassword()

    blocking = await _owned_workspaces_with_other_members(session, user)
    if blocking:
        import uuid as _uuid

        names = [w.name for w in blocking]
        rejected = DataSubjectRequest(
            id=_uuid.uuid4(),
            protocol=generate_protocol(),
            user_id=user.id,
            kind="erasure",
            status="rejected",
            resolution_note=f"bloqueada por titularidade de workspace compartilhado: {', '.join(names)}",
            resolved_at=datetime.now(timezone.utc),
        )
        session.add(rejected)
        await session.commit()
        raise WorkspacesBlockErasure(names, rejected.protocol)

    import uuid as _uuid

    row = DataSubjectRequest(
        id=_uuid.uuid4(),
        protocol=generate_protocol(),
        user_id=user.id,
        kind="erasure",
        status="resolved_auto",
        resolved_at=datetime.now(timezone.utc),
    )
    session.add(row)
    await session.commit()  # the create event is what survives — see Task 1's docstring
    await session.refresh(row)
    protocol = row.protocol

    # The address must still be readable when the mail is composed: send before the account is gone.
    subject, body = email_templates.erasure_confirmed(
        (user.preferences or {}).get("language"),
        protocol=protocol,
        when=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
    )
    email_service.send_in_background(user.email, subject, body)

    await user_deletion_service.delete_user_data(session, user)
    await session.commit()
    return row


async def list_own(session: AsyncSession, user: User) -> list[DataSubjectRequest]:
    rows = (
        await session.execute(
            select(DataSubjectRequest)
            .where(DataSubjectRequest.user_id == user.id)
            .order_by(DataSubjectRequest.created_at.desc())
        )
    ).scalars().all()
    return list(rows)
```

(The repeated `import uuid as _uuid` inside each function is deliberately consolidated in Step 4 below —
written this way first only to keep each snippet self-contained while drafting; the real file uses one
top-level `import uuid`.)

- [ ] **Step 4: Consolidate the `uuid` import**

Replace every inline `import uuid as _uuid` / `_uuid.uuid4()` with a single top-level `import uuid` and
`uuid.uuid4()` calls, matching the style of every other service file in this codebase (see
`user_deletion_service.py` from Task 2, which already imports `uuid` at the top).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_data_subject_request_service.py -v`
Expected: PASS (11 tests across the 4 test classes). If `test_correct_password_and_no_shared_workspace_deletes_the_account`
fails on the password check, confirm the `test_user` fixture's plaintext password is `"testpass123"`
(`tests/conftest.py:231`) — the test above uses that literal.

- [ ] **Step 6: Run ruff**

Run: `cd backend && python -m ruff check app/services/data_subject_request_service.py`
Expected: `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/data_subject_request_service.py backend/tests/test_data_subject_request_service.py
git commit -m "feat: data-subject request service — access, correction, erasure (D1)"
```

---

### Task 6: API routes

**Files:**
- Create: `backend/app/api/data_requests.py`
- Modify: `backend/app/main.py` (import + `app.include_router`, next to `access_log_router` at line 218)
- Modify: `backend/tests/test_write_permission_coverage.py:37-70` (ALLOWLIST entries)
- Test: `backend/tests/test_data_requests_api.py`

**Interfaces:**
- Consumes (Task 5): every function in `data_subject_request_service`.
- Produces: the 5 routes below, registered under `/api/data-requests` and `/api/admin/data-requests`.

- [ ] **Step 1: Write the failing API tests**

```python
# backend/tests/test_data_requests_api.py
"""The D1 routes: a person's own access/portability/correction/erasure, and the admin's queue."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.workspace import Workspace

pytestmark = pytest.mark.asyncio

BASE = "/api/data-requests"
ADMIN = "/api/admin/data-requests"


class TestOwnRequests:
    async def test_access_returns_a_zip_and_lists_afterwards(
        self, client: AsyncClient, auth_headers: dict, test_workspace: Workspace
    ):
        response = await client.post(BASE, json={"kind": "access"}, headers=auth_headers)
        assert response.status_code == 200, response.text
        assert response.headers["content-type"] == "application/zip"

        listed = await client.get(BASE, headers=auth_headers)
        assert listed.status_code == 200
        assert listed.json()["items"][0]["kind"] == "access"

    async def test_correction_self_service_resolves_immediately(self, client: AsyncClient, auth_headers: dict):
        response = await client.post(
            BASE, json={"kind": "correction", "self_service": True}, headers=auth_headers
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "resolved_auto"

    async def test_correction_without_self_service_needs_detail(self, client: AsyncClient, auth_headers: dict):
        response = await client.post(
            BASE, json={"kind": "correction", "self_service": False}, headers=auth_headers
        )
        assert response.status_code == 422

    async def test_an_unauthenticated_request_is_refused(self, client: AsyncClient):
        response = await client.post(BASE, json={"kind": "access"})
        assert response.status_code == 401

    async def test_an_api_token_is_refused(self, client: AsyncClient, api_token_headers: dict):
        response = await client.post(BASE, json={"kind": "access"}, headers=api_token_headers)
        assert response.status_code == 403


class TestErasure:
    async def test_wrong_password_is_refused(self, client: AsyncClient, auth_headers: dict):
        response = await client.post(f"{BASE}/erasure", json={"password": "wrong"}, headers=auth_headers)
        assert response.status_code == 401

    async def test_correct_password_deletes_the_account(self, client: AsyncClient, auth_headers: dict):
        response = await client.post(f"{BASE}/erasure", json={"password": "testpass123"}, headers=auth_headers)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "resolved_auto"
        again = await client.get(BASE, headers=auth_headers)
        assert again.status_code == 401  # the session's user no longer exists


class TestAdminQueue:
    async def test_a_regular_user_is_refused(self, client: AsyncClient, auth_headers: dict):
        response = await client.get(ADMIN, headers=auth_headers)
        assert response.status_code == 403

    async def test_the_admin_sees_pending_requests_and_can_resolve_them(
        self, client: AsyncClient, auth_headers: dict, admin_auth_headers: dict
    ):
        created = await client.post(
            BASE, json={"kind": "correction", "self_service": False, "detail": "endereço errado"},
            headers=auth_headers,
        )
        request_id = created.json()["id"]

        queue = await client.get(ADMIN, params={"status": "pending"}, headers=admin_auth_headers)
        assert queue.status_code == 200
        assert any(item["id"] == request_id for item in queue.json()["items"])

        resolved = await client.patch(
            f"{ADMIN}/{request_id}", json={"status": "resolved_manual", "resolution_note": "corrigido"},
            headers=admin_auth_headers,
        )
        assert resolved.status_code == 200
        assert resolved.json()["status"] == "resolved_manual"

    async def test_resolving_an_already_resolved_request_is_refused(
        self, client: AsyncClient, auth_headers: dict, admin_auth_headers: dict
    ):
        created = await client.post(BASE, json={"kind": "access"}, headers=auth_headers)
        # `access` resolves immediately — re-parse from the follow-up list call to get its id
        listed = await client.get(BASE, headers=auth_headers)
        request_id = listed.json()["items"][0]["id"]

        response = await client.patch(
            f"{ADMIN}/{request_id}", json={"status": "resolved_manual"}, headers=admin_auth_headers
        )
        assert response.status_code == 409
```

If `api_token_headers` is not an existing fixture, check `tests/conftest.py` and `tests/test_api_tokens.py`
for the actual fixture name that yields headers with a valid API-token `Authorization` value, and use that
name instead — do not invent a new fixture for this.

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && python -m pytest tests/test_data_requests_api.py -v`
Expected: FAIL with 404s (route module doesn't exist yet)

- [ ] **Step 3: Write the routes**

```python
# backend/app/api/data_requests.py
"""The D1 channel: a person's own access/portability/correction/erasure requests, and the admin's queue."""
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import current_active_user, current_superuser, get_user_manager
from app.core.database import get_async_session
from app.models.data_subject_request import KINDS, STATUSES, DataSubjectRequest
from app.models.user import User
from app.services import data_subject_request_service as svc

router = APIRouter(tags=["data-requests"])


class DataRequestRead(BaseModel):
    id: UUID
    protocol: str
    kind: str
    status: str
    created_at: datetime
    due_at: datetime
    resolved_at: Optional[datetime] = None
    detail: Optional[str] = None
    resolution_note: Optional[str] = None

    model_config = {"from_attributes": True}


class DataRequestPage(BaseModel):
    items: list[DataRequestRead]


class CreateDataRequest(BaseModel):
    kind: str
    self_service: Optional[bool] = None
    detail: Optional[str] = None


class ErasureBody(BaseModel):
    password: str


class AdminResolve(BaseModel):
    status: str = Field(pattern="^(resolved_manual|rejected)$")
    resolution_note: Optional[str] = None


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


BASE_PATH = "/api/data-requests"


@router.post(BASE_PATH)
async def create_request(
    body: CreateDataRequest,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    if body.kind not in KINDS:
        raise HTTPException(status_code=422, detail="UNKNOWN_REQUEST_KIND")

    if body.kind in ("access", "portability"):
        row, archive = await svc.create_access_or_portability(session, user, body.kind)
        return StreamingResponse(
            iter([archive]),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="syncrofin-dados-{_today()}.zip"'},
        )

    if body.kind == "correction":
        if body.self_service is None:
            raise HTTPException(status_code=422, detail="SELF_SERVICE_REQUIRED")
        try:
            row = await svc.create_correction(
                session, user, self_service=body.self_service, detail=body.detail
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        return DataRequestRead.model_validate(row)

    raise HTTPException(status_code=422, detail="USE_THE_EROSURE_ROUTE_FOR_ERASURE")


@router.get(BASE_PATH, response_model=DataRequestPage)
async def list_my_requests(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    rows = await svc.list_own(session, user)
    return DataRequestPage(items=[DataRequestRead.model_validate(r) for r in rows])


@router.post(f"{BASE_PATH}/erasure")
async def erasure(
    body: ErasureBody,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
    user_manager=Depends(get_user_manager),
):
    try:
        row = await svc.request_erasure(session, user_manager, user, body.password)
    except svc.WrongPassword:
        raise HTTPException(status_code=401, detail="WRONG_PASSWORD")
    except svc.WorkspacesBlockErasure as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "WORKSPACES_BLOCK_ERASURE",
                "workspaces": exc.workspace_names,
                "protocol": exc.protocol,
            },
        )
    return DataRequestRead.model_validate(row)


@router.get("/api/admin/data-requests", response_model=DataRequestPage)
async def admin_list(
    status: Optional[str] = Query(None),
    _: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
):
    if status is not None and status not in STATUSES:
        raise HTTPException(status_code=422, detail="UNKNOWN_STATUS")
    conditions = [DataSubjectRequest.status == status] if status else []
    rows = (
        await session.execute(
            select(DataSubjectRequest).where(*conditions).order_by(DataSubjectRequest.created_at.desc())
        )
    ).scalars().all()
    return DataRequestPage(items=[DataRequestRead.model_validate(r) for r in rows])


@router.patch("/api/admin/data-requests/{request_id}", response_model=DataRequestRead)
async def admin_resolve(
    request_id: UUID,
    body: AdminResolve,
    _: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
):
    row = await session.get(DataSubjectRequest, request_id)
    if row is None:
        raise HTTPException(status_code=404)
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="ALREADY_RESOLVED")
    row.status = body.status
    row.resolution_note = body.resolution_note
    row.resolved_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(row)
    return DataRequestRead.model_validate(row)
```

- [ ] **Step 4: Register the router**

In `backend/app/main.py`, add the import near `from app.api.access_log import router as access_log_router`
(around line 41):

```python
from app.api.data_requests import router as data_requests_router
```

And register it near `app.include_router(access_log_router)` (around line 218):

```python
app.include_router(data_requests_router)
```

- [ ] **Step 5: Add the write-permission allowlist entries**

In `backend/tests/test_write_permission_coverage.py`, inside `ALLOWLIST` (starting line 37), add, next to
the other "not workspace-scoped" entries:

```python
    ("POST", "/api/data-requests"): "the requester's own data-subject request",
    ("POST", "/api/data-requests/erasure"): "the requester's own data-subject request",
    ("PATCH", "/api/admin/data-requests/{request_id}"): "superuser-gated instance administration",
```

- [ ] **Step 6: Run the new API tests**

Run: `cd backend && python -m pytest tests/test_data_requests_api.py -v`
Expected: PASS. If `test_an_api_token_is_refused` fails, confirm the fixture name from Step 1 actually
exercises an API-token bearer header (`tests/test_api_tokens.py` has the definitive example of issuing one
inside a test if no fixture exists — copy that pattern into a local fixture in
`test_data_requests_api.py` instead of relying on a nonexistent shared one).

- [ ] **Step 7: Run the write-permission coverage test**

Run: `cd backend && python -m pytest tests/test_write_permission_coverage.py -v`
Expected: PASS — this is what confirms Step 5 was necessary (without it, the parametrized "every mutating
route declares a permission decision" test fails for all three new routes).

- [ ] **Step 8: Run ruff and ty on the new/changed files**

Run: `cd backend && python -m ruff check app/api/data_requests.py app/main.py tests/test_data_requests_api.py tests/test_write_permission_coverage.py`
Run: `cd backend && python -m ty check app/api/data_requests.py` (if `ty` is the project's type checker per
`docs/FASE1.md` — confirm the exact invocation from `docs/FASE1.md` or a CI workflow file if this command
doesn't match)
Expected: `All checks passed!` / no new errors.

- [ ] **Step 9: Commit**

```bash
git add backend/app/api/data_requests.py backend/app/main.py backend/tests/test_data_requests_api.py \
        backend/tests/test_write_permission_coverage.py
git commit -m "feat: API routes for the data-subject request channel (D1)"
```

---

### Task 7: Full-suite verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend suite**

Run: `cd backend && TZ=UTC0 python -m pytest tests -n 4 -q 2>&1 | tee /tmp/d1-suite.log` (adapt the `tee`
target to the session's scratchpad directory instead of `/tmp` on Windows/Git Bash)
Expected: all tests pass, 0 failures. Compare the total count against the pre-D1 baseline (4277, per the
D3 delivery) — it should grow by roughly the number of tests added in Tasks 1, 2, 3, 4, 5, 6.

- [ ] **Step 2: Run ruff and ty across the whole backend**

Run: `cd backend && python -m ruff check . && python -m ty check .` (or whatever exact `ty` invocation
`docs/FASE1.md`/CI uses)
Expected: clean on both.

- [ ] **Step 3: Run the migration-chain check**

Run: `cd backend && python scripts/check_migration_chain.py` (confirm this script's actual path first —
it's referenced in `docs/FASE1.md`'s pre-PR checklist)
Expected: no gaps, revision `100` is the head.

- [ ] **Step 4: Manual e2e smoke against the real dev stack (optional but recommended before the PR)**

Follow the same shape as the D3 delivery's e2e script (`docs/superpowers/plans/` sibling or the prior
session's scratchpad `e2e_d3.py` for the pattern): sign in, `POST /api/data-requests` with `kind: access`
and confirm a non-empty zip comes back; `POST /api/data-requests/erasure` with the right password on a
throwaway test account and confirm the account can no longer sign in afterward.

- [ ] **Step 5: Report status**

No commit for this task — it is the checkpoint before moving to the frontend/docs plan (Part 2) or opening
the PR, whichever the user chooses next.
