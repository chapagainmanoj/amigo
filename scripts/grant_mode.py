#!/usr/bin/env python3
"""Grant or revoke operator-managed Mode access and maintain its conversation."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


async def apply_mode_access(
    store,
    channel,
    user: dict,
    mode_id: str,
    operator: str,
    reason: str,
    *,
    revoke: bool = False,
    expires_at: datetime | None = None,
    registry=None,
) -> dict:
    """Store owns grant TTL/cap enforcement; channel addressing remains in its service."""
    from src.agent.catalogue import build_registry
    from src.conversations import ModeConversationService

    mode = await (registry or build_registry()).get(mode_id)
    if not operator.strip() or not reason.strip() or mode_id == "daily":
        raise ValueError("An operator, reason and specialized Mode are required")
    if expires_at is not None and expires_at.utcoffset() is None:
        raise ValueError("Expiry must include a timezone offset")
    if not revoke and mode.status != "live":
        raise ValueError("Mode must be live before granting access")
    service = ModeConversationService(store, channel)
    if revoke:
        result = await store.revoke_mode_grant(user["user_id"], mode_id, operator, reason)
        await service.close_expired()
    else:
        result = await store.grant_mode(
            user["user_id"], mode_id, operator, reason, expires_at,
        )
        if result["status"] in {"granted", "already_active"}:
            await service.ensure(user, mode_id)
    return result


async def main(argv=None) -> int:
    from src.channels.telegram import TelegramChannel
    from src.config import settings
    from src.memory.store import MemoryStore
    from src.runtime_config import is_production
    from src.schema import EXPECTED_SCHEMA_VERSION

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("grant", "revoke"))
    parser.add_argument("--chat-id", required=True, type=int)
    parser.add_argument("--mode", required=True)
    parser.add_argument("--operator", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--expires-at", type=datetime.fromisoformat)
    args = parser.parse_args(argv)
    logging.getLogger("httpx").disabled = True
    logging.getLogger("httpcore").disabled = True
    try:
        if args.chat_id <= 0:
            raise ValueError("Private chat required")
        store = MemoryStore()
        await store.connect()
        await store.verify_schema_version(EXPECTED_SCHEMA_VERSION)
        user = await store.get_user_by_chat_id(args.chat_id)
        if not user:
            raise ValueError("Participant not found")
        channel = TelegramChannel()
        await channel.initialize(production=is_production(settings))
        result = await apply_mode_access(
            store, channel, user, args.mode, args.operator, args.reason,
            revoke=args.action == "revoke", expires_at=args.expires_at,
        )
        print(json.dumps({"mode_id": args.mode, "status": result["status"]}))
        success = result["status"] in {"granted", "already_active", "revoked", "not_active"}
        return 0 if success else 1
    except Exception as error:
        logging.getLogger(__name__).error("Mode access operation failed: %s", type(error).__name__)
        print("Mode access operation failed; inspect canonical access before retrying.")
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
