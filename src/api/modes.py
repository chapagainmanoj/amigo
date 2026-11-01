"""Authenticated participant Mode availability, with channel-owned conversation links."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from src.access import is_full_access_user
from src.agent.catalogue import build_registry
from src.agent.modes import DAILY_MODE_ID, ModeUnavailableError
from src.agent.policies import admit
from src.api.dependencies import get_activated_user, get_store
from src.channels.base import ConversationRef
from src.coaching import CoachingCommands
from src.coaching_templates import COACH_TEMPLATES, TEMPLATES_BY_ID
from src.commands.base import (
    CommandContext,
    IdempotencyConflictError,
    InvalidTransitionError,
    StaleVersionError,
)
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
    # The open Daily-control Session holds the chat's current Mode, the field /mode updates.
    control = await store.get_active_session(user["user_id"], DAILY_MODE_ID)
    current_mode = (control or {}).get("active_mode_id") or DAILY_MODE_ID
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
            "current": mode.id == current_mode,
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
    return {"modes": result, "access": access, "current_mode": current_mode}


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
            {
                "program_id": program.get("program_id"), "version": program.get("version"),
                "goal": program.get("goal"), "state": program.get("state"),
            }
            if program else None
        ),
    }


class StopProgramRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    program_id: UUID
    expected_version: int = Field(ge=1)


@router.post("/api/coaching/program/stop")
async def stop_coach_program(
    body: StopProgramRequest,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=200)
    ],
    user: Annotated[dict, Depends(get_activated_user)],
    store: Annotated[object, Depends(get_store)],
):
    """Stop the participant's Coaching Program, as the Stop button in Telegram does."""
    try:
        result = await CoachingCommands(store).change(
            CommandContext(user["user_id"], "dashboard", idempotency_key),
            str(body.program_id),
            body.expected_version,
            "stop",
        )
    except (IdempotencyConflictError, StaleVersionError, InvalidTransitionError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from None
    return {"state": result["program"]["state"]}


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
                detail="You already have a coaching program. Stop it first.",
            )
        note = template.note()
    opener = getattr(request.app.state, "open_mode", None)
    if opener is None:
        raise HTTPException(status_code=503, detail="Messaging is not connected here")
    result = await opener(user, mode_id, note=note)
    if result is None:
        raise HTTPException(status_code=409, detail="Connect a messaging app first")
    opened, message = result
    return {"status": "opened" if opened else "refused", "message": message}
