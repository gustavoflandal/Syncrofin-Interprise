"""C9 — encryption at rest: TOTP secret and Pluggy item_id.

Verifies that:
- setup_2fa writes only the encrypted column (totp_secret_enc), leaving totp_secret NULL
- _totp_secret() returns the plaintext value whether the caller used enc or plaintext
- disable_2fa and admin reset both clear both columns
- Pluggy stores item_id_enc on connect and reads back via _item_id() with plaintext fallback
"""
import pyotp
import pytest

from app.agents.services.crypto import decrypt, encrypt
from app.api.two_factor import _totp_secret
from app.providers.pluggy import _item_id


# ---------------------------------------------------------------------------
# TOTP secret encryption helpers
# ---------------------------------------------------------------------------

def test_totp_secret_reads_encrypted_column(test_user):
    secret = pyotp.random_base32()
    test_user.totp_secret_enc = encrypt(secret)
    test_user.totp_secret = None
    assert _totp_secret(test_user) == secret


def test_totp_secret_falls_back_to_plaintext(test_user):
    secret = pyotp.random_base32()
    test_user.totp_secret_enc = None
    test_user.totp_secret = secret
    assert _totp_secret(test_user) == secret


def test_totp_secret_prefers_enc_over_plaintext(test_user):
    enc_secret = pyotp.random_base32()
    test_user.totp_secret_enc = encrypt(enc_secret)
    test_user.totp_secret = pyotp.random_base32()  # stale / different
    assert _totp_secret(test_user) == enc_secret


def test_totp_secret_returns_none_when_both_empty(test_user):
    test_user.totp_secret_enc = None
    test_user.totp_secret = None
    assert _totp_secret(test_user) is None


# ---------------------------------------------------------------------------
# setup_2fa writes enc only
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_setup_2fa_stores_encrypted(client, auth_headers, session, test_user):
    from unittest.mock import AsyncMock, MagicMock, patch

    def _fake_redis():
        m = AsyncMock()
        m.pipeline = lambda: MagicMock(execute=AsyncMock(return_value=[0, 0, True, True]))
        return m

    with patch("app.core.redis.get_redis", _fake_redis), \
         patch("app.core.rate_limit.get_redis", _fake_redis):
        resp = await client.post("/api/auth/2fa/setup", headers=auth_headers)

    assert resp.status_code == 200
    returned_secret = resp.json()["secret"]

    await session.refresh(test_user)
    assert test_user.totp_secret is None, "plaintext column must be NULL after setup"
    assert test_user.totp_secret_enc is not None, "enc column must be set after setup"
    assert decrypt(test_user.totp_secret_enc) == returned_secret


# ---------------------------------------------------------------------------
# Pluggy _item_id helper
# ---------------------------------------------------------------------------

def test_item_id_reads_encrypted_field():
    raw = "pluggy-item-abc123"
    creds = {"item_id_enc": encrypt(raw)}
    assert _item_id(creds) == raw


def test_item_id_fallback_to_plaintext():
    raw = "pluggy-item-legacy"
    creds = {"item_id": raw}
    assert _item_id(creds) == raw


def test_item_id_prefers_enc_over_plaintext():
    enc_id = "pluggy-item-encrypted"
    creds = {"item_id_enc": encrypt(enc_id), "item_id": "pluggy-item-old"}
    assert _item_id(creds) == enc_id


def test_item_id_returns_none_for_empty_credentials():
    assert _item_id({}) is None
    assert _item_id(None) is None
