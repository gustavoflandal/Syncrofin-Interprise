"""The audit trail: what it records, who it blames, and that nobody can rewrite it."""
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_event, seal
from app.models.account import Account
from app.models.audit import AuditEvent
from app.models.category import Category
from app.models.user import User
from app.models.workspace import Workspace


async def _events(session: AsyncSession, **where) -> list[AuditEvent]:
    query = select(AuditEvent).order_by(AuditEvent.occurred_at, AuditEvent.id)
    for column, value in where.items():
        query = query.where(getattr(AuditEvent, column) == value)
    result = await session.execute(query.execution_options(populate_existing=True))
    return list(result.scalars().all())


@pytest_asyncio.fixture
async def account(session: AsyncSession, test_user: User, test_workspace: Workspace) -> Account:
    row = Account(
        id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id,
        name="Conta corrente", type="checking", balance=Decimal("100.00"), currency="BRL",
    )
    session.add(row)
    await session.commit()
    return row


@pytest.mark.asyncio
class TestWhatIsRecorded:
    async def test_a_created_row_is_recorded_with_its_values(
        self, session: AsyncSession, account: Account, test_workspace: Workspace
    ):
        [event] = await _events(session, entity_type="accounts", entity_id=str(account.id))
        assert event.action == "create"
        assert event.workspace_id == test_workspace.id
        assert event.changes is not None
        assert event.changes["name"] == [None, "Conta corrente"]
        assert event.changes["balance"] == [None, "100.00"]

    async def test_an_update_records_only_what_changed_before_and_after(
        self, session: AsyncSession, account: Account
    ):
        account.name = "Conta principal"
        await session.commit()

        updates = [e for e in await _events(session, entity_id=str(account.id)) if e.action == "update"]
        assert len(updates) == 1
        assert updates[0].changes == {"name": ["Conta corrente", "Conta principal"]}

    async def test_a_row_whose_key_is_not_called_id_is_identified_by_it(self, session: AsyncSession):
        """`app_settings` is keyed by `key`: a row created in this flush has no identity key yet."""
        from app.models.app_settings import AppSetting

        session.add(AppSetting(key="registration_enabled", value="false"))
        await session.commit()

        [event] = await _events(session, entity_type="app_settings")
        assert event.entity_id == "registration_enabled" and event.action == "create"

    async def test_a_delete_keeps_what_the_row_held(self, session: AsyncSession, account: Account):
        account_id = str(account.id)
        await session.delete(account)
        await session.commit()

        deletes = [e for e in await _events(session, entity_id=account_id) if e.action == "delete"]
        assert len(deletes) == 1
        assert deletes[0].changes is not None
        assert deletes[0].changes["name"] == ["Conta corrente", None]

    async def test_a_change_that_rolls_back_leaves_no_trace(
        self, session: AsyncSession, test_user: User, test_workspace: Workspace
    ):
        ghost = Category(
            id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id,
            name="Fantasma", icon="tag", color="#000000",
        )
        session.add(ghost)
        await session.flush()
        await session.rollback()

        assert await _events(session, entity_id=str(ghost.id)) == []

    async def test_a_balance_that_moves_on_its_own_is_not_an_event(
        self, session: AsyncSession, account: Account
    ):
        account.balance = Decimal("250.00")
        await session.commit()

        updates = [e for e in await _events(session, entity_id=str(account.id)) if e.action == "update"]
        assert updates == []

    async def test_secrets_are_masked_not_stored(self, session: AsyncSession, test_user: User):
        test_user.totp_secret = "JBSWY3DPEHPK3PXP"
        await session.commit()

        [event] = [e for e in await _events(session, entity_id=str(test_user.id)) if e.action == "update"]
        assert event.changes == {"totp_secret": [None, "***"]}
        everything = [e.changes for e in await _events(session, entity_id=str(test_user.id))]
        assert "JBSWY3DPEHPK3PXP" not in str(everything)
        assert "bcrypt" not in str(everything) and "$2b$" not in str(everything)

    async def test_data_subject_request_detail_and_resolution_note_are_masked(
        self, session: AsyncSession, test_user: User
    ):
        """D1 Fix 7: `detail`/`resolution_note` carry free text a titular writes (or an admin writes
        about them) — masked (the fact that it changed is kept), not left in the clear."""
        from app.models.data_subject_request import DataSubjectRequest, generate_protocol

        row = DataSubjectRequest(
            id=uuid.uuid4(),
            protocol=generate_protocol(),
            user_id=test_user.id,
            kind="correction",
            status="pending",
            detail="meu endereço mudou para Rua das Flores, 123",
        )
        session.add(row)
        await session.commit()

        [created] = [
            e for e in await _events(session, entity_type="data_subject_requests", entity_id=str(row.id))
            if e.action == "create"
        ]
        assert created.changes is not None
        assert created.changes["detail"] == [None, "***"]
        assert "Rua das Flores" not in str(created.changes)

        row.status = "resolved_manual"
        row.resolution_note = "corrigido manualmente, endereço confirmado por telefone com o titular"
        await session.commit()

        [updated] = [
            e for e in await _events(session, entity_type="data_subject_requests", entity_id=str(row.id))
            if e.action == "update"
        ]
        assert updated.changes is not None
        assert updated.changes["resolution_note"] == [None, "***"]
        assert "confirmado por telefone" not in str(updated.changes)

    async def test_a_user_deletes_email_is_masked_not_stored(self, session: AsyncSession):
        """D1 Fix 7: the pre-existing admin-delete behaviour (the e-mail in clear text on a User delete
        event) is now self-service-reachable via erasure, so it is masked like every other secret."""
        other = User(
            id=uuid.uuid4(), email="to-be-erased@example.com", hashed_password="x",
            is_active=True, is_superuser=False, is_verified=True,
        )
        session.add(other)
        await session.commit()
        other_id = other.id

        await session.delete(other)
        await session.commit()

        [event] = [e for e in await _events(session, entity_type="users", entity_id=str(other_id)) if e.action == "delete"]
        assert event.changes is not None
        assert event.changes["email"] == ["***", None]
        assert "to-be-erased@example.com" not in str(event.changes)


