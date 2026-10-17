"""`POST /api/auth/forgot-password`, without a stopwatch side channel.

The library's endpoint answers 202 for every address, which is right. But for a
real account it first computes a bcrypt fingerprint of the current password
(~200 ms), and for an unknown address it returns at once (~20 ms). Same status,
different time: anyone with a timer could ask "does this person use SyncroFin?"
for any address they like. Sending the mail in the background (see
`email_service.send_in_background`) does not help, because the cost is in
building the token, before any mail exists.

So this route does the *same work* on both paths: an unknown address pays for an
equivalent hash and is then thrown away. It is mounted ahead of the library's
router, so it wins the path; `POST /reset-password` stays the library's.
"""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, status
from fastapi_users import exceptions
from pydantic import BaseModel, EmailStr

from app.core.auth import UserManager, get_user_manager

router = APIRouter()


class ForgotPasswordBody(BaseModel):
    email: EmailStr


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(
    body: ForgotPasswordBody,
    user_manager: UserManager = Depends(get_user_manager),
) -> None:
    try:
        user = await user_manager.get_by_email(body.email)
    except exceptions.UserNotExists:
        # Burn the cost the real path pays, so the two are indistinguishable by time.
        user_manager.password_helper.hash(secrets.token_urlsafe(24))
        return None

    try:
        await user_manager.forgot_password(user)
    except exceptions.UserInactive:
        # Same answer as for a stranger: an inactive account is not to be revealed either.
        return None
    return None
