"""Authenticated participant Mode availability, with channel-owned conversation links."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from src.access import is_full_access_user
from src.agent.catalogue import build_registry
from src.agent.modes import ModeUnavailableError
from src.agent.policies import admit
from src.api.dependencies import get_activated_user, get_store
from src.channels.base import ConversationRef
from src.coaching_templates import COACH_TEMPLATES, TEMPLATES_BY_ID
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
    context = ToolContext(
        store=store, scheduler=None, channel=channel, user=user, session_id="",
        # Admission reads only the participant and the store; no message is sent from here.
        chat_id=0,
        timezone=user.get("timezone") or "UTC", turn_id="mode-availability",
    )
    result = []
    for mode in build_registry():
        grant = await store.get_active_mode_grant(user["user_id"], mode.id)
        available, consent_required = True, False
        try:
            await admit(context, mode)
        except ModeUnavailableError as refusal:
            # Only the participant's own I agree tap is missing: the Mode is open to them.
            consent_required = refusal.participant_message == COACH_PROCESSING_NOTICE
            available = consent_required
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


class OpenModeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template_id: str | None = None


@router.get("/api/coaching/templates")
async def list_coach_templates(
    user: Annotated[dict, Depends(get_activated_user)],
    store: Annotated[object, Depends(get_store)],
):
    """Ready-made Coach goals, and the participant's current Program if one is running."""
    program = await store.get_coaching_program(user["user_id"])
    return {
        "templates": [
            {
                "id": t.id, "title": t.title, "goal": t.goal,
                "success_measure": t.success_measure, "check_in_days": t.check_in_days,
            }
            for t in COACH_TEMPLATES
        ],
        "current_program": (
            {"goal": program.get("goal"), "state": program.get("state")} if program else None
        ),
    }


@router.post("/api/modes/{mode_id}/open")
async def open_mode(
    mode_id: str,
    body: OpenModeRequest,
    request: Request,
    user: Annotated[dict, Depends(get_activated_user)],
    store: Annotated[object, Depends(get_store)],
):
    """Switch the participant's chat to a Mode, as if they had sent /mode <id> in Telegram."""
    if mode_id not in {mode.id for mode in build_registry()}:
        raise HTTPException(status_code=404, detail="Unknown mode")
    note = None
    if body.template_id is not None:
        template = TEMPLATES_BY_ID.get(body.template_id)
        if mode_id != "coach" or template is None:
            raise HTTPException(status_code=404, detail="Unknown template")
        # One Coaching Program at a time.
        if await store.get_coaching_program(user["user_id"]) is not None:
            raise HTTPException(
                status_code=409,
                detail="You already have a coaching program. Stop it in Telegram first.",
            )
        note = template.note()
    opener = getattr(request.app.state, "open_mode", None)
    if opener is None:
        raise HTTPException(status_code=503, detail="Telegram is not connected here")
    result = await opener(user, mode_id, note=note)
    if result is None:
        raise HTTPException(status_code=409, detail="Connect Telegram first")
    opened, message = result
    return {"status": "opened" if opened else "refused", "message": message}
