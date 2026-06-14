"""Production smoke checks for channel delivery and scheduler firing.

Usage:
    python scripts/smoke_check.py --channel
    python scripts/smoke_check.py --scheduler
    python scripts/smoke_check.py --all

The channel check sends a real Telegram message using TELEGRAM_BOT_TOKEN and
SMOKE_TEST_CHAT_ID. The scheduler check is intentionally in-memory: it proves
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

from telegram import Bot

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.scheduler.reminders import ReminderScheduler  # noqa: E402


class SmokeChannel:
    """Recording channel used by the in-memory scheduler smoke check."""

    def __init__(self):
        self.sent: list[dict] = []
        self._sent_event = asyncio.Event()

    async def send_message(
        self,
        chat_id: str | int,
        text: str,
        *,
        buttons: list[list[dict[str, str]]] | None = None,
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
    ) -> None:
        return None

    async def wait_for_send(self, timeout: float = 5.0) -> None:
        await asyncio.wait_for(self._sent_event.wait(), timeout=timeout)


class SmokeStore:
    """Minimal store interface needed by ReminderScheduler._send_reminder."""

    def __init__(self):
        self.reminders = {
            "smoke-reminder": {
                "status": "pending",
                "task_status": "pending",
                "updates": [],
            }
        }

    async def claim_reminder_for_send(self, reminder_id: str) -> dict | None:
        reminder = self.reminders.get(reminder_id)
        if not reminder or reminder["status"] != "pending":
            return None
        reminder["status"] = "sending"
        return {"status": "sending", "tasks": {"status": reminder["task_status"]}}

    async def update_reminder(self, reminder_id: str, updates: dict) -> dict:
        reminder = self.reminders[reminder_id]
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

    bot = Bot(token=token)
    message = await bot.send_message(
        chat_id=chat_id,
        text=(
            "Amigo smoke check: Telegram channel OK at "
            f"{datetime.now(UTC).isoformat()}"
        ),
    )
    print(f"channel: sent Telegram smoke message {message.message_id} to {chat_id}")


async def smoke_scheduler() -> None:
    channel = SmokeChannel()
    store = SmokeStore()
    scheduler = ReminderScheduler(channel=channel, store=store)
    scheduler.start()
    try:
        scheduler.schedule_reminder(
            user_id="smoke-user",
            reminder_id="smoke-reminder",
            send_time=datetime.now() + timedelta(seconds=1),
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
