"""CLI entrypoint — chat with Amigo in your terminal.

Usage:
    APP_CHANNEL=cli GOOGLE_API_KEY=your-key python -m src.cli
    APP_CHANNEL=cli GOOGLE_API_KEY=your-key python -m src.cli --onboard
"""

import argparse
import asyncio
import logging
import signal
import sys
from datetime import UTC, timedelta

from src.activation import ACTIVATION_POLICY_VERSION
from src.bot.handlers import BotHandlers
from src.bot.update_claims import ParticipantTurnSerializer
from src.channels.cli import CLIChannel
from src.commands.activation import CreateActivationTestCommand
from src.commands.base import CommandContext
from src.commands.tasks import ResolveTaskCommand
from src.config import settings
from src.maintenance import run_isolated_steps
from src.memory.memory_store import InMemoryStore
from src.memory.sessions import SessionManager
from src.observability import quiet_routine_logs
from src.runtime_config import require_agent_credentials, validate_runtime_configuration
from src.scheduler.outbox import SchedulerOutboxWorker
from src.scheduler.reminders import ReminderScheduler
from src.utils import utc_now

# ANSI
_GREEN = "\033[92m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_CYAN = "\033[96m"
_RESET = "\033[0m"

DEV_CHAT_ID = 12345
DEV_TIMEZONE = "Asia/Kathmandu"

logger = logging.getLogger(__name__)


def _print_banner():
    print(f"""
{_CYAN}{_BOLD}╔══════════════════════════════════════╗
║         🤝 Amigo CLI Mode            ║
╚══════════════════════════════════════╝{_RESET}
{_DIM}In-memory store • no Telegram • no Supabase
Type /quit to exit, /tasks to see tasks, /debug to toggle debug logging{_RESET}
""")


async def _seed_dev_user(store: InMemoryStore) -> dict:
    """Pre-create an onboarded dev user so you skip straight to chatting."""
    # This fixture exists only in the CLI's disposable InMemoryStore. Use the canonical
    # Activation transitions so Telegram's production gate stays exercised and unchanged.
    auth_id = "cli-development-fixture"
    await store.acknowledge_activation_terms(auth_id, ACTIVATION_POLICY_VERSION)
    user = await store.create_user(DEV_CHAT_ID)
    user_id = user["user_id"]
    await store.update_user(user_id, {"supabase_auth_id": auth_id, "primary_channel": "cli"})
    await store.update_activation_profile(
        auth_id, name="Dev", timezone=DEV_TIMEZONE, wake_time="07:30", sleep_time="23:00"
    )
    result = await CreateActivationTestCommand(store).run(
        CommandContext(user_id, "dashboard", "cli-fixture-activation"),
        scheduled_at=utc_now().replace(tzinfo=UTC) + timedelta(minutes=2),
        timezone=DEV_TIMEZONE,
    )
    reminder_id = result["reminder"]["reminder_id"]
    # Simulated delivery, not a Telegram send. Resolving cancels its pending schedule effect.
    await store.update_reminder(
        reminder_id, {"status": "sent", "telegram_message_id": 0}, user_id
    )
    resolved = await ResolveTaskCommand(store).run(
        CommandContext(user_id, "telegram", "cli-fixture-complete"),
        task_id=result["task"]["task_id"], outcome="completed", acted_reminder_id=reminder_id,
    )
    # Both fixture effects were simulated above; never enqueue them on the running scheduler.
    for effect in [*result["effects"], *resolved["effects"]]:
        await store.complete_scheduler_effect(
            effect["effect_id"], user_id, succeeded=True, error_type=None
        )
    activation = await store.get_activation_state(auth_id)
    if not activation["completed"]:
        raise RuntimeError("CLI development fixture failed Activation")
    return await store.get_user_by_chat_id(DEV_CHAT_ID)


async def _handle_cli_commands(text: str, store: InMemoryStore) -> bool:
    """Handle CLI-only meta commands. Returns True if handled."""
    if text == "/quit":
        print(f"\n{_DIM}👋 See you later!{_RESET}\n")
        return True

    if text == "/tasks":
        user = await store.get_user_by_chat_id(DEV_CHAT_ID)
        if user:
            tasks = await store.get_today_tasks(user["user_id"], DEV_TIMEZONE)
            if tasks:
                print(f"\n{_BOLD}Today's tasks:{_RESET}")
                status_emoji = {
                    "pending": "⏳",
                    "completed": "✅",
                    "skipped": "⏭️",
                    "cancelled": "🚫",
                }
                for t in tasks:
                    emoji = status_emoji.get(t["status"], "❓")
                    print(f"  {emoji} {t['title']} ({t['status']})")
            else:
                print(f"\n{_DIM}No tasks yet today.{_RESET}")
        print()
        return True

    if text == "/debug":
        root = logging.getLogger()
        if root.level == logging.DEBUG:
            root.setLevel(logging.INFO)
            quiet_routine_logs()
            print(f"{_DIM}Debug logging OFF{_RESET}\n")
        else:
            root.setLevel(logging.DEBUG)
            quiet_routine_logs(False)
            print(f"{_DIM}Debug logging ON{_RESET}\n")
        return True

    return False


async def run_cli(onboard: bool = False):
    """Main CLI loop — wire components and run an interactive chat session."""
    validate_runtime_configuration(settings)
    require_agent_credentials(settings)
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    if settings.log_level != "DEBUG":
        quiet_routine_logs()

    _print_banner()

    # Wire components with in-memory store
    channel = CLIChannel()
    store = InMemoryStore()
    session_mgr = SessionManager(store)
    reminder_scheduler = ReminderScheduler(channel=channel, store=store)
    outbox_worker = SchedulerOutboxWorker(store, reminder_scheduler)

    handlers = BotHandlers(
        channel=channel,
        store=store,
        session_mgr=session_mgr,
        reminder_scheduler=reminder_scheduler,
    )

    serializer = ParticipantTurnSerializer()

    async def maintain_modes():
        async def recover():
            await handlers.handoffs.recover(serializer)

        await run_isolated_steps([
            ("memory_prune", handlers.memory.service.prune),
            ("handoff_recovery", recover),
        ])

    # Start the scheduler so reminders fire in the terminal
    reminder_scheduler.start()
    reminder_scheduler.start_outbox_worker(outbox_worker.drain_once)
    await reminder_scheduler.start_mode_maintenance(maintain_modes)

    # Seed dev user unless --onboard flag is set
    if not onboard:
        await _seed_dev_user(store)
        print(
            f"{_DIM}Dev user seeded (name=Dev, tz={DEV_TIMEZONE}); "
            f"simulated Activation complete.{_RESET}"
        )
        print(f"{_DIM}Use --onboard flag to walk through onboarding.{_RESET}\n")

    try:
        while True:
            try:
                text = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input(f"{_GREEN}{_BOLD}You > {_RESET}")
                )
            except EOFError:
                break

            text = text.strip()
            if not text:
                continue

            # CLI-only commands
            if text.startswith("/"):
                if text == "/quit":
                    await _handle_cli_commands(text, store)
                    break
                if await _handle_cli_commands(text, store):
                    continue

            # Check if input is a button tap (number while buttons are pending)
            if channel.pending_buttons and text.isdigit():
                callback_data = channel.resolve_button(text)
                if callback_data:
                    async with serializer.hold(DEV_CHAT_ID):
                        await handlers.handle_callback(
                            chat_id=DEV_CHAT_ID,
                            message_id=0,
                            data=callback_data,
                        )
                    continue
                else:
                    msg = "Invalid button choice. Type a valid number or a message."
                    print(f"{_DIM}{msg}{_RESET}\n")
                    continue

            # Regular message
            async with serializer.hold(DEV_CHAT_ID):
                await handlers.handle_message(chat_id=DEV_CHAT_ID, text=text)

    except KeyboardInterrupt:
        print(f"\n{_DIM}👋 Interrupted. Bye!{_RESET}\n")
    finally:
        reminder_scheduler.shutdown()


def main():
    parser = argparse.ArgumentParser(description="Amigo CLI — chat in your terminal")
    parser.add_argument(
        "--onboard",
        action="store_true",
        help="Run through the full onboarding flow instead of skipping it",
    )
    args = parser.parse_args()

    # Handle Ctrl+C gracefully
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))

    asyncio.run(run_cli(onboard=args.onboard))


if __name__ == "__main__":
    main()
