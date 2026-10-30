"""Participant's linked messaging apps and their primary channel (ADR 0004).

Provider identifiers (chat ids, phone numbers) are never returned: participants see which
apps are linked, not the addresses behind them.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, StrictStr

from src.api.dependencies import get_activated_user, get_store
from src.memory.identities import ChannelNotLinkedError

router = APIRouter()
Actor = Annotated[dict, Depends(get_activated_user)]
Store = Annotated[object, Depends(get_store)]


class PrimaryChannelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel: StrictStr


async def _channels(store, user_id: str) -> JSONResponse:
    user = await store.get_user_by_id(user_id)
    return JSONResponse(
        {
            "primary_channel": user.get("primary_channel", "telegram"),
            "linked": sorted(await store.list_channel_identities(user_id)),
        },
        headers={"Cache-Control": "no-store"},
    )


@router.get("/api/channels")
async def linked_channels(user: Actor, store: Store):
    return await _channels(store, user["user_id"])


@router.post("/api/channels/primary")
async def set_primary_channel(body: PrimaryChannelRequest, user: Actor, store: Store):
    try:
        await store.set_primary_channel(user["user_id"], body.channel)
    except ChannelNotLinkedError:
        raise HTTPException(409, "That app is not linked to your account.") from None
    return await _channels(store, user["user_id"])
