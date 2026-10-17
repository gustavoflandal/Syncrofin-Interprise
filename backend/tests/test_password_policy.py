"""The password rule (app/core/password_policy.py) and where it is enforced."""
import pytest
from httpx import AsyncClient

from app.core import password_policy as policy
from app.models.user import User


@pytest.mark.parametrize(
    "password, expected",
    [
        ("curta1", policy.TOO_SHORT),
        ("a" * 129, policy.TOO_LONG),
        ("password123", policy.TOO_COMMON),  # too short is not the only thing wrong
        ("Senha123!", policy.TOO_COMMON),  # the trailing digits and symbol do not disguise it
        ("qwertyuiop", policy.TOO_COMMON),
        ("aaaaaaaaaaaa", policy.TOO_SIMPLE),
        ("abababababab", policy.TOO_SIMPLE),
        ("abcdefghijkl", policy.TOO_SIMPLE),
        ("1234567890123", policy.TOO_SIMPLE),
    ],
)
def test_refuses_what_is_guessable(password, expected):
    assert expected in policy.problems(password)


def test_refuses_the_address_it_protects():
    assert policy.HAS_EMAIL in policy.problems("maria.souza-2026!", email="maria.souza@example.com")
    assert policy.HAS_EMAIL in policy.problems("mariasouza-2026!", email="maria.souza@example.com")
    # A short local part says nothing about the password.
    assert policy.HAS_EMAIL not in policy.problems("uma frase bem longa", email="ana@example.com")


@pytest.mark.parametrize("password", ["correct horse battery", "cavalo-grampo-bateria-9", "Tr0ca-o-Cafe-da-Manha"])
def test_accepts_a_long_phrase_without_symbols_or_capitals(password):
    assert policy.problems(password, email="ana@example.com") == []


def test_the_minimum_length_is_configurable_but_never_below_eight(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "password_min_length", 14)
    assert policy.TOO_SHORT in policy.problems("doze-carac-12")
    monkeypatch.setattr(get_settings(), "password_min_length", 2)
    assert policy.minimum_length() == 8


@pytest.mark.asyncio
async def test_register_refuses_a_weak_password_with_the_reason(client: AsyncClient, clean_db):
    response = await client.post("/api/auth/register", json={"email": "novo@example.com", "password": "senha123"})
    assert response.status_code == 400
    assert response.json()["detail"]["reason"] == policy.TOO_SHORT


@pytest.mark.asyncio
async def test_info_tells_the_forms_the_minimum(client: AsyncClient):
    response = await client.get("/api/info")
    assert response.json()["password_min_length"] == policy.minimum_length()


@pytest.mark.asyncio
async def test_changing_your_own_password_goes_through_the_rule(
    client: AsyncClient, test_user: User, auth_headers: dict
):
    weak = await client.patch("/api/users/me", json={"password": "1234567890"}, headers=auth_headers)
    assert weak.status_code == 400
    assert weak.json()["detail"]["reason"] in {policy.TOO_COMMON, policy.TOO_SIMPLE}

    ok = await client.patch("/api/users/me", json={"password": "uma-senha-bem-mais-longa"}, headers=auth_headers)
    assert ok.status_code == 200


@pytest.mark.asyncio
async def test_an_administrator_cannot_set_a_weak_password_either(
    client: AsyncClient, test_user: User, admin_auth_headers: dict
):
    created = await client.post(
        "/api/admin/users",
        json={"email": "novo@example.com", "password": "12345678"},
        headers=admin_auth_headers,
    )
    assert created.status_code == 400
    assert created.json()["detail"] == {"code": "INVALID_PASSWORD", "reason": policy.TOO_SHORT}

    changed = await client.patch(
        f"/api/admin/users/{test_user.id}", json={"password": "aaaaaaaaaaaa"}, headers=admin_auth_headers
    )
    assert changed.status_code == 400
    assert changed.json()["detail"]["reason"] == policy.TOO_SIMPLE

    fine = await client.patch(
        f"/api/admin/users/{test_user.id}", json={"password": "definida-pelo-admin-1"}, headers=admin_auth_headers
    )
    assert fine.status_code == 200


@pytest.mark.asyncio
async def test_setup_refuses_a_weak_first_password(client: AsyncClient, clean_db):
    response = await client.post("/api/setup/create-admin", json={"email": "root@example.com", "password": "password"})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_PASSWORD"
