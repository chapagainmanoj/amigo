"""CLI entrypoint — chat with Amigo in your terminal.

Usage:
    APP_CHANNEL=cli GOOGLE_API_KEY=your-key python -m src.cli
    APP_CHANNEL=cli GOOGLE_API_KEY=your-key python -m src.cli --onboard
    DEV_MODEL=claude-cli:sonnet APP_CHANNEL=cli python -m src.cli --preview-modes
"""

import argparse
import asyncio
import logging
import secrets
import signal
import sys
from dataclasses import replace
from datetime import UTC, timedelta

from src.access import grant_required
from src.activation import ACTIVATION_POLICY_VERSION
from src.bot.handlers import BotHandlers
from src.bot.update_claims import ParticipantTurnSerializer, inbound_participant_key
from src.channels.cli import CLIChannel
from src.commands.activation import CreateActivationTestCommand
from src.commands.base import CommandContext
from src.commands.tasks import ResolveTaskCommand
from src.config import settings
from src.maintenance import run_isolated_steps
from src.memory.memory_store import InMemoryStore
from src.memory.pairing import PAIRING_TOKEN_HEX_LENGTH
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
PREVIEW_OPERATOR = "cli-preview"

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
    await store.update_user(user_id, {"supabase_auth_id": auth_id})
    # The CLI links as its own channel through dashboard-token Pairing, like any second app.
    token = secrets.token_hex(PAIRING_TOKEN_HEX_LENGTH // 2)
    await store.create_pairing_token(token, auth_id, utc_now() + timedelta(minutes=5))
    await store.complete_channel_pairing(token, "cli", str(DEV_CHAT_ID))
    await store.set_primary_channel(user_id, "cli")
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


def _preview_runtime():
    """Planned Modes as live for the disposable CLI store only; never a release decision.

    Entry guards (Coach admission, Reflect wellbeing consent) are dropped exactly as the
    candidate eval runner does. Reflect's deterministic safety routing still runs first.
    """
    from src.agent.catalogue import build_registry
    from src.agent.registry import ModeRegistry
    from src.agent.runtime import ModeRuntime

    if settings.app_env == "production":
        raise SystemExit("--preview-modes is development-only")
    registry = ModeRegistry(
        mode if mode.id == "daily" else replace(mode, status="live", entry_guard=None)
        for mode in build_registry()
    )
    return ModeRuntime(registry)


async def _grant_preview_modes(store: InMemoryStore, runtime) -> list[str]:
    user = await store.get_user_by_chat_id(DEV_CHAT_ID)
    granted = []
    for mode in runtime.registry:
        if grant_required(user, mode):
            await store.grant_mode(
                user["user_id"], mode.id, PREVIEW_OPERATOR, "local CLI preview"
            )
            granted.append(mode.id)
    return granted


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


async def run_cli(onboard: bool = False, preview_modes: bool = False):
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

    mode_runtime = _preview_runtime() if preview_modes else None
    handlers = BotHandlers(
        channel=channel,
        store=store,
        session_mgr=session_mgr,
        reminder_scheduler=reminder_scheduler,
        mode_runtime=mode_runtime,
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
        if mode_runtime is not None:
            granted = await _grant_preview_modes(store, mode_runtime)
            print(
                f"{_DIM}Preview Modes (development only, not live): {', '.join(granted)}. "
                f"Use /mode, /mode <id>, /daily.{_RESET}\n"
            )

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
                    async with serializer.hold(
                        await inbound_participant_key(store, channel.channel_id, DEV_CHAT_ID)
                    ):
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
            async with serializer.hold(
                await inbound_participant_key(store, channel.channel_id, DEV_CHAT_ID)
            ):
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
    parser.add_argument(
        "--preview-modes",
        action="store_true",
        help="Development only: enable Planned Modes for the seeded dev user",
    )
    args = parser.parse_args()

    # Handle Ctrl+C gracefully
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))

    asyncio.run(run_cli(onboard=args.onboard, preview_modes=args.preview_modes))


if __name__ == "__main__":
    main()
