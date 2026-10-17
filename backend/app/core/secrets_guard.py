"""Refuse to start in production with the secrets that ship in the repository.

Every default below is public: it is in the source, in the compose files and in the docs. A
deployment that keeps one signs its login tokens (or opens its database) with a value anyone can
read. That is what these checks catch, at startup, with a message that says how to fix it,
instead of leaving it to a checklist nobody reads.

`DEBUG=true` switches all of it off, which is what the development compose does. The production
compose and the Helm chart never set it.
"""

from urllib.parse import urlsplit

#: Values that appear in the source, the compose files, the chart or the docs.
KNOWN_DEFAULT_SECRETS = frozenset(
    {
        "",
        "change-me-in-production",
        "dev-secret-change-in-production",
        "dev-mcp-secret-change-in-production",
        "changeme",
        "secret",
    }
)

MIN_SECRET_KEY_LENGTH = 32

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

HOW_TO = "Generate one with: openssl rand -hex 32"


def secret_key_problem(value: str) -> str | None:
    if value in KNOWN_DEFAULT_SECRETS:
        return f"SECRET_KEY is the default that ships with SyncroFin, which is public. {HOW_TO}"
    if len(value) < MIN_SECRET_KEY_LENGTH:
        return f"SECRET_KEY is too short ({len(value)} characters; at least {MIN_SECRET_KEY_LENGTH}). {HOW_TO}"
    return None


def mcp_secret_problem(value: str) -> str | None:
    if value in KNOWN_DEFAULT_SECRETS:
        return f"AGENTS_MCP_JWT_SECRET is empty or a default that ships with SyncroFin (agents are enabled). {HOW_TO}"
    return None


def database_password_problem(database_url: str) -> str | None:
    """The stock `postgres` password is fine on your own laptop and not on a network."""
    try:
        parts = urlsplit(database_url)
        host, password = parts.hostname, parts.password
    except ValueError:
        return None
    if password == "postgres" and host not in _LOCAL_HOSTS:
        return (
            f"DATABASE_URL uses the default database password 'postgres' on host '{host}'. "
            "Set POSTGRES_PASSWORD to a long random value (openssl rand -hex 24)."
        )
    return None


def refusal_message(problems: list[str]) -> str:
    """The error raised at startup: what is wrong, one line each, and the escape hatch."""
    lines = "\n".join(f"  - {problem}" for problem in problems)
    return f"Refusing to start with insecure defaults (set DEBUG=true only for local development):\n{lines}"
