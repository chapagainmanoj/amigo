"""Participant-facing Coaching Program approval and shared command adapter."""

import hashlib
import json
import uuid
from datetime import time
from types import SimpleNamespace

from src.commands.base import CommandContext


def command_hash(action, values):
    return hashlib.sha256(
        json.dumps({"action": action, **values}, sort_keys=True).encode()
    ).hexdigest()


def coaching_callback(action, identifier, version=None):
    token = uuid.UUID(identifier).hex
    return f"coach:{action}:{token}" + (f":{version}" if version is not None else "")


_DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def schedule_text(check_in_days, check_in_time: str) -> str:
    """Readable check-in schedule, e.g. "Mon to Fri at 11:00 pm"."""
    days = sorted(set(check_in_days))
    if days == list(range(1, 8)):
        label = "Every day"
    elif len(days) > 2 and days == list(range(days[0], days[-1] + 1)):
        label = f"{_DAY_NAMES[days[0] - 1]} to {_DAY_NAMES[days[-1] - 1]}"
    else:
        label = ", ".join(_DAY_NAMES[day - 1] for day in days)
    hour, minute = (int(part) for part in check_in_time.split(":")[:2])
    clock = f"{(hour % 12) or 12}:{minute:02d} {'am' if hour < 12 else 'pm'}"
    return f"{label} at {clock}"


def quiet_hours_conflict(user: dict, check_in_time: str) -> str | None:
    """Why a check-in at this local time could never be sent, or None if it can."""
    from datetime import datetime

    from src.scheduler.coaching import _quiet

    wake, sleep = user.get("wake_time") or "07:30", user.get("sleep_time") or "23:00"
    try:
        local = datetime.combine(datetime(2000, 1, 3).date(), time.fromisoformat(check_in_time))
    except ValueError:
        return None
    if _quiet(local, wake, sleep):
        return (
            f"Draft not saved: {check_in_time} is inside the participant's quiet hours "
            f"({sleep} to {wake}), so no check-in could ever be sent. Ask for a time between "
            f"{wake} and {sleep}, with an example (for a bedtime goal, a morning check-in about "
            "last night works)."
        )
    return None


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
        term = (
            f"Existing term ends {row['ends_at']}; approval does not restart it. "
            if row.get("ends_at")
            else "14 days from first approval. "
        )
        await self.channel.send_message(
            recipient,
            f"Review your Coaching Program:\nGoal: {row['goal']}\n"
            f"Your success measure: {row['success_measure']}\n"
            f"Check-ins: {schedule_text(row['check_in_days'], row['check_in_time'])} "
            f"({row['timezone']}).\n"
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
                    CommandContext(user["user_id"], self.channel.channel_id, data),
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
            f"Coaching Program: {row['state']}."
            + (
                f" Check-ins: {schedule_text(row['check_in_days'], row['check_in_time'])}."
                if row["state"] == "active" and row.get("check_in_days") else ""
            ),
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
