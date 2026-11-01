"""Participant access tiers: owner-listed full access, everyone else a bounded trial.

ALLOWED_TELEGRAM_CHAT_IDS lists owner-approved full-access chats. In the allowlist posture it
also blocks everyone else; in the registered posture everyone else gets the trial. Full access
is an owner decision, like a model pin: it never comes from participant input.
"""

import logging

from src.channels.base import Recipient
from src.runtime_config import (
    ACCESS_CLOSED,
    ACCESS_OPEN,
    ACCESS_REGISTERED,
    UnsafeProductionConfigurationError,
    parse_allowed_chat_ids,
)

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


# Apps every linked participant may use. Telegram is the first app (Activation); the CLI is local.
OPEN_CHANNELS = frozenset({"telegram", "cli"})


def may_use_channel(user: dict | None, channel_id: str) -> bool:
    """Whether this participant may chat, pair or be reached on this messaging app.

    Other apps are only for linked dashboard accounts with full access (owner decision 31 Oct
    2026), until the privacy promise and decision 04 cover their providers. The one rule for the
    bot, Pairing, the dashboard and proactive delivery; Activation and access postures stay
    with their callers.
    """
    if not user:
        return False
    if channel_id in OPEN_CHANNELS:
        return True
    return bool(user.get("supabase_auth_id")) and is_full_access_user(user)


async def admitted(
    store, channel_id: str, chat_id: Recipient, *, pairing_attempt: bool = False
) -> bool:
    """Whether this chat address may talk to the bot under the configured ACCESS_MODE.

    The one access-posture rule for every messaging app's handler: closed admits nobody; other
    apps follow ``may_use_channel`` in every posture; open admits everyone; registered admits
    Pairing attempts and linked dashboard accounts; allowlist admits the listed Telegram chats.
    Pairing attempts are admitted here because Pairing applies the rule to the token's account.
    """
    from src.config import settings

    if settings.access_mode == ACCESS_CLOSED:
        return False
    if channel_id not in OPEN_CHANNELS:
        if pairing_attempt:
            return True
        return may_use_channel(await _participant(store, channel_id, chat_id), channel_id)
    if settings.access_mode == ACCESS_OPEN:
        return True
    if settings.access_mode in ACCESS_REGISTERED:
        if pairing_attempt:
            return True
        user = await _participant(store, channel_id, chat_id)
        return bool(user and user.get("supabase_auth_id"))

    try:
        allowed_ids = parse_allowed_chat_ids(settings.allowed_telegram_chat_ids)
    except UnsafeProductionConfigurationError:
        logger.error("Invalid ALLOWED_TELEGRAM_CHAT_IDS; denying Telegram access")
        return False
    return chat_id in allowed_ids


async def _participant(store, channel_id: str, chat_id: Recipient) -> dict | None:
    """The participant this channel address is linked to (ADR 0004)."""
    return await store.get_user_by_channel_identity(channel_id, str(chat_id))


async def activation_completed(store, user: dict | None) -> bool:
    """Whether this participant's dashboard account has completed Activation.

    The one check behind every "Activation first" gate: bot, Pairing, proactive delivery,
    handoff notices and the dashboard API.
    """
    auth_id = (user or {}).get("supabase_auth_id")
    if not auth_id:
        return False
    return (await store.get_activation_state(auth_id)).get("completed") is True


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
