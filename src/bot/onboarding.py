"""Onboarding state machine — multi-turn, resumable.

Steps:
  0 → not started
  1 → ask name (required)
  2 → confirm timezone (required, auto-detected)
  3 → done → first task planning

State tracked via onboarding_step INT on user_profiles.
If user abandons mid-flow, resumes at last incomplete step on next message.
"""

import logging

from src.bot.keyboards import confirm_timezone_keyboard
from src.channels.base import MessageChannel
from src.memory.store import MemoryStore

logger = logging.getLogger(__name__)

# Default timezone inferred from locale (Phase 1a: hardcoded for Nepal)
DEFAULT_TIMEZONE = "Asia/Kathmandu"

# Common casual inputs → IANA timezone names
TIMEZONE_ALIASES = {
    "nepal": "Asia/Kathmandu",
    "kathmandu": "Asia/Kathmandu",
    "india": "Asia/Kolkata",
    "kolkata": "Asia/Kolkata",
    "mumbai": "Asia/Kolkata",
    "toronto": "America/Toronto",
    "new york": "America/New_York",
    "london": "Europe/London",
    "dubai": "Asia/Dubai",
    "tokyo": "Asia/Tokyo",
    "sydney": "Australia/Sydney",
}


async def handle_onboarding(
    user: dict,
    message: str,
    channel: MessageChannel,
    store: MemoryStore,
    chat_id: int,
    callback_data: str | None = None,
) -> bool:
    """Process one step of onboarding. Returns True if onboarding is still in progress.

    Called by the main handler for every message until onboarding_complete = True.
    """
    step = user.get("onboarding_step", 0)
    user_id = user["user_id"]

    # ── Step 0: Welcome → ask name ──
    if step == 0:
        await channel.send_message(
            chat_id,
            "Hey! I'm Amigo, an AI accountability companion for everyday tasks. 👋\n\n"
            "What should I call you?",
        )
        await store.update_user(user_id, {"onboarding_step": 1})
        return True

    # ── Step 1: Receive name → confirm timezone ──
    if step == 1:
        name = message.strip()

        # Users often reply with a greeting instead of their name
        greetings = {
            "hi", "hello", "hey", "yo", "sup", "hola", "namaste",
            "hi!", "hello!", "hey!", "yo!",
        }
        if name.lower() in greetings:
            await channel.send_message(
                chat_id,
                f"{name}! 😄 What's your name though? What should I call you?",
            )
            return True

        await store.update_user(user_id, {"name": name, "onboarding_step": 2})
        await channel.send_message(
            chat_id,
            f"Got it, {name}! I'm guessing you're in {DEFAULT_TIMEZONE} — right?",
            buttons=confirm_timezone_keyboard(),
        )
        return True

    # ── Step 2: Timezone confirmation → done ──
    if step == 2:
        if callback_data == "tz:confirm":
            tz = DEFAULT_TIMEZONE
        elif callback_data == "tz:manual":
            await channel.send_message(
                chat_id,
                "What timezone are you in? (e.g., Asia/Kolkata, America/New_York)",
            )
            # Stay on step 2, next text message will be treated as timezone
            return True
        elif message.strip():
            # Manual timezone entry — validate
            tz = message.strip()
            tz = TIMEZONE_ALIASES.get(tz.lower(), tz)
            try:
                from zoneinfo import ZoneInfo
                if "/" not in tz and tz != "UTC":
                    raise KeyError(tz)
                ZoneInfo(tz)
            except (KeyError, Exception):
                await channel.send_message(
                    chat_id,
                    f"\"{tz}\" doesn't look right. Use an IANA timezone like "
                    "America/Toronto or Asia/Kathmandu.",
                )
                return True
        else:
            return True

        # Timezone confirmed — finish onboarding
        name = user.get("name") or "friend"
        await store.update_user(user_id, {
            "timezone": tz,
            "onboarding_step": 3,
            "onboarding_complete": True,
        })
        await channel.send_message(
            chat_id,
            f"All set, {name}! 🎉\n\n"
            "Tell me one thing you're planning to do today and when you'd like a reminder.",
        )
        return False  # Onboarding complete, next message goes to regular handler

    return False
