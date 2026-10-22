"""Explicit job requests may produce a confirmed Mode offer; feature defaults off."""

import re
from dataclasses import dataclass

from src.agent.modes import ModeUnavailableError
from src.agent.runtime import FAILURE_REPLY
from src.tools.context import ToolContext


@dataclass(frozen=True)
class SuggestionReadiness:
    enabled: bool = False
    two_modes_released: bool = False
    switching_friction_reviewed: bool = False
    routing_policy_reviewed: bool = False

    async def complete(self):
        return all(
            (
                self.enabled,
                self.two_modes_released,
                self.switching_friction_reviewed,
                self.routing_policy_reviewed,
            )
        )


async def explicit_job_target(text):
    """Conservative authored rules, never mood, inferred need, silence or Task history."""
    normalized = " ".join(text.lower().split())
    if len(normalized) > 1000 or normalized.startswith("/"):
        return None
    # This is an additional suppression rule, not a crisis detector or safety certification.
    if re.search(r"\b(suicid\w*|self.harm|kill myself|hurt myself|crisis|emergency)\b", normalized):
        return None
    rules = (
        (
            "coach",
            r"\b(i want|help me|can you help me) (to )?(build|start|maintain) (a |an |my )?habit\b",
        ),
        ("reflect", r"\b(i want to|help me) (reflect on|think through)\b"),
        (
            "recommender",
            r"\b(help me|i want to) (compare|choose between) (laundry|washing|drying)\b",
        ),
    )
    matches = [mode for mode, pattern in rules if re.search(pattern, normalized)]
    return matches[0] if len(matches) == 1 else None


async def deny_turn_clearance(context, text, response):
    """Until reviewed safety/operation outcome metadata supplies affirmative clearance."""
    return False


class ModeSuggestionController:
    def __init__(self, modes, *, readiness=None, turn_clearance=None):
        self.modes = modes
        self.store, self.channel, self.runtime = modes.store, modes.channel, modes.runtime
        self.readiness = readiness or SuggestionReadiness()
        self.turn_clearance = turn_clearance or deny_turn_clearance

    async def offer(self, context, text, response):
        if context.mode_id != "daily" or response == FAILURE_REPLY:
            return None
        if not await self.readiness.complete():
            return None
        if not await self.turn_clearance(context, text, response):
            return None
        target = await explicit_job_target(text)
        if target is None:
            return None
        try:
            mode = await self.runtime.resolve(context, target)
        except (ModeUnavailableError, KeyError):
            return None
        offer = await self.store.create_mode_suggestion(
            context.user["user_id"],
            context.session_id,
            target,
            grant_required=mode.entitlement == "grant",
        )
        if offer:
            await self.channel.send_message(
                context.chat_id,
                f"Open {mode.name}? {mode.purpose}\n{mode.limits}\n"
                "This only opens the Mode; your message and history stay here.",
                buttons=[
                    [
                        {
                            "text": f"Open {mode.name}",
                            "callback_data": f"suggest:yes:{offer['offer_id']}",
                        },
                        {"text": "No thanks", "callback_data": f"suggest:no:{offer['offer_id']}"},
                    ]
                ],
                conversation=context.conversation,
            )
        return offer

    async def preference(self, user, chat_id, text, conversation=None):
        parts = text.strip().split()
        if len(parts) != 2 or parts[1] not in {"on", "off"}:
            reply = (
                "Use /suggestions on or /suggestions off. Offers still require release approval."
            )
        else:
            enabled = parts[1] == "on"
            await self.store.set_mode_suggestion_preference(user["user_id"], enabled)
            reply = (
                "Mode suggestions allowed when available." if enabled else "Mode suggestions off."
            )
        await self.channel.send_message(chat_id, reply, conversation=conversation)

    async def handle_callback(self, user, chat_id, data, conversation=None):
        parts = data.split(":")
        if len(parts) != 3 or parts[:1] != ["suggest"] or parts[1] not in {"yes", "no"}:
            return
        import uuid

        try:
            uuid.UUID(parts[2])
        except ValueError:
            return
        offer = await self.store.get_mode_suggestion(user["user_id"], parts[2])
        if not offer:
            return
        confirm = parts[1] == "yes"
        if confirm:
            if not await self.readiness.complete():
                return
            context = ToolContext(
                self.store,
                self.modes.scheduler,
                self.channel,
                user,
                offer["source_session_id"],
                chat_id,
                user.get("timezone") or "UTC",
                parts[2],
                conversation=conversation,
            )
            try:
                await self.runtime.resolve(context, offer["target_mode_id"])
            except (ModeUnavailableError, KeyError):
                await self.channel.send_message(
                    chat_id, "That Mode is no longer available.", conversation=conversation
                )
                return
        resolved = await self.store.resolve_mode_suggestion(user["user_id"], parts[2], confirm)
        if not resolved or not confirm:
            return
        # Opens via the same resolver as an explicit command. No target model call or carried text.
        prepared = await self.modes.prepare(
            chat_id, user, f"/mode {offer['target_mode_id']}", parts[2], conversation
        )
        await self.channel.send_message(
            chat_id,
            prepared.response or "Mode opened.",
            conversation=prepared.context.conversation,
        )