@pytest.mark.asyncio
class TestWhoDidIt:
    async def test_a_request_is_attributed_to_the_signed_in_user(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict, test_user: User
    ):
        response = await client.post(
            "/api/categories",
            json={"name": "Assinaturas", "icon": "tag", "color": "#112233"},
            headers={**auth_headers, "User-Agent": "pytest-audit"},
        )
        assert response.status_code in (200, 201), response.text
        created = response.json()["id"]

        [event] = await _events(session, entity_type="categories", entity_id=created)
        assert event.action == "create"
        assert event.actor_user_id == test_user.id
        assert event.actor_kind == "user"
        assert event.user_agent == "pytest-audit"
        assert event.request_id
        assert response.headers["x-request-id"] == event.request_id

    async def test_work_outside_a_request_is_the_systems(
        self, session: AsyncSession, account: Account
    ):
        [event] = await _events(session, entity_id=str(account.id))
        assert event.actor_kind == "system"
        assert event.actor_user_id is None

    async def test_the_address_comes_from_the_trusted_proxy_chain(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict
    ):
        from app.core.config import get_settings

        settings = get_settings()
        previous = settings.trusted_proxy_hops
        settings.trusted_proxy_hops = 1
        try:
            response = await client.post(
                "/api/categories",
                json={"name": "Com IP", "icon": "tag", "color": "#112233"},
                headers={**auth_headers, "X-Forwarded-For": "198.51.100.7"},
            )
        finally:
            settings.trusted_proxy_hops = previous
        [event] = await _events(session, entity_id=response.json()["id"])
        assert event.ip == "198.51.100.7"


