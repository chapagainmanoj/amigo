"""Authenticated participant Mode availability, with channel-owned conversation links."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from src.access import entitled, is_full_access_user
from src.agent.catalogue import build_registry
from src.api.dependencies import get_activated_user, get_store
from src.channels.base import ConversationRef
from src.mode_readiness import COACH_PROCESSING_NOTICE
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
        available = mode.status == "live" and await entitled(store, user, mode)
        consent_required = False
        if available and mode.entry_guard is not None:
            context = ToolContext(
                store=store, scheduler=None, channel=channel, user=user, session_id="",
                chat_id=await channel.recipient_for(user) if channel else 0,
                timezone=user.get("timezone") or "UTC", turn_id="mode-availability",
            )
            refusal = await mode.entry_guard(context)
            # Only the participant's own I agree tap is missing: the Mode is open to them.
            consent_required = refusal == COACH_PROCESSING_NOTICE
            available = not refusal or consent_required
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
            "consent_required": consent_required,
            "grant_expires_at": grant["expires_at"] if grant else None,
            "deep_link": link,
        })
    from src.config import settings

    full = is_full_access_user(user)
    access = {
        "tier": "full" if full else "trial",
        "messages_used": None if full else await store.count_participant_messages(user["user_id"]),
        "message_limit": None if full else settings.trial_message_limit,
    }
    return {"modes": result, "access": access}
