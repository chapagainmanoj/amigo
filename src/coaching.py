"""Participant-facing Coaching Program approval and shared command adapter."""

import hashlib
import json
import uuid
from types import SimpleNamespace

from src.commands.base import CommandContext


def command_hash(action, values):
    return hashlib.sha256(
        json.dumps({"action": action, **values}, sort_keys=True).encode()
    ).hexdigest()


def coaching_callback(action, identifier, version=None):
    token = uuid.UUID(identifier).hex
    return f"coach:{action}:{token}" + (f":{version}" if version is not None else "")


class CoachingCommands:
    def __init__(self, store):
        self.store = store

    async def draft(self, context: CommandContext, **configuration):
        return await self.store.draft_coaching_program(
            context.actor_user_id,
            context.idempotency_key,
            command_hash("draft", configuration),
            **configuration,
        )

    async def change(self, context, program_id, version, action, **values):
        return await self.store.change_coaching_program(
            context.actor_user_id,
            program_id,
            version,
            action,
            context.idempotency_key,
            command_hash(action, {"program_id": program_id, "version": version, **values}),
            **values,
        )

    async def revise(self, context, program_id, version, **configuration):
        return await self.store.revise_coaching_draft(
            context.actor_user_id,
            program_id,
            version,
            context.idempotency_key,
            command_hash("revise", {"program_id": program_id, "version": version, **configuration}),
            **configuration,
        )


class CoachingController:
    def __init__(self, store, channel):
        self.store, self.channel = store, channel

    async def inspect(self, user, recipient, conversation=None):
        row = await self.store.get_coaching_program(user["user_id"])
        if row is None:
            await self.channel.send_message(
                recipient, "No current Coaching Program.", conversation=conversation
            )
            return
        if row["state"] == "draft":
            await self.show_approval(user["user_id"], row["program_id"], recipient, conversation)
            return
        actions = ["stop"]
        if row["state"] == "active":
            actions.insert(0, "pause")
        elif row["state"] == "paused":
            actions.insert(0, "resume")
        await self.channel.send_message(
            recipient,
            f"Coach Program: {row['state']}, version {row['version']}.\n"
            f"Goal: {row['goal']}\nYour success measure: {row['success_measure']}\n"
            f"Term ends: {row.get('ends_at') or 'not started'}.\n"
            "Pause or Stop does not delete Program records or conversation Messages.",
            conversation=conversation,
            buttons=[
                [
                    {
                        "text": action.title(),
                        "callback_data": coaching_callback(
                            action, row["program_id"], row["version"]
                        ),
                    }
                    for action in actions
                ]
            ],
        )

    async def show_approval(self, user_id, program_id, recipient, conversation=None):
        row = await self.store.get_coaching_program(user_id, program_id)
        if row is None or row["state"] != "draft":
            return "There is no draft ready for approval."
        token = await self.store.issue_coaching_approval(user_id, program_id, row["version"])
        days = ", ".join(str(day) for day in row["check_in_days"])
        term = (
            f"Existing term ends {row['ends_at']}; approval does not restart it. "
            if row.get("ends_at")
            else "14 days from first approval. "
        )
        await self.channel.send_message(
            recipient,
            f"Review your Coaching Program:\nGoal: {row['goal']}\n"
            f"Your success measure: {row['success_measure']}\n"
            f"Check-in weekdays (Mon=1): {days}; {row['check_in_time']} {row['timezone']}.\n"
            f"{term}At most one coaching message/day, within your shared budget "
            "and quiet hours. One missed follow-up, then silence. Pause or Stop any time.\n"
            "Approve this exact draft to start; leaving it unapproved starts nothing.",
            conversation=conversation,
            buttons=[
                [
                    {
                        "text": "Approve program",
                        "callback_data": coaching_callback("approve", token),
                    },
                    {
                        "text": "Stop draft",
                        "callback_data": coaching_callback("stop", program_id, row["version"]),
                    },
                ]
            ],
        )
        return "Draft shown. Only the participant's approval button can start it."

    async def handle_consent(self, user, recipient, data, conversation=None) -> bool:
        """Record the participant's own tap on the reviewed Coach processing notice."""
        from src.mode_readiness import COACH_CONSENT_VERSION, coach_readiness

        if data != f"consent:{COACH_CONSENT_VERSION}" or not await coach_readiness.complete():
            await self.channel.send_message(
                recipient, "Coach is unavailable.", conversation=conversation
            )
            return False
        await self.store.set_coaching_consent(user["user_id"], COACH_CONSENT_VERSION)
        return True

    async def handle_callback(self, user, recipient, data, conversation=None):
        try:
            parts = data.split(":")
            if parts[0] != "coach" or len(parts) not in {3, 4}:
                return
            action, identifier = parts[1], str(uuid.UUID(parts[2]))
            if action not in {"pause", "stop"}:
                from src.agent.catalogue import build_registry
                from src.agent.modes import ModeUnavailableError
                from src.agent.policies import admit

                try:
                    await admit(
                        SimpleNamespace(store=self.store, user=user), build_registry()["coach"]
                    )
                except ModeUnavailableError as refusal:
                    message = (
                        refusal.participant_message
                        if refusal.reason == "readiness" else "Coach is unavailable."
                    )
                    await self.channel.send_message(recipient, message, conversation=conversation)
                    return
            if action == "approve" and len(parts) == 3:
                result = await self.store.confirm_coaching_approval(
                    user["user_id"],
                    identifier,
                    f"coach-approve:{identifier}",
                    command_hash("approve", {"token": identifier}),
                )
            elif action in {"pause", "stop", "resume", "continue", "adjust"} and len(parts) == 4:
                values = {"weekly_choice": action} if action in {"continue", "adjust"} else {}
                command = "record_weekly_choice" if values else action
                result = await CoachingCommands(self.store).change(
                    CommandContext(user["user_id"], "telegram", data),
                    identifier,
                    int(parts[3]),
                    command,
                    **values,
                )
            else:
                return
        except ValueError:
            await self.channel.send_message(
                recipient,
                "That program control is unavailable or changed. Review its current state.",
                conversation=conversation,
            )
            return
        row = result["program"]
        row = await self.store.get_coaching_program(user["user_id"], row["program_id"]) or row
        await self.channel.send_message(
            recipient,
            f"Coaching Program: {row['state']}.",
            conversation=conversation,
            buttons=[
                [
                    {
                        "text": "Pause",
                        "callback_data": coaching_callback(
                            "pause", row["program_id"], row["version"]
                        ),
                    },
                    {
                        "text": "Stop",
                        "callback_data": coaching_callback(
                            "stop", row["program_id"], row["version"]
                        ),
                    },
                ]
            ]
            if row["state"] == "active"
            else None,
        )