@pytest.mark.asyncio
class TestNobodyCanRewriteIt:
    async def test_update_is_refused_even_for_the_database_owner(
        self, session: AsyncSession, account: Account
    ):
        with pytest.raises(DBAPIError, match="append-only"):
            await session.execute(text("UPDATE audit_events SET action = 'nothing happened'"))
        await session.rollback()

    async def test_delete_is_refused(self, session: AsyncSession, account: Account):
        with pytest.raises(DBAPIError, match="append-only"):
            await session.execute(text("DELETE FROM audit_events"))
        await session.rollback()

    async def test_truncate_is_refused(self, session: AsyncSession, account: Account):
        with pytest.raises(DBAPIError, match="append-only"):
            await session.execute(text("TRUNCATE audit_events"))
        await session.rollback()

    async def test_a_sealed_row_cannot_be_given_a_new_hash_by_hand(
        self, session: AsyncSession, account: Account
    ):
        await seal(session)
        with pytest.raises(DBAPIError, match="append-only"):
            await session.execute(text("UPDATE audit_events SET hash = repeat('a', 64)"))
        await session.rollback()

    async def test_the_content_of_an_unsealed_row_cannot_be_changed_either(
        self, session: AsyncSession, account: Account
    ):
        with pytest.raises(DBAPIError, match="append-only"):
            await session.execute(text("UPDATE audit_events SET entity_type = 'x' WHERE hash IS NULL"))
        await session.rollback()


@pytest.mark.asyncio
class TestTheChain:
    async def test_sealing_chains_every_event_in_order(
        self, session: AsyncSession, account: Account
    ):
        account.name = "Outro nome"
        await session.commit()

        assert await seal(session) >= 2
        events = [e for e in await _events(session) if e.seq is not None]
        events.sort(key=lambda e: e.seq or 0)
        assert [e.seq for e in events] == list(range(1, len(events) + 1))
        assert events[0].prev_hash == "0" * 64
        for before, after in zip(events, events[1:]):
            assert after.prev_hash == before.hash
        assert await seal(session) == 0, "nothing left to seal"

    async def test_a_new_event_continues_the_chain(self, session: AsyncSession, account: Account):
        await seal(session)
        session.add(Category(id=uuid.uuid4(), user_id=account.user_id, workspace_id=account.workspace_id,
                             name="Nova", icon="tag", color="#000000"))
        await session.commit()
        await seal(session)

        events = sorted([e for e in await _events(session) if e.seq is not None], key=lambda e: e.seq or 0)
        assert events[-1].prev_hash == events[-2].hash

    async def test_verify_passes_on_an_untouched_trail(
        self, client: AsyncClient, admin_auth_headers: dict, session: AsyncSession
    ):
        result = (await client.get("/api/audit/verify", headers=admin_auth_headers)).json()
        assert result["ok"] is True
        assert result["checked"] >= 1
        assert result["head_hash"]

    async def _tamper(self, session: AsyncSession, sql: str) -> None:
        """What someone with the database's own credentials could do: switch the guard off first."""
        await session.execute(text("ALTER TABLE audit_events DISABLE TRIGGER USER"))
        await session.execute(text(sql))
        await session.execute(text("ALTER TABLE audit_events ENABLE TRIGGER USER"))
        await session.commit()

    async def test_verify_catches_an_edited_row(
        self, client: AsyncClient, admin_auth_headers: dict, session: AsyncSession, account: Account
    ):
        await seal(session)
        await self._tamper(session, "UPDATE audit_events SET actor_kind = 'user' WHERE seq = 1")

        result = (await client.get("/api/audit/verify", headers=admin_auth_headers)).json()
        assert result["ok"] is False
        assert result["broken_at_seq"] == 1
        assert result["reason"] == "content changed"

    async def test_verify_catches_a_removed_row(
        self, client: AsyncClient, admin_auth_headers: dict, session: AsyncSession, account: Account
    ):
        account.name = "Segundo"
        await session.commit()
        account.name = "Terceiro"
        await session.commit()
        await seal(session)
        await self._tamper(session, "DELETE FROM audit_events WHERE seq = 2")

        result = (await client.get("/api/audit/verify", headers=admin_auth_headers)).json()
        assert result["ok"] is False
        assert result["broken_at_seq"] == 3


