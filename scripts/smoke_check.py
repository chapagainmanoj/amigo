"""Production smoke checks for channel delivery and scheduler firing.

Usage:
    python scripts/smoke_check.py --channel
    python scripts/smoke_check.py --scheduler
    python scripts/smoke_check.py --all

The channel check sends a real Telegram message using TELEGRAM_BOT_TOKEN and
SMOKE_TEST_CHAT_ID, resolving the linked participant's Daily conversation through the Store.
The channel check also requires the configured database/schema.
The scheduler check is intentionally in-memory: it proves
APScheduler can fire through the MessageChannel interface without writing to
production Supabase tables.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.channels.base import ChannelCapabilities  # noqa: E402
from src.scheduler.reminders import ReminderScheduler  # noqa: E402


class SmokeChannel:
    """Recording channel used by the in-memory scheduler smoke check."""

    # Local and in-process like the CLI, so it is an app every participant may use.
    channel_id = "cli"
    capabilities = ChannelCapabilities()

    async def recipient_for(self, user):
        return user["chat_id"]

    def __init__(self):
        self.sent: list[dict] = []
        self._sent_event = asyncio.Event()

    async def send_message(
        self,
        chat_id: str | int,
        text: str,
        *,
        buttons: list[list[dict[str, str]]] | None = None,
        conversation=None,
    ) -> int:
        message_id = len(self.sent) + 1
        self.sent.append({
            "chat_id": chat_id,
            "text": text,
            "buttons": buttons,
            "message_id": message_id,
        })
        self._sent_event.set()
        return message_id

    async def edit_message_buttons(
        self,
        chat_id: str | int,
        message_id: int,
        *,
        buttons: list[list[dict[str, str]]] | None = None,
        conversation=None,
    ) -> None:
        return None

    async def wait_for_send(self, timeout: float = 5.0) -> None:
        await asyncio.wait_for(self._sent_event.wait(), timeout=timeout)


class SmokeStore:
    """Minimal store interface needed by ReminderScheduler._send_reminder."""

    def __init__(self):
        self.reminders = {
            "smoke-reminder": {
                "user_id": "smoke-user",
                "status": "pending",
                "task_status": "pending",
                "updates": [],
            }
        }

    async def get_user_by_id(self, user_id):
        if user_id == "smoke-user":
            return {"user_id": user_id, "chat_id": 0, "primary_channel": "cli"}
        return None

    async def claim_reminder_for_send(
        self, reminder_id: str, user_id: str, idempotency_key: str
    ) -> dict | None:
        reminder = self.reminders.get(reminder_id)
        if (
            not reminder
            or reminder["user_id"] != user_id
            or reminder["status"] != "pending"
        ):
            return None
        reminder["status"] = "sending"
        return {
            "claimed": True,
            "task_status": reminder["task_status"],
            "attempt": {"attempt_id": idempotency_key},
        }

    async def finish_reminder_delivery(
        self,
        *,
        attempt_id: str,
        reminder_id: str,
        user_id: str,
        result: str,
        normalized_cause: str | None,
        retry_decision: str,
        telegram_message_id: int | None,
        channel: str = "telegram",
        channel_message_ref: str | None = None,
    ) -> dict:
        reminder = self.reminders[reminder_id]
        if reminder["user_id"] != user_id or attempt_id is None:
            raise ValueError("Reminder delivery state conflict")
        reminder.update(
            status="sent" if result == "accepted" else (
                "pending" if retry_decision == "retry" else "failed"
            ),
            telegram_message_id=telegram_message_id,
            delivery_channel=channel,
            channel_message_ref=channel_message_ref,
        )
        reminder["updates"].append(
            {
                "result": result,
                "normalized_cause": normalized_cause,
                "retry_decision": retry_decision,
            }
        )
        return {"attempt": {"attempt_id": attempt_id, "result": result}}

    async def update_reminder(
        self, reminder_id: str, updates: dict, user_id: str
    ) -> dict:
        reminder = self.reminders[reminder_id]
        if reminder["user_id"] != user_id:
            raise ValueError("Reminder not found")
        reminder.update(updates)
        reminder["updates"].append(dict(updates))
        return reminder

    async def get_pending_reminders_for_reload(self, cutoff: datetime) -> list[dict]:
        return []


async def smoke_channel() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("SMOKE_TEST_CHAT_ID")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required for --channel")
    if not chat_id:
        raise RuntimeError("SMOKE_TEST_CHAT_ID is required for --channel")

    from src.channels.telegram import TelegramChannel
    from src.config import settings
    from src.conversations import ModeConversationService
    from src.memory.store import MemoryStore
    from src.runtime_config import is_production
    from src.schema import EXPECTED_SCHEMA_VERSION

    store = MemoryStore()
    await store.connect()
    await store.verify_schema_version(EXPECTED_SCHEMA_VERSION)
    user = await store.get_user_by_chat_id(int(chat_id))
    if not user:
        raise RuntimeError("SMOKE_TEST_CHAT_ID must name a linked test participant")
    channel = TelegramChannel(token=token)
    await channel.initialize(production=is_production(settings))
    conversation = await ModeConversationService(store, channel).ensure(user)
    message_id = await channel.send_message(
        int(chat_id),
        "Amigo smoke check: Telegram channel OK at " + datetime.now(UTC).isoformat(),
        conversation=conversation,
    )
    print(f"channel: sent Telegram smoke message {message_id} to {chat_id}")


async def smoke_scheduler() -> None:
    channel = SmokeChannel()
    store = SmokeStore()
    scheduler = ReminderScheduler(channel=channel, store=store)
    scheduler.start()
    try:
        scheduler.schedule_reminder(
            user_id="smoke-user",
            reminder_id="smoke-reminder",
            send_time=datetime.now(UTC) + timedelta(seconds=1),
            chat_id=0,
            task_title="run scheduler smoke check",
        )
        await channel.wait_for_send()
    finally:
        scheduler.shutdown()

    reminder = store.reminders["smoke-reminder"]
    if reminder["status"] != "sent":
        raise RuntimeError(f"expected smoke reminder to be sent, got {reminder['status']!r}")
    if not channel.sent or channel.sent[0]["buttons"] is None:
        raise RuntimeError("scheduler smoke did not deliver reminder buttons")
    print("scheduler: in-memory APScheduler reminder fired through channel")


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run Amigo production smoke checks")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--channel", action="store_true", help="send a real Telegram ping")
    group.add_argument("--scheduler", action="store_true", help="run in-memory scheduler ping")
    group.add_argument("--all", action="store_true", help="run channel and scheduler checks")
    args = parser.parse_args()

    try:
        if args.channel or args.all:
            await smoke_channel()
        if args.scheduler or args.all:
            await smoke_scheduler()
    except Exception as exc:
        print(f"smoke check failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
