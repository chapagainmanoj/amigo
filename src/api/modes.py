"""Authenticated participant Mode availability, with channel-owned conversation links."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from src.agent.catalogue import build_registry
from src.api.dependencies import get_activated_user, get_store
from src.channels.base import ConversationRef
from src.tools.context import ToolContext

router = APIRouter()


@router.get("/api/modes")
async def list_modes(
    request: Request,
    user: Annotated[dict, Depends(get_activated_user)],
    store: Annotated[object, Depends(get_store)],
):
    """Show only the authenticated participant's access and conversation addresses."""
    channel = getattr(request.app.state, "channel", None)
    channel_id = getattr(channel, "channel_id", None)
    conversations = await store.list_mode_conversations(user["user_id"])
    result = []
    for mode in build_registry():
        grant = await store.get_active_mode_grant(user["user_id"], mode.id)
        entitled = mode.entitlement == "activated" or (
            mode.entitlement == "grant" and grant is not None
        )
        available = mode.status == "live" and entitled
        if available and mode.entry_guard is not None:
            context = ToolContext(
                store=store, scheduler=None, channel=channel, user=user, session_id="",
                chat_id=await channel.recipient_for(user) if channel else 0,
                timezone=user.get("timezone") or "UTC", turn_id="mode-availability",
            )
            available = not bool(await mode.entry_guard(context))
        address = next((
            row for row in conversations
            if row["mode_id"] == mode.id and row["channel"] == channel_id
            and row.get("closed_at") is None
        ), None)
        conversation = (
            ConversationRef(address["channel"], address["endpoint"]) if address else None
        )
        link = (
            await channel.conversation_link(conversation)
            if channel is not None and available else None
        )
        result.append({
            "id": mode.id,
            "name": mode.name,
            "purpose": mode.purpose,
            "status": mode.status,
            "available": available,
            "grant_expires_at": grant["expires_at"] if grant else None,
            "deep_link": link,
        })
    return {"modes": result}