@pytest.mark.asyncio
class TestReading:
    async def test_the_owner_reads_the_workspace_trail_and_only_that(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict,
        test_user: User, test_workspace: Workspace, account: Account,
    ):
        other = Workspace(id=uuid.uuid4(), name="Outro", kind="business", created_by_user_id=test_user.id)
        session.add(other)
        await session.flush()
        session.add(Category(id=uuid.uuid4(), user_id=test_user.id, workspace_id=other.id,
                             name="De outro", icon="tag", color="#000000"))
        await session.commit()

        page = (await client.get("/api/audit", headers=auth_headers)).json()
        assert page["total"] >= 1
        assert {item["workspace_id"] for item in page["items"]} == {str(test_workspace.id)}
        assert any(item["entity_id"] == str(account.id) for item in page["items"])

    async def test_filters(self, client: AsyncClient, auth_headers: dict, account: Account):
        page = (
            await client.get("/api/audit", params={"entity_type": "accounts", "action": "create"}, headers=auth_headers)
        ).json()
        assert page["total"] >= 1
        assert {(i["entity_type"], i["action"]) for i in page["items"]} == {("accounts", "create")}

        none = (await client.get("/api/audit", params={"entity_type": "budgets"}, headers=auth_headers)).json()
        assert none["total"] == 0

    async def test_the_actor_is_shown_by_e_mail(
        self, client: AsyncClient, auth_headers: dict, test_user: User
    ):
        await client.post("/api/categories", json={"name": "Quem", "icon": "tag", "color": "#112233"}, headers=auth_headers)
        page = (await client.get("/api/audit", params={"entity_type": "categories"}, headers=auth_headers)).json()
        assert page["items"][0]["actor_email"] == test_user.email

    async def test_a_viewer_cannot_read_it(self, client: AsyncClient, viewer_auth_headers: dict):
        assert (await client.get("/api/audit", headers=viewer_auth_headers)).status_code == 403
        assert (await client.get("/api/audit/export", headers=viewer_auth_headers)).status_code == 403

    async def test_the_instance_trail_is_for_the_administrator(
        self, client: AsyncClient, auth_headers: dict
    ):
        assert (await client.get("/api/audit/instance", headers=auth_headers)).status_code == 403
        assert (await client.get("/api/audit/verify", headers=auth_headers)).status_code == 403

    async def test_export_is_a_csv_with_hashes(
        self, client: AsyncClient, auth_headers: dict, account: Account
    ):
        response = await client.get("/api/audit/export", headers=auth_headers)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        lines = response.text.lstrip("﻿").splitlines()
        assert lines[0].startswith("seq;quando_utc;usuario")
        assert str(account.id) in response.text
        assert all(len(line.split(";")[-1]) == 64 for line in lines[1:]), "every exported row is sealed"

    async def test_facets_list_what_can_be_filtered_on(
        self, client: AsyncClient, auth_headers: dict, account: Account
    ):
        facets = (await client.get("/api/audit/facets", headers=auth_headers)).json()
        assert "accounts" in facets["entity_types"] and "create" in facets["actions"]


@pytest.mark.asyncio
class TestNamedEvents:
    async def test_record_event_writes_a_row_that_is_not_a_row_change(
        self, session: AsyncSession, test_workspace: Workspace
    ):
        await record_event(session, "export", "workspace", entity_id=test_workspace.id,
                           workspace_id=test_workspace.id, detail="backup")
        await session.commit()

        [event] = [e for e in await _events(session, action="export")]
        assert event.entity_type == "workspace" and event.detail == "backup"
