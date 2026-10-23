"""Participant-confirmed handoff proposals; never available to Daily's Tool schema."""

import base64
import uuid

from pydantic_ai import FunctionToolset, RunContext

from src.access import grant_required
from src.tools.context import ToolContext

HANDOFFS: FunctionToolset[ToolContext] = FunctionToolset(max_retries=0)


def handoff_callback(action: str, handoff_id: str, session_id: str) -> str:
    tokens = [base64.urlsafe_b64encode(uuid.UUID(value).bytes).decode().rstrip("=")
              for value in (handoff_id, session_id)]
    return f"handoff:{action}:" + ":".join(tokens)


def parse_handoff_callback(value: str):
    prefix, action, handoff, session = value.split(":")
    if prefix != "handoff" or action not in {"c", "d"}:
        raise ValueError("Invalid handoff callback")
    values = []
    for token in (handoff, session):
        if len(token) != 22:
            raise ValueError("Invalid handoff callback")
        decoded = base64.b64decode(token + "==", altchars=b"-_", validate=True)
        values.append(str(uuid.UUID(bytes=decoded)))
    return action, *values


@HANDOFFS.tool
async def propose_handoff(
    ctx: RunContext[ToolContext], target_mode_id: str, carried_request: str
) -> str:
    """Offer a request to another declared Mode. Nothing executes until the participant confirms.

    Args:
        target_mode_id: A handoff target declared by this Mode.
        carried_request: The exact request shown to the participant before confirmation.
    """
    deps = ctx.deps
    registry = deps.mode_registry
    source = await registry.get(deps.mode_id)
    if target_mode_id not in source.handoffs:
        return "That handoff target is not available. Nothing was passed."
    target = await registry.get(target_mode_id)
    if target.status != "live":
        return "That Mode isn't available. Nothing was passed."
    pending = await deps.store.create_handoff(
        deps.user["user_id"], deps.session_id, source.id, target.id, carried_request,
        source_grant_required=grant_required(deps.user, source),
        target_grant_required=grant_required(deps.user, target),
    )
    if pending["status"] != "pending":
        return "The handoff could not be proposed. Nothing was passed."
    handoff_id = pending["handoff"]["handoff_id"]
    await deps.channel.send_message(
        deps.chat_id, f"Pass this request to {target.name}?\n{carried_request}",
        conversation=deps.conversation,
        buttons=[[{"text": "Confirm", "callback_data": handoff_callback(
            "c", handoff_id, deps.session_id
        )}, {"text": "Decline", "callback_data": handoff_callback(
            "d", handoff_id, deps.session_id
        )}]],
    )
    return "Handoff proposed. Wait for the participant's confirmation before passing anything."
