"""What a new account starts with. Brazilian by default; every value is overridable by environment.

This is the single place the defaults live: the user model, the schemas, registration and the
first-run setup all read from here, so a fresh instance opens in Portuguese, in reais, with the
Brazilian date format and time zone, and with the Portuguese default categories and wallet.
A person who picks something else at registration keeps what they picked.
"""

from app.core.config import get_settings


def default_preferences() -> dict[str, str]:
    settings = get_settings()
    return {
        "language": settings.default_language,
        "date_format": settings.default_date_format,
        "timezone": settings.default_timezone,
        "currency_display": settings.default_currency,
    }
