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

    async def test_sessions_do_not_include_refresh_token_hashes(
        self, session: AsyncSession, test_user: User, test_workspace: Workspace, clean_db
    ):
        import uuid
        from datetime import datetime, timedelta, timezone

        from app.models.user_session import UserSession

        session.add(UserSession(
            id=uuid.uuid4(),
            user_id=test_user.id,
            refresh_hash="a" * 64,
            previous_refresh_hash="b" * 64,
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        ))
        await session.commit()

        archive = await data_subject_export_service.build_person_archive(session, test_user)
        zf = zipfile.ZipFile(io.BytesIO(archive))
        names = zf.namelist()
        sessions = json.loads(zf.read(next(n for n in names if n.endswith("sessions.json"))))
        assert len(sessions) == 1
        assert "refresh_hash" not in sessions[0]
        assert "previous_refresh_hash" not in sessions[0]

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

    async def test_it_covers_a_workspace_the_person_only_manages_externally(
        self, session: AsyncSession, test_user: User, test_workspace: Workspace, clean_db
    ):
        import uuid

        managed = Workspace(
            id=uuid.uuid4(),
            name="Managed externally",
            kind="business",
            created_by_user_id=test_user.id,
            managed_by_user_id=test_user.id,
        )
        session.add(managed)
        await session.commit()

        archive = await data_subject_export_service.build_person_archive(session, test_user)
        names = zipfile.ZipFile(io.BytesIO(archive)).namelist()
        workspace_folders = {name.split("/")[0] for name in names if "/" in name}
        assert str(managed.id) in workspace_folders

    async def test_shared_workspace_is_scoped_to_the_persons_own_transactions(
        self, session: AsyncSession, test_user: User, test_workspace: Workspace, clean_db
    ):
        """test_workspace has a second member added here; each of them has their own transaction. The
        archive's copy of that workspace must contain only test_user's, not the other member's."""
        import uuid

        from app.models.account import Account
        from app.models.transaction import Transaction
        from app.models.workspace import WorkspaceMember

        other = User(
            id=uuid.uuid4(), email="other-export@example.com", hashed_password="x",
            is_active=True, is_superuser=False, is_verified=True,
        )
        session.add(other)
        await session.flush()
        session.add(WorkspaceMember(
            id=uuid.uuid4(), workspace_id=test_workspace.id, user_id=other.id, role="editor"
        ))

        mine = Account(
            id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id,
            name="Minha conta", type="checking", currency="BRL",
        )
        theirs = Account(
            id=uuid.uuid4(), user_id=other.id, workspace_id=test_workspace.id,
            name="Conta do outro", type="checking", currency="BRL",
        )
        session.add_all([mine, theirs])
        await session.flush()

        from datetime import date

        tx_mine = Transaction(
            id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id, account_id=mine.id,
            description="Minha transação", amount="10.00", date=date.today(), type="debit", source="manual",
        )
        tx_theirs = Transaction(
            id=uuid.uuid4(), user_id=other.id, workspace_id=test_workspace.id, account_id=theirs.id,
            description="Transação do outro", amount="20.00", date=date.today(), type="debit", source="manual",
        )
        session.add_all([tx_mine, tx_theirs])
        await session.commit()

        archive = await data_subject_export_service.build_person_archive(session, test_user)
        zf = zipfile.ZipFile(io.BytesIO(archive))
        names = zf.namelist()
        tx_name = next(n for n in names if f"{test_workspace.id}" in n and n.endswith("transactions.json"))
        transactions = json.loads(zf.read(tx_name))
        assert len(transactions) == 1
        assert transactions[0]["description"] == "Minha transação"

        accounts_name = next(n for n in names if f"{test_workspace.id}" in n and n.endswith("accounts.json"))
        accounts = json.loads(zf.read(accounts_name))
        assert len(accounts) == 1
        assert accounts[0]["name"] == "Minha conta"

        metadata_name = next(
            n for n in names if n.startswith(f"{test_workspace.id}/") and n.endswith("metadata.json")
        )
        metadata = json.loads(zf.read(metadata_name))
        assert metadata["scope"] == "own_records_only"

    async def test_sole_member_workspace_still_gets_the_full_collection(
        self, session: AsyncSession, test_user: User, test_workspace: Workspace, clean_db
    ):
        """Regression: test_user is the sole member of test_workspace (the default fixture), so the
        archive must still use the full `collect_workspace` collection, scoped as "full_workspace"."""
        archive = await data_subject_export_service.build_person_archive(session, test_user)
        zf = zipfile.ZipFile(io.BytesIO(archive))
        names = zf.namelist()
        metadata_name = next(
            n for n in names if n.startswith(f"{test_workspace.id}/") and n.endswith("metadata.json")
        )
        metadata = json.loads(zf.read(metadata_name))
        assert metadata["scope"] == "full_workspace"

    async def test_it_covers_an_archived_workspace_the_person_is_a_member_of(
        self, session: AsyncSession, test_user: User, clean_db
    ):
        import uuid
        from app.models.workspace import WorkspaceMember

        archived = Workspace(
            id=uuid.uuid4(),
            name="Archived",
            kind="business",
            created_by_user_id=test_user.id,
            is_archived=True,
        )
        session.add(archived)
        await session.flush()
        session.add(WorkspaceMember(id=uuid.uuid4(), workspace_id=archived.id, user_id=test_user.id, role="owner"))
        await session.commit()

        archive = await data_subject_export_service.build_person_archive(session, test_user)
        names = zipfile.ZipFile(io.BytesIO(archive)).namelist()
        workspace_folders = {name.split("/")[0] for name in names if "/" in name}
        assert str(archived.id) in workspace_folders
