"""A fresh instance is Brazilian: Portuguese, reais, DD/MM/YYYY, America/Sao_Paulo."""

import pytest
from httpx import AsyncClient

from app.core.config import Settings
from app.core.defaults import default_preferences
from app.schemas.user import UserPreferences


class TestDefaultPreferences:
    def test_settings_default_to_brazil(self):
        settings = Settings(_env_file=None, debug=True)
        assert settings.default_language == "pt-BR"
        assert settings.default_currency == "BRL"
        assert settings.default_date_format == "DD/MM/YYYY"
        assert settings.default_timezone == "America/Sao_Paulo"

    def test_the_new_account_preferences(self):
        assert default_preferences() == {
            "language": "pt-BR",
            "date_format": "DD/MM/YYYY",
            "timezone": "America/Sao_Paulo",
            "currency_display": "BRL",
        }

    def test_the_preferences_schema_agrees_with_the_model_default(self):
        schema = UserPreferences().model_dump()
        for key, value in default_preferences().items():
            assert schema[key] == value

    def test_another_market_is_a_matter_of_environment(self, monkeypatch):
        from app.core import config

        monkeypatch.setenv("DEFAULT_LANGUAGE", "en")
        monkeypatch.setenv("DEFAULT_CURRENCY", "USD")
        monkeypatch.setenv("DEFAULT_DATE_FORMAT", "MM/DD/YYYY")
        monkeypatch.setenv("DEFAULT_TIMEZONE", "UTC")
        config.get_settings.cache_clear()
        try:
            assert default_preferences() == {
                "language": "en",
                "date_format": "MM/DD/YYYY",
                "timezone": "UTC",
                "currency_display": "USD",
            }
        finally:
            monkeypatch.undo()
            config.get_settings.cache_clear()


async def _sign_in(client: AsyncClient, email: str, password: str) -> dict[str, str]:
    response = await client.post("/api/auth/login", data={"username": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.asyncio
class TestNewAccountIsBrazilian:
    async def test_registering_without_choices_gives_portuguese_and_reais(
        self, client: AsyncClient, clean_db
    ):
        created = await client.post(
            "/api/auth/register", json={"email": "ana@example.com", "password": "senha-forte-123"}
        )
        assert created.status_code == 201
        assert created.json()["preferences"]["language"] == "pt-BR"
        assert created.json()["preferences"]["currency_display"] == "BRL"
        assert created.json()["preferences"]["date_format"] == "DD/MM/YYYY"
        assert created.json()["preferences"]["timezone"] == "America/Sao_Paulo"

    async def test_the_starting_wallet_and_categories_are_in_portuguese(
        self, client: AsyncClient, clean_db
    ):
        await client.post(
            "/api/auth/register", json={"email": "ana@example.com", "password": "senha-forte-123"}
        )
        headers = await _sign_in(client, "ana@example.com", "senha-forte-123")

        accounts = (await client.get("/api/accounts", headers=headers)).json()
        assert [a["name"] for a in accounts] == ["Carteira"]

        categories = {
            c["name"] for c in (await client.get("/api/categories", headers=headers)).json()
        }
        assert {"Mercado", "Transporte", "Saúde"} <= categories
        assert "Groceries" not in categories

    async def test_a_person_who_chooses_english_gets_english(self, client: AsyncClient, clean_db):
        prefs = {
            "language": "en",
            "currency_display": "USD",
            "date_format": "MM/DD/YYYY",
            "timezone": "UTC",
        }
        await client.post(
            "/api/auth/register",
            json={"email": "bob@example.com", "password": "strong-pass-123", "preferences": prefs},
        )
        headers = await _sign_in(client, "bob@example.com", "strong-pass-123")

        accounts = (await client.get("/api/accounts", headers=headers)).json()
        assert [a["name"] for a in accounts] == ["Wallet"]
        categories = {
            c["name"] for c in (await client.get("/api/categories", headers=headers)).json()
        }
        assert "Groceries" in categories and "Mercado" not in categories

    async def test_what_the_form_did_not_send_is_filled_in(self, client: AsyncClient, clean_db):
        """The web form sends the language and the currency, not the date format or the time zone."""
        created = await client.post(
            "/api/auth/register",
            json={
                "email": "form@example.com",
                "password": "senha-forte-123",
                "preferences": {"language": "es", "currency_display": "EUR"},
            },
        )
        preferences = created.json()["preferences"]
        assert preferences["language"] == "es" and preferences["currency_display"] == "EUR"
        assert preferences["date_format"] == "DD/MM/YYYY"
        assert preferences["timezone"] == "America/Sao_Paulo"

    async def test_first_run_setup_defaults_to_brazil_too(self, client: AsyncClient, clean_db):
        response = await client.post(
            "/api/setup/create-admin",
            json={"email": "admin@example.com", "password": "senha-forte-123"},
        )
        assert response.status_code == 200, response.text
        headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        me = (await client.get("/api/users/me", headers=headers)).json()
        assert me["preferences"]["language"] == "pt-BR"
        assert me["preferences"]["currency_display"] == "BRL"
        assert me["preferences"]["date_format"] == "DD/MM/YYYY"
        assert me["preferences"]["timezone"] == "America/Sao_Paulo"
