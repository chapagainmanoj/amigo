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

from src.agent.amigo import AmigoAgent
from src.bot.handlers import BotHandlers
from src.channels.cli import CLIChannel
from src.config import settings
from src.memory.memory_store import InMemoryStore
from src.memory.sessions import SessionManager
from src.providers.gemini import GeminiProvider
from src.scheduler.reminders import ReminderScheduler

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
    user = await store.create_user(DEV_CHAT_ID)
    await store.update_user(user["user_id"], {
        "name": "Dev",
        "timezone": DEV_TIMEZONE,
        "onboarding_step": 3,
        "onboarding_complete": True,
    })
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
                status_emoji = {"pending": "⏳", "done": "✅", "skipped": "⏭️", "deferred": "🔄"}
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
            print(f"{_DIM}Debug logging OFF{_RESET}\n")
        else:
            root.setLevel(logging.DEBUG)
            print(f"{_DIM}Debug logging ON{_RESET}\n")
        return True

    return False


async def run_cli(onboard: bool = False):
    """Main CLI loop — wire components and run an interactive chat session."""
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    _print_banner()

    # Wire components with in-memory store
    channel = CLIChannel()
    store = InMemoryStore()
    model = GeminiProvider(settings.default_model)
    agent = AmigoAgent(model=model, store=store)
    session_mgr = SessionManager(store)
    reminder_scheduler = ReminderScheduler(channel=channel, store=store)

    handlers = BotHandlers(
        agent=agent,
        channel=channel,
        store=store,
        session_mgr=session_mgr,
        reminder_scheduler=reminder_scheduler,
    )

    # Start the scheduler so reminders fire in the terminal
    reminder_scheduler.start()

    # Seed dev user unless --onboard flag is set
    if not onboard:
        await _seed_dev_user(store)
        print(f"{_DIM}Dev user seeded (name=Dev, tz={DEV_TIMEZONE}). Skipping onboarding.{_RESET}")
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
