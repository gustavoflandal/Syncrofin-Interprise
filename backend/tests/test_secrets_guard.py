"""Production refuses to start on the secrets that are printed in the repository."""

import pytest
from pydantic import SecretStr, ValidationError

from app.agents.config import AgentSettings
from app.core.config import Settings
from app.core.secrets_guard import (
    KNOWN_DEFAULT_SECRETS,
    database_password_problem,
    mcp_secret_problem,
    refusal_message,
    secret_key_problem,
)

STRONG_KEY = "a3f9c1d27b8e4406a5d1e9f0c2b73845d6e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7"
STRONG_DB = "postgresql+asyncpg://syncrofin:Zk3-long-random-value@db:5432/syncrofin"


def build(
    *, debug: bool = False, secret_key: str = STRONG_KEY, database_url: str = STRONG_DB
) -> Settings:
    """Settings from arguments only: the process environment must not leak into the case."""
    return Settings(
        _env_file=None, debug=debug, secret_key=SecretStr(secret_key), database_url=database_url
    )


class TestSecretKey:
    @pytest.mark.parametrize("value", sorted(KNOWN_DEFAULT_SECRETS))
    def test_every_published_default_is_refused(self, value):
        assert secret_key_problem(value) is not None

    def test_the_repository_defaults_are_all_on_the_list(self):
        # If someone adds a new placeholder to a compose file or the chart, it belongs here too.
        for placeholder in (
            "change-me-in-production",
            "dev-secret-change-in-production",
            "dev-mcp-secret-change-in-production",
        ):
            assert placeholder in KNOWN_DEFAULT_SECRETS

    def test_a_short_key_is_refused_even_if_it_is_not_a_known_default(self):
        assert "too short" in (secret_key_problem("x" * 31) or "")

    def test_a_long_random_key_passes(self):
        assert secret_key_problem(STRONG_KEY) is None
        assert secret_key_problem("x" * 32) is None

    def test_the_message_says_how_to_fix_it(self):
        assert "openssl rand -hex 32" in (secret_key_problem("change-me-in-production") or "")


class TestDatabasePassword:
    def test_the_stock_password_is_refused_on_a_network_host(self):
        problem = database_password_problem(
            "postgresql+asyncpg://postgres:postgres@db:5432/syncrofin"
        )
        assert problem is not None and "'db'" in problem and "POSTGRES_PASSWORD" in problem

    @pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "[::1]"])
    def test_it_is_fine_on_the_developers_own_machine(self, host):
        assert (
            database_password_problem(
                f"postgresql+asyncpg://postgres:postgres@{host}:5432/syncrofin"
            )
            is None
        )

    def test_a_real_password_passes_anywhere(self):
        assert database_password_problem(STRONG_DB) is None

    def test_a_url_without_a_password_is_not_this_checks_business(self):
        assert database_password_problem("postgresql+asyncpg://postgres@db:5432/syncrofin") is None

    def test_garbage_does_not_crash_startup_with_a_confusing_error(self):
        assert database_password_problem("not a url at all") is None


class TestMcpSecret:
    @pytest.mark.parametrize(
        "value", ["", "change-me-in-production", "dev-mcp-secret-change-in-production"]
    )
    def test_defaults_and_empty_are_refused(self, value):
        assert mcp_secret_problem(value) is not None

    def test_any_other_value_passes(self):
        assert mcp_secret_problem("a-real-random-secret-value") is None


class TestSettingsStartup:
    def test_production_with_the_default_key_does_not_start(self):
        with pytest.raises(ValidationError) as caught:
            build(secret_key="dev-secret-change-in-production")
        assert "Refusing to start with insecure defaults" in str(caught.value)
        assert "SECRET_KEY" in str(caught.value)

    def test_production_with_the_default_database_password_does_not_start(self):
        with pytest.raises(ValidationError) as caught:
            build(database_url="postgresql+asyncpg://postgres:postgres@db:5432/syncrofin")
        assert "POSTGRES_PASSWORD" in str(caught.value)

    def test_every_problem_is_reported_at_once(self):
        with pytest.raises(ValidationError) as caught:
            build(
                secret_key="change-me-in-production",
                database_url="postgresql+asyncpg://postgres:postgres@db:5432/syncrofin",
            )
        message = str(caught.value)
        assert "SECRET_KEY" in message and "DATABASE_URL" in message

    def test_debug_lets_a_developer_run_on_the_defaults(self):
        settings = build(
            debug=True,
            secret_key="change-me-in-production",
            database_url="postgresql+asyncpg://postgres:postgres@db:5432/syncrofin",
        )
        assert settings.debug is True

    def test_strong_secrets_start_fine(self):
        assert build().secret_key.get_secret_value() == STRONG_KEY

    def test_the_test_suite_and_local_databases_are_not_locked_out(self):
        # CI and developers use the stock postgres password on localhost.
        build(database_url="postgresql+asyncpg://postgres:postgres@localhost:5432/syncrofin")

    def test_the_error_names_the_escape_hatch(self):
        assert "DEBUG=true" in refusal_message(["x"])


class TestAgentSettingsStartup:
    def test_agents_off_needs_no_secret(self):
        assert AgentSettings(enabled=False).enabled is False

    def test_agents_on_with_the_default_secret_does_not_start(self):
        with pytest.raises(ValidationError) as caught:
            AgentSettings(enabled=True, mcp_jwt_secret="dev-mcp-secret-change-in-production")
        assert "AGENTS_MCP_JWT_SECRET" in str(caught.value)

    def test_agents_on_with_an_empty_secret_does_not_start(self):
        with pytest.raises(ValidationError):
            AgentSettings(enabled=True, mcp_jwt_secret="")

    def test_agents_on_with_a_real_secret_start_fine(self):
        assert (
            AgentSettings(enabled=True, mcp_jwt_secret="a-real-random-secret-value").enabled is True
        )
