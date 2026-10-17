"""Roles and permissions: the built-in roles keep their behaviour, and a workspace can make its own."""
import uuid

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import permissions as catalog
from app.models.audit import AuditEvent
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.models.workspace_role import WorkspaceRole
from app.services import role_service
from tests.conftest import issue_test_token

pytestmark = pytest.mark.asyncio


async def _member(
    session: AsyncSession, workspace: Workspace, role: str, email: str | None = None
) -> tuple[User, dict]:
    """A user who is a member of `workspace` with `role`, and headers for them."""
    user = User(
        id=uuid.uuid4(),
        email=email or f"{role.replace('_', '-')}-{uuid.uuid4().hex[:6]}@example.com",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    session.add(user)
    await session.flush()
    session.add(WorkspaceMember(id=uuid.uuid4(), workspace_id=workspace.id, user_id=user.id, role=role))
    await session.commit()
    token = await issue_test_token(user)
    return user, {"Authorization": f"Bearer {token}", "X-Workspace-Id": str(workspace.id)}


async def _role(client: AsyncClient, owner: dict, name: str, permissions: list[str], **extra) -> dict:
    response = await client.post("/api/roles", json={"name": name, "permissions": permissions, **extra}, headers=owner)
    assert response.status_code == 201, response.text
    return response.json()


TRANSACTION = {"description": "Papelaria", "amount": "10.00", "date": "2026-09-10", "type": "debit"}


async def _new_transaction(client: AsyncClient, headers: dict, session: AsyncSession, workspace: Workspace, owner: User):
    from app.models.account import Account

    account = Account(
        id=uuid.uuid4(), user_id=owner.id, workspace_id=workspace.id, name="Caixa", type="checking", currency="BRL"
    )
    session.add(account)
    await session.commit()
    return await client.post("/api/transactions", json={**TRANSACTION, "account_id": str(account.id)}, headers=headers)


class TestTheCatalog:
    async def test_the_built_in_roles_grant_what_they_always_did(self):
        assert catalog.SYSTEM_ROLES["owner"] == catalog.ALL_PERMISSIONS
        assert catalog.SYSTEM_ROLES["manager"] == catalog.ALL_PERMISSIONS
        # An editor writes any data and takes the data out; it administers nothing and reads no audit trail.
        assert catalog.SYSTEM_ROLES["editor"] == catalog.WRITE_PERMISSIONS | {"export.read"}
        assert not catalog.SYSTEM_ROLES["editor"] & catalog.ADMIN_PERMISSIONS
        assert "audit.read" not in catalog.SYSTEM_ROLES["editor"]
        # A viewer changes nothing.
        assert catalog.SYSTEM_ROLES["viewer"] == {"export.read"}
        assert not catalog.SYSTEM_ROLES["viewer"] & catalog.WRITE_PERMISSIONS

    async def test_every_role_and_template_uses_only_catalog_permissions(self):
        for permissions in catalog.SYSTEM_ROLES.values():
            assert permissions <= catalog.ALL_PERMISSIONS
        for template in catalog.TEMPLATES:
            assert template.permissions <= catalog.ALL_PERMISSIONS, template.key

    async def test_the_catalog_is_served(self, client: AsyncClient, auth_headers: dict):
        body = (await client.get("/api/roles/catalog", headers=auth_headers)).json()
        assert {p["key"] for p in body["permissions"]} == catalog.ALL_PERMISSIONS
        assert {t["key"] for t in body["templates"]} == {t.key for t in catalog.TEMPLATES}


class TestTheBuiltInRolesBehaveAsBefore:
    async def test_a_viewer_reads_and_takes_data_out_but_changes_nothing(
        self, client: AsyncClient, viewer_auth_headers: dict
    ):
        assert (await client.get("/api/accounts", headers=viewer_auth_headers)).status_code == 200
        assert (await client.post("/api/export/backup", json={}, headers=viewer_auth_headers)).status_code == 200
        assert (await client.post("/api/categories", json={"name": "x"}, headers=viewer_auth_headers)).status_code == 403
        assert (await client.get("/api/audit", headers=viewer_auth_headers)).status_code == 403
        assert (await client.post("/api/roles", json={"name": "x"}, headers=viewer_auth_headers)).status_code == 403

    async def test_an_editor_writes_but_does_not_administer(
        self, client: AsyncClient, session: AsyncSession, test_workspace: Workspace, test_user: User
    ):
        _, headers = await _member(session, test_workspace, "editor")
        assert (await _new_transaction(client, headers, session, test_workspace, test_user)).status_code == 201
        assert (await client.post("/api/categories", json={"name": "Nova", "icon": "tag", "color": "#112233"}, headers=headers)).status_code in (200, 201)
        # What only an owner could do:
        assert (await client.get("/api/audit", headers=headers)).status_code == 403
        assert (await client.post("/api/roles", json={"name": "x"}, headers=headers)).status_code == 403
        invite = await client.post(
            f"/api/workspaces/{test_workspace.id}/members", json={"email": "novo@example.com", "role": "viewer"}, headers=headers
        )
        assert invite.status_code == 403
        rename = await client.patch(f"/api/workspaces/{test_workspace.id}", json={"name": "Outro"}, headers=headers)
        assert rename.status_code == 403

    async def test_an_owner_can_do_all_of_it(
        self, client: AsyncClient, auth_headers: dict, test_workspace: Workspace
    ):
        assert (await client.get("/api/audit", headers=auth_headers)).status_code == 200
        assert (await client.post("/api/roles", json={"name": "Contador", "permissions": ["export.read"]}, headers=auth_headers)).status_code == 201
        rename = await client.patch(f"/api/workspaces/{test_workspace.id}", json={"name": "Renomeado"}, headers=auth_headers)
        assert rename.status_code == 200

    async def test_the_workspace_says_what_the_role_allows(
        self, client: AsyncClient, auth_headers: dict, viewer_auth_headers: dict
    ):
        owner = (await client.get("/api/workspaces/current", headers=auth_headers)).json()
        viewer = (await client.get("/api/workspaces/current", headers=viewer_auth_headers)).json()
        assert set(owner["permissions"]) == catalog.ALL_PERMISSIONS
        assert viewer["permissions"] == ["export.read"]


class TestCreatingRoles:
    async def test_an_owner_makes_a_role_from_permissions(self, client: AsyncClient, auth_headers: dict):
        role = await _role(client, auth_headers, "Tesoureiro", ["transactions.write", "accounts.write"], description="Lança e concilia")
        assert role["system"] is False and role["key"].startswith("c_")
        assert role["permissions"] == ["accounts.write", "transactions.write"]
        assert role["member_count"] == 0

    async def test_a_role_can_start_from_a_template(self, client: AsyncClient, auth_headers: dict):
        role = await _role(client, auth_headers, "Contador externo", [], template="accountant")
        assert role["permissions"] == ["export.read"]
        role = await _role(client, auth_headers, "Auditoria", ["accounts.write"], template="auditor")
        assert role["permissions"] == ["accounts.write", "audit.read", "export.read"], "the template and what was added"

    async def test_the_list_has_the_built_in_roles_then_the_workspaces_own(self, client: AsyncClient, auth_headers: dict):
        await _role(client, auth_headers, "Contador", ["export.read"])
        roles = (await client.get("/api/roles", headers=auth_headers)).json()
        assert [r["key"] for r in roles[:3]] == ["owner", "editor", "viewer"]
        assert all(r["system"] for r in roles[:3]) and roles[3]["name"] == "Contador"

    async def test_bad_input_is_refused(self, client: AsyncClient, auth_headers: dict):
        bad = await client.post("/api/roles", json={"name": "X", "permissions": ["transactions.write", "fly.moon"]}, headers=auth_headers)
        assert bad.status_code == 400 and "fly.moon" in bad.json()["detail"]
        assert (await client.post("/api/roles", json={"name": "X", "template": "nope"}, headers=auth_headers)).status_code == 400
        assert (await client.post("/api/roles", json={"name": "  "}, headers=auth_headers)).status_code in (400, 422)

    async def test_names_are_unique_and_do_not_shadow_the_built_in_roles(self, client: AsyncClient, auth_headers: dict):
        await _role(client, auth_headers, "Contador", [])
        assert (await client.post("/api/roles", json={"name": "contador"}, headers=auth_headers)).status_code == 409
        for taken in ("Owner", "editor", "VIEWER", "manager"):
            assert (await client.post("/api/roles", json={"name": taken}, headers=auth_headers)).status_code == 409, taken

    async def test_only_someone_with_the_permission_can_make_roles(
        self, client: AsyncClient, session: AsyncSession, test_workspace: Workspace, auth_headers: dict
    ):
        granted = await _role(client, auth_headers, "Gestor de papéis", ["roles.manage"])
        _, helper = await _member(session, test_workspace, granted["key"])
        _, plain = await _member(session, test_workspace, "editor")

        assert (await client.post("/api/roles", json={"name": "Novo"}, headers=helper)).status_code == 201
        assert (await client.post("/api/roles", json={"name": "Outro"}, headers=plain)).status_code == 403

    async def test_roles_are_audited(self, client: AsyncClient, session: AsyncSession, auth_headers: dict):
        role = await _role(client, auth_headers, "Contador", ["export.read"])
        events = (
            await session.execute(select(AuditEvent).where(AuditEvent.entity_type == "workspace_roles", AuditEvent.entity_id == role["id"]))
        ).scalars().all()
        assert [e.action for e in events] == ["create"]


class TestChangingAndDeletingRoles:
    async def test_a_role_changes_for_everyone_who_holds_it_at_once(
        self, client: AsyncClient, session: AsyncSession, test_workspace: Workspace, test_user: User, auth_headers: dict
    ):
        role = await _role(client, auth_headers, "Lançador", ["accounts.write"])
        _, headers = await _member(session, test_workspace, role["key"])
        assert (await _new_transaction(client, headers, session, test_workspace, test_user)).status_code == 403

        changed = await client.patch(
            f"/api/roles/{role['id']}", json={"permissions": ["accounts.write", "transactions.write"]}, headers=auth_headers
        )
        assert changed.status_code == 200 and changed.json()["member_count"] == 1
        assert (await _new_transaction(client, headers, session, test_workspace, test_user)).status_code == 201

    async def test_rename_checks_the_name_again(self, client: AsyncClient, auth_headers: dict):
        one = await _role(client, auth_headers, "Um", [])
        await _role(client, auth_headers, "Dois", [])
        assert (await client.patch(f"/api/roles/{one['id']}", json={"name": "dois"}, headers=auth_headers)).status_code == 409
        assert (await client.patch(f"/api/roles/{one['id']}", json={"name": "Um novo"}, headers=auth_headers)).json()["name"] == "Um novo"

    async def test_a_role_in_use_cannot_be_deleted(
        self, client: AsyncClient, session: AsyncSession, test_workspace: Workspace, auth_headers: dict
    ):
        role = await _role(client, auth_headers, "Contador", ["export.read"])
        user, _ = await _member(session, test_workspace, role["key"])

        assert (await client.delete(f"/api/roles/{role['id']}", headers=auth_headers)).status_code == 409

        moved = await client.patch(
            f"/api/workspaces/{test_workspace.id}/members/{user.id}", json={"role": "viewer"}, headers=auth_headers
        )
        assert moved.status_code == 200
        assert (await client.delete(f"/api/roles/{role['id']}", headers=auth_headers)).status_code == 204
        assert (await client.get("/api/roles", headers=auth_headers)).json()[3:] == []

    async def test_a_role_of_another_workspace_is_not_reachable(
        self, client: AsyncClient, session: AsyncSession, test_user: User, auth_headers: dict
    ):
        other = Workspace(id=uuid.uuid4(), name="Outro", kind="business", created_by_user_id=test_user.id)
        session.add(other)
        await session.flush()
        session.add(WorkspaceMember(id=uuid.uuid4(), workspace_id=other.id, user_id=test_user.id, role="owner"))
        foreign = WorkspaceRole(workspace_id=other.id, key="c_deadbeef", name="Alheio", permissions=["export.read"])
        session.add(foreign)
        await session.commit()

        assert (await client.patch(f"/api/roles/{foreign.id}", json={"name": "x"}, headers=auth_headers)).status_code == 404
        assert (await client.delete(f"/api/roles/{foreign.id}", headers=auth_headers)).status_code == 404


class TestWhatACustomRoleAllows:
    async def test_an_accountant_reads_and_exports_and_nothing_more(
        self, client: AsyncClient, session: AsyncSession, test_workspace: Workspace, test_user: User, auth_headers: dict
    ):
        role = await _role(client, auth_headers, "Contador", [], template="accountant")
        _, headers = await _member(session, test_workspace, role["key"])

        assert (await client.get("/api/accounts", headers=headers)).status_code == 200
        assert (await client.post("/api/export/backup", json={}, headers=headers)).status_code == 200
        assert (await _new_transaction(client, headers, session, test_workspace, test_user)).status_code == 403
        assert (await client.get("/api/audit", headers=headers)).status_code == 403

    async def test_a_role_without_export_cannot_take_the_data_out(
        self, client: AsyncClient, session: AsyncSession, test_workspace: Workspace, auth_headers: dict
    ):
        """Unlike the built-in viewer, which always could."""
        role = await _role(client, auth_headers, "Só leitura", [])
        _, headers = await _member(session, test_workspace, role["key"])

        assert (await client.get("/api/accounts", headers=headers)).status_code == 200
        assert (await client.post("/api/export/backup", json={}, headers=headers)).status_code == 403
        assert (await client.get("/api/transactions/export", headers=headers)).status_code == 403

    async def test_a_clerk_enters_data_but_configures_nothing(
        self, client: AsyncClient, session: AsyncSession, test_workspace: Workspace, test_user: User, auth_headers: dict
    ):
        role = await _role(client, auth_headers, "Lançador", [], template="clerk")
        _, headers = await _member(session, test_workspace, role["key"])

        assert (await _new_transaction(client, headers, session, test_workspace, test_user)).status_code == 201
        assert (await client.post("/api/categories", json={"name": "Nova", "icon": "tag", "color": "#112233"}, headers=headers)).status_code == 403
        assert (await client.post("/api/roles", json={"name": "x"}, headers=headers)).status_code == 403
        assert (await client.patch(f"/api/workspaces/{test_workspace.id}", json={"name": "x"}, headers=headers)).status_code == 403

    async def test_the_audit_trail_is_a_permission_of_its_own(
        self, client: AsyncClient, session: AsyncSession, test_workspace: Workspace, auth_headers: dict
    ):
        role = await _role(client, auth_headers, "Auditor", [], template="auditor")
        _, headers = await _member(session, test_workspace, role["key"])
        assert (await client.get("/api/audit", headers=headers)).status_code == 200
        assert (await client.get("/api/audit/export", headers=headers)).status_code == 200

    async def test_managing_members_is_separate_from_managing_the_workspace(
        self, client: AsyncClient, session: AsyncSession, test_workspace: Workspace, auth_headers: dict
    ):
        role = await _role(client, auth_headers, "RH", ["members.manage"])
        _, headers = await _member(session, test_workspace, role["key"])
        target, _ = await _member(session, test_workspace, "viewer")

        moved = await client.patch(
            f"/api/workspaces/{test_workspace.id}/members/{target.id}", json={"role": "editor"}, headers=headers
        )
        assert moved.status_code == 200
        rename = await client.patch(f"/api/workspaces/{test_workspace.id}", json={"name": "x"}, headers=headers)
        assert rename.status_code == 403
        removed = await client.delete(f"/api/workspaces/{test_workspace.id}/members/{target.id}", headers=headers)
        assert removed.status_code == 204

    async def test_someone_without_the_permission_cannot_remove_others_but_can_leave(
        self, client: AsyncClient, session: AsyncSession, test_workspace: Workspace
    ):
        me, mine = await _member(session, test_workspace, "editor")
        other, _ = await _member(session, test_workspace, "viewer")
        assert (
            await client.delete(f"/api/workspaces/{test_workspace.id}/members/{other.id}", headers=mine)
        ).status_code == 403
        assert (
            await client.delete(f"/api/workspaces/{test_workspace.id}/members/{me.id}", headers=mine)
        ).status_code == 204

    async def test_a_removed_role_leaves_a_member_with_no_permissions_not_an_error(
        self, client: AsyncClient, session: AsyncSession, test_workspace: Workspace
    ):
        """A member left holding a key that no longer resolves can still sign in and read; nothing more."""
        _, headers = await _member(session, test_workspace, "c_00000000")
        assert (await client.get("/api/accounts", headers=headers)).status_code == 200
        assert (await client.post("/api/categories", json={"name": "x"}, headers=headers)).status_code == 403
        assert (await client.post("/api/export/backup", json={}, headers=headers)).status_code == 403


class TestAssigningRoles:
    async def test_a_member_is_invited_with_one_of_the_workspaces_roles(
        self, client: AsyncClient, session: AsyncSession, test_workspace: Workspace, auth_headers: dict
    ):
        role = await _role(client, auth_headers, "Contador", ["export.read"])
        session.add(
            User(id=uuid.uuid4(), email="contador@escritorio.com", hashed_password="x", is_active=True, is_verified=True)
        )
        await session.commit()
        invited = await client.post(
            f"/api/workspaces/{test_workspace.id}/members",
            json={"email": "contador@escritorio.com", "role": role["key"]},
            headers=auth_headers,
        )
        assert invited.status_code in (200, 201), invited.text
        assert invited.json()["role"] == role["key"]

    async def test_an_unknown_role_or_another_workspaces_is_refused(
        self, client: AsyncClient, session: AsyncSession, test_workspace: Workspace, test_user: User, auth_headers: dict
    ):
        other = Workspace(id=uuid.uuid4(), name="Outro", kind="business", created_by_user_id=test_user.id)
        session.add(other)
        await session.flush()
        session.add(WorkspaceRole(workspace_id=other.id, key="c_feedface", name="Alheio", permissions=[]))
        await session.commit()
        target, _ = await _member(session, test_workspace, "viewer")

        for key in ("c_nonexistent", "c_feedface", "superuser"):
            response = await client.patch(
                f"/api/workspaces/{test_workspace.id}/members/{target.id}", json={"role": key}, headers=auth_headers
            )
            assert response.status_code == 400, key

    async def test_the_sole_owner_still_cannot_be_demoted_to_a_custom_role(
        self, client: AsyncClient, test_workspace: Workspace, test_user: User, auth_headers: dict
    ):
        role = await _role(client, auth_headers, "Contador", [])
        response = await client.patch(
            f"/api/workspaces/{test_workspace.id}/members/{test_user.id}", json={"role": role["key"]}, headers=auth_headers
        )
        assert response.status_code == 400


class TestRoleService:
    async def test_a_permission_dropped_from_the_catalog_is_ignored_not_fatal(
        self, session: AsyncSession, test_workspace: Workspace
    ):
        role = WorkspaceRole(
            workspace_id=test_workspace.id, key="c_0badf00d", name="Antigo", permissions=["export.read", "retired.permission"]
        )
        session.add(role)
        await session.commit()

        assert await role_service.permissions_of(session, test_workspace.id, "c_0badf00d") == {"export.read"}

    async def test_an_unknown_key_allows_nothing(self, session: AsyncSession, test_workspace: Workspace):
        assert await role_service.permissions_of(session, test_workspace.id, "c_ffffffff") == frozenset()
        assert await role_service.permissions_of(session, test_workspace.id, "made-up") == frozenset()

    async def test_the_number_of_custom_roles_is_bounded(self, session: AsyncSession, test_workspace: Workspace, test_user: User):
        for i in range(role_service.MAX_CUSTOM_ROLES):
            await role_service.create_role(
                session, test_workspace.id, name=f"Papel {i}", description=None, permissions=[], created_by=test_user.id
            )
        with pytest.raises(HTTPException) as caught:
            await role_service.create_role(
                session, test_workspace.id, name="Um a mais", description=None, permissions=[], created_by=test_user.id
            )
        assert "at most" in str(caught.value.detail)
