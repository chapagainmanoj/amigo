"""Participant's linked messaging apps and their primary channel (ADR 0004).

Provider identifiers (chat ids, phone numbers) are never returned: participants see which
apps are linked, not the addresses behind them.
"""

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, StrictStr

from src.access import OPEN_CHANNELS, may_use_channel
from src.api.dependencies import get_activated_user, get_store
from src.memory.identities import ChannelNotLinkedError
from src.memory.pairing import (
    PAIRING_TOKEN_HEX_LENGTH,
    PAIRING_TOKEN_TTL,
    PAIRING_TOKEN_WINDOW,
    ActivationTermsRequiredError,
    PairingTokenRateLimitError,
)
from src.utils import UTC, utc_now

router = APIRouter()
Actor = Annotated[dict, Depends(get_activated_user)]
Store = Annotated[object, Depends(get_store)]


class PrimaryChannelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel: StrictStr


def _connectable(request: Request, user: dict, linked) -> list[str]:
    """Second apps this process runs that this account may use and has not linked yet.

    Telegram stays the first app, linked through Activation; the others are added here.
    """
    registry = getattr(request.app.state, "channels", None)
    if registry is None:
        return []
    return sorted(
        channel.channel_id for channel in registry
        if channel.channel_id not in OPEN_CHANNELS and channel.channel_id not in linked
        and may_use_channel(user, channel.channel_id)
    )


async def _channels(request: Request, store, user_id: str) -> JSONResponse:
    user = await store.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(404, "User profile not found.")
    linked = await store.list_channel_identities(user_id)
    return JSONResponse(
        {
            "primary_channel": user.get("primary_channel", "telegram"),
            "linked": sorted(linked),
            "available": _connectable(request, user, linked),
        },
        headers={"Cache-Control": "no-store"},
    )


@router.get("/api/channels")
async def linked_channels(request: Request, user: Actor, store: Store):
    return await _channels(request, store, user["user_id"])


@router.post("/api/channels/{channel_id}/pairing-token")
async def second_app_pairing_token(channel_id: str, request: Request, user: Actor, store: Store):
    """A single-use code the participant sends to the other app as `/pair <code>`.

    The bot side re-checks the same rule (an activated full-access account) before linking.
    """
    current = await store.get_user_by_id(user["user_id"])
    if current is None:
        raise HTTPException(404, "User profile not found.")
    linked = await store.list_channel_identities(user["user_id"])
    if channel_id not in _connectable(request, current, linked):
        raise HTTPException(404, "That app cannot be connected to this account.")
    token = secrets.token_hex(PAIRING_TOKEN_HEX_LENGTH // 2)
    expires_at = utc_now() + PAIRING_TOKEN_TTL
    try:
        await store.create_pairing_token(token, current["supabase_auth_id"], expires_at)
    except ActivationTermsRequiredError:
        raise HTTPException(403, "Review and accept the beta limits first.") from None
    except PairingTokenRateLimitError:
        raise HTTPException(
            429,
            "Too many Pairing links requested. Try again later.",
            headers={"Retry-After": str(int(PAIRING_TOKEN_WINDOW.total_seconds()))},
        ) from None
    channel = request.app.state.channels.get(channel_id)
    return JSONResponse(
        {
            "channel": channel_id,
            "command": f"/pair {token}",
            "app_link": channel.connect_link,
            "expires_at": expires_at.replace(tzinfo=UTC).isoformat(),
        },
        headers={"Cache-Control": "no-store"},
    )


@router.post("/api/channels/primary")
async def set_primary_channel(
    body: PrimaryChannelRequest, request: Request, user: Actor, store: Store
):
    try:
        await store.set_primary_channel(user["user_id"], body.channel)
    except ChannelNotLinkedError:
        raise HTTPException(409, "That app is not linked to your account.") from None
    return await _channels(request, store, user["user_id"])
