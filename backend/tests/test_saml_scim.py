"""SAML 2.0 + SCIM 2.0 (C6) — endpoint tests.

These test the router-level behaviour — config visibility, auth gates, SCIM
CRUD — without requiring the ``xmlsec1`` system library that python3-saml
needs for real SAML processing.
"""
import uuid

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# SAML config
# ---------------------------------------------------------------------------

async def test_saml_config_endpoint(client: AsyncClient):
    """The SAML config endpoint returns the enabled status."""
    resp = await client.get("/api/auth/saml/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "enabled" in data
    assert "provider_name" in data
    assert "local_auth_enabled" in data


async def test_saml_metadata_returns_404_when_disabled(client: AsyncClient):
    """SP metadata is not served when SAML is disabled."""
    resp = await client.get("/api/auth/saml/metadata")
    # Either 404 (disabled) or 503 (library missing) is acceptable
    assert resp.status_code in (404, 503)


async def test_saml_login_returns_404_when_disabled(client: AsyncClient):
    """Login redirect is not available when SAML is disabled."""
    resp = await client.get("/api/auth/saml/login")
    assert resp.status_code in (404, 503)


# ---------------------------------------------------------------------------
# SCIM auth
# ---------------------------------------------------------------------------

async def test_scim_list_users_unauthorized(client: AsyncClient):
    """No token or wrong token -> 401 or 404."""
    resp = await client.get("/api/scim/v2/Users")
    # 422 (missing header), 404 (disabled), or 401 are all acceptable
    assert resp.status_code in (401, 404, 422)


async def test_scim_list_users_wrong_token(client: AsyncClient):
    """Wrong bearer token -> 401 or 404."""
    resp = await client.get(
        "/api/scim/v2/Users",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert resp.status_code in (401, 404)


# ---------------------------------------------------------------------------
# SCIM CRUD (with SCIM enabled via env override)
# ---------------------------------------------------------------------------

@pytest.fixture
def _enable_scim(monkeypatch):
    """Enable SCIM with a known bearer token for testing."""
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("SCIM_ENABLED", "true")
    monkeypatch.setenv("SCIM_BEARER_TOKEN", "test-scim-token-1234")
    yield
    get_settings.cache_clear()


@pytest.fixture
def scim_headers():
    return {"Authorization": "Bearer test-scim-token-1234"}


async def test_scim_create_user(
    client: AsyncClient, _enable_scim, scim_headers
):
    """POST /Users with valid data creates a user."""
    email = f"scim-test-{uuid.uuid4().hex[:8]}@example.com"
    resp = await client.post(
        "/api/scim/v2/Users",
        headers=scim_headers,
        json={
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": email,
            "name": {"givenName": "Test", "familyName": "User"},
            "active": True,
            "externalId": f"ext-{uuid.uuid4().hex[:8]}",
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["userName"] == email
    assert data["active"] is True
    assert data["id"]  # UUID assigned


async def test_scim_deactivate_user(
    client: AsyncClient, _enable_scim, scim_headers
):
    """PATCH with active=false deactivates the user."""
    # Create first
    email = f"scim-deact-{uuid.uuid4().hex[:8]}@example.com"
    create_resp = await client.post(
        "/api/scim/v2/Users",
        headers=scim_headers,
        json={
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": email,
            "name": {"givenName": "Deact", "familyName": "Test"},
            "active": True,
            "externalId": f"ext-deact-{uuid.uuid4().hex[:8]}",
        },
    )
    assert create_resp.status_code == 201
    user_id = create_resp.json()["id"]

    # Deactivate
    patch_resp = await client.patch(
        f"/api/scim/v2/Users/{user_id}",
        headers=scim_headers,
        json={
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [{"op": "replace", "path": "active", "value": False}],
        },
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["active"] is False


async def test_scim_idempotent_by_external_id(
    client: AsyncClient, _enable_scim, scim_headers
):
    """POST with the same externalId returns the existing user."""
    ext_id = f"ext-idem-{uuid.uuid4().hex[:8]}"
    email = f"scim-idem-{uuid.uuid4().hex[:8]}@example.com"
    payload = {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
        "userName": email,
        "name": {"givenName": "Idem", "familyName": "Test"},
        "active": True,
        "externalId": ext_id,
    }

    resp1 = await client.post("/api/scim/v2/Users", headers=scim_headers, json=payload)
    assert resp1.status_code == 201
    id1 = resp1.json()["id"]

    # Second create with same externalId
    resp2 = await client.post("/api/scim/v2/Users", headers=scim_headers, json=payload)
    # Should return 200 or 201 with the same user
    assert resp2.status_code in (200, 201)
    assert resp2.json()["id"] == id1
