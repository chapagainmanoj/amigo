"""Participant access tiers: owner-listed full access, everyone else a bounded trial.

ALLOWED_TELEGRAM_CHAT_IDS lists owner-approved full-access chats. In the allowlist posture it
also blocks everyone else; in the registered posture everyone else gets the trial. Full access
is an owner decision, like a model pin: it never comes from participant input.
"""

import logging

from src.channels.base import Recipient
from src.runtime_config import UnsafeProductionConfigurationError, parse_allowed_chat_ids

logger = logging.getLogger(__name__)

# A Mode with this entitlement is for full-access chats, or anyone holding an operator grant.
FULL_ACCESS = "full_access"


def is_full_access(chat_id: int | str | None) -> bool:
    from src.config import settings

    if chat_id is None:
        return False
    try:
        allowed = parse_allowed_chat_ids(settings.allowed_telegram_chat_ids)
    except UnsafeProductionConfigurationError:
        logger.error("Invalid ALLOWED_TELEGRAM_CHAT_IDS; no chat has full access")
        return False
    try:
        return int(chat_id) in allowed
    except (TypeError, ValueError):
        return False


def is_full_access_user(user: dict) -> bool:
    return is_full_access(user.get("telegram_chat_id"))


def grant_required(user: dict, mode) -> bool:
    """Whether opening this Mode for this participant needs an active operator grant."""
    if mode.entitlement == "grant":
        return True
    return mode.entitlement == FULL_ACCESS and not is_full_access_user(user)


async def entitled(store, user: dict, mode) -> bool:
    if mode.entitlement not in {"activated", "grant", FULL_ACCESS}:
        return False
    if not grant_required(user, mode):
        return True
    return bool(await store.get_active_mode_grant(user["user_id"], mode.id))


def trial_finished_message(chat_id: Recipient) -> str:
    from src.config import settings

    return (
        "Your free Amigo trial has finished. For full access, contact us at "
        f"{settings.trial_contact} and quote reference {chat_id}. "
        "Your Tasks and Reminders keep working."
    )


def help_message() -> str:
    from src.config import settings

    return (
        "Tell me what you need to do, e.g. \"remind me to call mom at 6\" or "
        "\"what's on today\".\n\n"
        "/mode – see and switch Modes\n"
        "/daily – back to Daily\n"
        "/program – your Coach program\n"
        "/memory – what I remember\n"
        "/feedback <text> – tell the team something\n\n"
        f"Full guide: {settings.guide_url}"
    )


async def trial_exhausted(store, user: dict) -> bool:
    """True once a trial participant has used their message allowance."""
    from src.config import settings

    if is_full_access_user(user):
        return False
    used = await store.count_participant_messages(user["user_id"])
    return used >= settings.trial_message_limit
