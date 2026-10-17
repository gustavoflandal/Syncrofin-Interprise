"""Public capability/feature-flag endpoint.

Tells the frontend which optional features are enabled so it can hide
nav items, routes, etc. Lightweight — no auth required.
"""
from fastapi import APIRouter

from app.core import password_policy
from app.core.config import get_settings
from app.core.feature_flags import feature_flag

router = APIRouter(prefix="/api", tags=["info"])


@router.get("/info")
async def get_app_info():
    return {
        "features": {
            "agents": feature_flag("AGENTS_ENABLED"),
            "tesouro_direto": feature_flag("TESOURO_DIRETO_ENABLED"),
            # Whether the server can send e-mail (SMTP configured). Decides what the
            # UI can promise: a reset link by e-mail, an invitation without a password.
            "email": get_settings().smtp_enabled,
        },
        # What a password has to be, so the forms can say so before the server has to.
        "password_min_length": password_policy.minimum_length(),
    }
