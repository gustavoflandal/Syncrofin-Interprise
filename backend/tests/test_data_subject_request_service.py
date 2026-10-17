"""Creating and resolving a data-subject request: access/portability build a package on the spot,
correction is self-served or becomes a ticket, erasure re-authenticates and can be blocked."""
import uuid
from email.message import EmailMessage

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import UserManager
from app.core.config import get_settings
from app.models.data_subject_request import DataSubjectRequest
from app.models.goal import Goal
from app.models.group import Group
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.services import data_subject_request_service as svc, email_service

pytestmark = pytest.mark.asyncio


async def _user_manager(session: AsyncSession) -> UserManager:
    from fastapi_users.db import SQLAlchemyUserDatabase
    return UserManager(SQLAlchemyUserDatabase(session, User))


@pytest.fixture
def outbox(monkeypatch) -> list[EmailMessage]:
    """E-mail switched on, with the SMTP hand-off captured instead of sent — the same fixture
    `tests/test_email_flows.py` uses for the password-reset flow, copied locally (not imported: pytest
    fixtures are file-local unless promoted to a conftest, which no other D1 test needs)."""
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "smtp.test.local")
    monkeypatch.setattr(settings, "smtp_from", "SyncroFin <no-reply@test.local>")
    sent: list[EmailMessage] = []
    monkeypatch.setattr(email_service, "send_blocking", lambda _settings, msg: sent.append(msg))
    return sent


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

    async def test_wrong_password_records_an_access_event(
        self, session: AsyncSession, test_user: User, clean_db
    ):
        from app.models.audit import AuditEvent

        manager = await _user_manager(session)
        with pytest.raises(svc.WrongPassword):
            await svc.request_erasure(session, manager, test_user, "not-the-password")

        event = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "erasure_password_failed",
                    AuditEvent.entity_id == str(test_user.id),
                )
            )
        ).scalars().first()
        assert event is not None
        assert event.entity_type == "user"

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
        assert rejected.resolution_note is not None
        assert test_workspace.name in rejected.resolution_note

    async def test_editor_with_own_data_in_someone_elses_shared_workspace_blocks_it(
        self, session: AsyncSession, test_user: User, clean_db
    ):
        """test_user is NOT role='owner' here — merely an editor with their own Account row in a
        workspace owned by a different person and shared with a third member. This is the new coverage:
        the old owner-only check would have let this erasure through and destroyed the account row."""
        from app.models.account import Account

        owner = User(
            id=uuid.uuid4(), email="owner3@example.com", hashed_password="x",
            is_active=True, is_superuser=False, is_verified=True,
        )
        third = User(
            id=uuid.uuid4(), email="third3@example.com", hashed_password="x",
            is_active=True, is_superuser=False, is_verified=True,
        )
        session.add_all([owner, third])
        await session.flush()

        shared = Workspace(
            id=uuid.uuid4(), name="Workspace Compartilhado", kind="personal",
            created_by_user_id=owner.id, default_currency="BRL",
        )
        session.add(shared)
        await session.flush()
        session.add_all([
            WorkspaceMember(id=uuid.uuid4(), workspace_id=shared.id, user_id=owner.id, role="owner"),
            WorkspaceMember(id=uuid.uuid4(), workspace_id=shared.id, user_id=test_user.id, role="editor"),
            WorkspaceMember(id=uuid.uuid4(), workspace_id=shared.id, user_id=third.id, role="viewer"),
        ])
        account = Account(
            id=uuid.uuid4(), user_id=test_user.id, workspace_id=shared.id,
            name="Conta lançada pelo editor", type="checking", currency="BRL",
        )
        session.add(account)
        await session.commit()

        manager = await _user_manager(session)
        with pytest.raises(svc.WorkspacesBlockErasure) as exc_info:
            await svc.request_erasure(session, manager, test_user, "testpass123")
        assert shared.name in exc_info.value.workspace_names

        still_there = (
            await session.execute(select(Account).where(Account.id == account.id))
        ).scalar_one_or_none()
        assert still_there is not None

        user_still_there = (await session.execute(select(User).where(User.id == test_user.id))).scalar_one_or_none()
        assert user_still_there is not None

    async def test_member_who_created_a_shared_group_blocks_it(
        self, session: AsyncSession, test_user: User, clean_db
    ):
        """`Group` carries `ondelete="CASCADE"` (not "none"), so it's never in
        `_OWNED_DATA_MODELS_WITH_WORKSPACE`'s original set — but it's visible to every workspace member
        (see `group_service.py`), and self-erasure would otherwise silently cascade-delete it, its
        members and its settlements out from under the other members with no block at all. test_user
        has ZERO rows in any of the already-covered tables — only this Group."""
        owner = User(
            id=uuid.uuid4(), email="owner4@example.com", hashed_password="x",
            is_active=True, is_superuser=False, is_verified=True,
        )
        third = User(
            id=uuid.uuid4(), email="third4@example.com", hashed_password="x",
            is_active=True, is_superuser=False, is_verified=True,
        )
        session.add_all([owner, third])
        await session.flush()

        shared = Workspace(
            id=uuid.uuid4(), name="Workspace com Grupo", kind="personal",
            created_by_user_id=owner.id, default_currency="BRL",
        )
        session.add(shared)
        await session.flush()
        session.add_all([
            WorkspaceMember(id=uuid.uuid4(), workspace_id=shared.id, user_id=owner.id, role="owner"),
            WorkspaceMember(id=uuid.uuid4(), workspace_id=shared.id, user_id=test_user.id, role="editor"),
            WorkspaceMember(id=uuid.uuid4(), workspace_id=shared.id, user_id=third.id, role="viewer"),
        ])
        group = Group(
            id=uuid.uuid4(), user_id=test_user.id, workspace_id=shared.id, name="Viagem em grupo",
        )
        session.add(group)
        await session.commit()

        manager = await _user_manager(session)
        with pytest.raises(svc.WorkspacesBlockErasure) as exc_info:
            await svc.request_erasure(session, manager, test_user, "testpass123")
        assert shared.name in exc_info.value.workspace_names

        still_there = (await session.execute(select(Group).where(Group.id == group.id))).scalar_one_or_none()
        assert still_there is not None

        user_still_there = (await session.execute(select(User).where(User.id == test_user.id))).scalar_one_or_none()
        assert user_still_there is not None

    async def test_sole_member_workspace_with_a_goal_erases_successfully(
        self, session: AsyncSession, test_user: User, test_workspace: Workspace, clean_db
    ):
        """Regression test for the actual bug users would have hit: before this fix, `Goal.user_id` had
        no `ondelete` action and wasn't in `_delete_owned_data`, so erasing an account that owned a Goal
        raised a `ForeignKeyViolation` (500) even for the ordinary case of a sole member erasing their
        own solo workspace — the erasure right simply didn't work for those accounts."""
        goal = Goal(
            id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id,
            name="Viagem", target_amount="2000.00",
        )
        session.add(goal)
        await session.commit()

        manager = await _user_manager(session)
        row = await svc.request_erasure(session, manager, test_user, "testpass123")
        assert row.status == "resolved_auto"

        gone = (await session.execute(select(User).where(User.id == test_user.id))).scalar_one_or_none()
        assert gone is None
        goal_gone = (await session.execute(select(Goal).where(Goal.id == goal.id))).scalar_one_or_none()
        assert goal_gone is None

    async def test_sole_member_workspace_with_own_data_is_not_blocked(
        self, session: AsyncSession, test_user: User, test_workspace: Workspace, clean_db
    ):
        """The common case: test_user's own solo "Pessoal" workspace, with data in it, and nobody else
        as a member. Must NOT be blocked."""
        from app.models.account import Account

        account = Account(
            id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id,
            name="Conta pessoal", type="checking", currency="BRL",
        )
        session.add(account)
        await session.commit()

        manager = await _user_manager(session)
        row = await svc.request_erasure(session, manager, test_user, "testpass123")
        assert row.status == "resolved_auto"
        gone = (await session.execute(select(User).where(User.id == test_user.id))).scalar_one_or_none()
        assert gone is None

    async def test_correct_password_and_no_shared_workspace_deletes_the_account(
        self, session: AsyncSession, test_user: User, test_workspace: Workspace, clean_db
    ):
        manager = await _user_manager(session)
        row = await svc.request_erasure(session, manager, test_user, "testpass123")
        assert row.status == "resolved_auto"
        gone = (await session.execute(select(User).where(User.id == test_user.id))).scalar_one_or_none()
        assert gone is None

    async def test_a_failed_cascade_leaves_no_false_success_and_sends_no_email(
        self, session: AsyncSession, test_user: User, test_workspace: Workspace, clean_db, outbox, monkeypatch
    ):
        """Third-round fix: before it, the `DataSubjectRequest` row was committed and the confirmation
        e-mail sent BEFORE `delete_user_data` ran, so a failed cascade (a `ForeignKeyViolation`, e.g.)
        left the person told "your account was deleted" by e-mail while their account and data were
        completely untouched. Simulated here via monkeypatch — Fix 1/2 above closed every FK-ordering
        gap this suite could otherwise trigger for real."""
        from app.services import user_deletion_service

        class _SimulatedCascadeFailure(Exception):
            pass

        async def _boom(_session, _user):
            raise _SimulatedCascadeFailure("simulated ForeignKeyViolation")

        monkeypatch.setattr(user_deletion_service, "delete_user_data", _boom)

        # Captured before the rollback below: `session.rollback()` expires every object in the
        # session, `test_user` included, and an expired attribute can't be re-fetched by plain
        # attribute access on an AsyncSession outside a greenlet (`MissingGreenlet`) — only an
        # explicit `await` can do that, so the plain uuid is grabbed first instead.
        user_id = test_user.id

        manager = await _user_manager(session)
        with pytest.raises(_SimulatedCascadeFailure):
            await svc.request_erasure(session, manager, test_user, "testpass123")
        # Mirrors what closing the request-scoped session on an unhandled exception does in production
        # (`get_async_session`'s `async with` block) — discards the row `request_erasure` had
        # `session.add`ed but, per the fix, never got to commit.
        await session.rollback()

        await email_service.drain()
        assert len(outbox) == 0

        still_there = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        assert still_there is not None

        resolved = (
            await session.execute(
                select(DataSubjectRequest).where(
                    DataSubjectRequest.user_id == user_id,
                    DataSubjectRequest.kind == "erasure",
                    DataSubjectRequest.status == "resolved_auto",
                )
            )
        ).scalar_one_or_none()
        assert resolved is None

    async def test_the_confirmation_email_is_actually_sent_after_the_deletion_commits(
        self, session: AsyncSession, test_user: User, test_workspace: Workspace, clean_db, outbox
    ):
        """The send happens only after `delete_user_data`'s commit has actually succeeded (see
        `request_erasure`'s own comment on that ordering — a third-round fix moved it here specifically
        so nothing claims success before the deletion does), reading `user.email` off the in-memory,
        post-commit, post-delete object (`expire_on_commit=False` keeps it populated)."""
        expected_email = test_user.email
        manager = await _user_manager(session)
        row = await svc.request_erasure(session, manager, test_user, "testpass123")
        protocol = row.protocol

        await email_service.drain()

        assert len(outbox) == 1
        msg = outbox[0]
        assert msg["To"] == expected_email
        assert protocol in msg.get_content()

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
        assert event.changes is not None
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
