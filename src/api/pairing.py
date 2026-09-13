"""Verified Dashboard Account to Telegram Pairing adapter."""

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import get_bot_username, get_store
from src.auth import AuthenticatedIdentity, get_authenticated_identity
from src.config import settings
from src.memory.pairing import (
    PAIRING_TOKEN_HEX_LENGTH,
    PAIRING_TOKEN_TTL,
    PAIRING_TOKEN_WINDOW,
    ActivationTermsRequiredError,
    PairingTokenRateLimitError,
)
from src.utils import utc_now

router = APIRouter()


@router.post("/api/pairing-token")
async def get_pairing_token(
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    store: Annotated[object, Depends(get_store)],
    bot_username: Annotated[str, Depends(get_bot_username)],
):
    """Issue one expiring Pairing link only after verified acknowledgement."""
    auth_id = identity.auth_id
    if not identity.email_verified:
        raise HTTPException(status_code=403, detail="Verify your email before connecting Telegram.")
    activation = await store.get_activation_state(auth_id)
    if not activation.get("acknowledged_at"):
        raise HTTPException(status_code=403, detail="Review and accept the beta limits first.")
    if settings.access_mode == "closed":
        raise HTTPException(status_code=503, detail="New Pairing links are temporarily disabled.")
    if await store.get_user_by_auth_id(auth_id):
        raise HTTPException(status_code=409, detail="Dashboard account is already linked.")

    token = secrets.token_hex(PAIRING_TOKEN_HEX_LENGTH // 2)
    expires_at = utc_now() + PAIRING_TOKEN_TTL
    try:
        await store.create_pairing_token(token, auth_id, expires_at)
    except ActivationTermsRequiredError:
        raise HTTPException(
            status_code=403,
            detail="Review and accept the beta limits first.",
        ) from None
    except PairingTokenRateLimitError:
        raise HTTPException(
            status_code=429,
            detail="Too many Pairing links requested. Try again later.",
            headers={"Retry-After": str(int(PAIRING_TOKEN_WINDOW.total_seconds()))},
        ) from None

    return {
        "bot_link": f"https://t.me/{bot_username}?start=pair_{token}",
        "expires_at": expires_at.isoformat(),
    }
