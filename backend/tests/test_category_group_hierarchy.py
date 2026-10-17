import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_create_root_group_with_natureza(client: AsyncClient, auth_headers):
    resp = await client.post("/api/category-groups", json={
        "name": "Receitas", "code": "4", "natureza": "receita",
    }, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["depth"] == 0
    assert data["natureza"] == "receita"
    assert data["code"] == "4"
    assert data["parent_id"] is None


async def test_create_subgroup(client: AsyncClient, auth_headers):
    root = (await client.post("/api/category-groups", json={
        "name": "Receitas", "natureza": "receita",
    }, headers=auth_headers)).json()
    resp = await client.post("/api/category-groups", json={
        "name": "Operacional", "parent_id": root["id"],
    }, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["depth"] == 1
    assert data["parent_id"] == root["id"]


async def test_reject_depth_greater_than_1(client: AsyncClient, auth_headers):
    root = (await client.post("/api/category-groups", json={
        "name": "Raiz", "natureza": "despesa",
    }, headers=auth_headers)).json()
    sub = (await client.post("/api/category-groups", json={
        "name": "Sub", "parent_id": root["id"],
    }, headers=auth_headers)).json()
    resp = await client.post("/api/category-groups", json={
        "name": "Neto", "parent_id": sub["id"],
    }, headers=auth_headers)
    assert resp.status_code == 400


async def test_reject_self_referential_cycle(client: AsyncClient, auth_headers):
    grp = (await client.post("/api/category-groups", json={
        "name": "G",
    }, headers=auth_headers)).json()
    resp = await client.patch(
        f"/api/category-groups/{grp['id']}",
        json={"parent_id": grp["id"]},
        headers=auth_headers,
    )
    assert resp.status_code == 400


async def test_natureza_inherited_from_parent(client: AsyncClient, auth_headers):
    root = (await client.post("/api/category-groups", json={
        "name": "Despesas", "natureza": "despesa",
    }, headers=auth_headers)).json()
    sub = (await client.post("/api/category-groups", json={
        "name": "Operacional", "parent_id": root["id"],
    }, headers=auth_headers)).json()
    # sub without own natureza should inherit from root
    assert sub.get("effective_natureza") == "despesa"


async def test_list_groups_returns_tree_structure(client: AsyncClient, auth_headers):
    root = (await client.post("/api/category-groups", json={
        "name": "R", "natureza": "receita",
    }, headers=auth_headers)).json()
    await client.post("/api/category-groups", json={
        "name": "Sub", "parent_id": root["id"],
    }, headers=auth_headers)
    resp = await client.get("/api/category-groups", headers=auth_headers)
    assert resp.status_code == 200
    groups = resp.json()
    root_in_resp = next((g for g in groups if g["id"] == root["id"]), None)
    assert root_in_resp is not None
    assert any(c["name"] == "Sub" for c in root_in_resp.get("children", []))


async def test_reject_moving_root_group_with_children(client: AsyncClient, auth_headers):
    """Moving a root group that has children would create depth-2 grandchildren — must be rejected."""
    root = (await client.post("/api/category-groups", json={"name": "Root"}, headers=auth_headers)).json()
    await client.post("/api/category-groups", json={"name": "Child", "parent_id": root["id"]}, headers=auth_headers)
    other_root = (await client.post("/api/category-groups", json={"name": "Other"}, headers=auth_headers)).json()

    resp = await client.patch(
        f"/api/category-groups/{root['id']}",
        json={"parent_id": other_root["id"]},
        headers=auth_headers,
    )
    assert resp.status_code == 400


async def test_delete_root_group_promotes_children(client: AsyncClient, auth_headers):
    """Deleting a root group must promote its subgroups to root (depth=0, parent_id=null)."""
    root = (await client.post("/api/category-groups", json={"name": "Parent"}, headers=auth_headers)).json()
    child = (await client.post("/api/category-groups", json={"name": "Child", "parent_id": root["id"]}, headers=auth_headers)).json()

    del_resp = await client.delete(f"/api/category-groups/{root['id']}", headers=auth_headers)
    assert del_resp.status_code == 204

    # The child group must now appear as a root group
    groups = (await client.get("/api/category-groups", headers=auth_headers)).json()
    promoted = next((g for g in groups if g["id"] == child["id"]), None)
    assert promoted is not None, "Promoted child group is missing from listing"
    assert promoted["depth"] == 0
    assert promoted["parent_id"] is None
