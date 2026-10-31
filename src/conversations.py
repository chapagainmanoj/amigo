"""Channel-neutral conversation addressing, with provider mechanics delegated to channels."""

import asyncio
import logging
from functools import partial
from weakref import WeakKeyDictionary

from src.access import entitled
from src.channels.base import ConversationRef, endpoint_dict
from src.maintenance import run_isolated_steps

# Services used by handlers, grant operations and delivery share creation locks for one Store.
_CREATION_LOCKS: WeakKeyDictionary = WeakKeyDictionary()
logger = logging.getLogger(__name__)


class ModeConversationService:
    def __init__(self, store, channel):
        self.store = store
        self.channel = channel
        self._locks = _CREATION_LOCKS.setdefault(store, {})

    async def ensure(self, user: dict, mode_id: str = "daily", *, chat_id=None):
        if not self.channel.capabilities.threads:
            return None
        channel_id = self.channel.channel_id
        key = (user["user_id"], mode_id, channel_id)
        async with self._locks.setdefault(key, asyncio.Lock()):
            recipient = chat_id if chat_id is not None else await self.channel.recipient_for(user)
            current = await self.store.get_mode_conversation(*key)
            if current and current.get("closed_at") is None:
                ref = ConversationRef(channel_id, current["endpoint"])
                if await self.channel.recipient_matches(ref, recipient):
                    return ref
                await self.store.close_mode_conversation(*key)
            if recipient is None:
                raise ValueError("No linked messaging endpoint")
            created = await self.channel.create_conversation(recipient, mode_id.title())
            saved = await self.store.save_mode_conversation(
                user["user_id"], mode_id, channel_id, endpoint_dict(created)
            )
            if saved["endpoint"] != endpoint_dict(created):
                # Another process won the canonical insert. Retire only our new resource.
                try:
                    await self.channel.close_conversation(recipient, created)
                except Exception as error:
                    logger.warning("Conversation race cleanup failed: %s", type(error).__name__)
            return ConversationRef(channel_id, saved["endpoint"])

    async def ensure_by_chat(self, chat_id):
        user = await self.store.get_user_by_channel_identity(
            self.channel.channel_id, str(chat_id)
        )
        if user is None:
            return None
        return await self.ensure(user, chat_id=chat_id)

    async def select(self, user: dict, incoming: ConversationRef | None) -> str | None:
        """Unknown addressed conversations become Daily aliases; absent address uses commands."""
        if not self.channel.capabilities.threads or incoming is None:
            return None
        if incoming.channel != self.channel.channel_id:
            raise ValueError("Conversation belongs to another channel")
        mode = await self.store.get_mode_by_conversation(
            user["user_id"], incoming.channel, endpoint_dict(incoming)
        )
        if mode is None:
            await self.store.save_mode_conversation(
                user["user_id"], "daily", incoming.channel, endpoint_dict(incoming), alias=True
            )
            return "daily"
        return mode

    async def close_expired(self):
        """Close withdrawn specialized conversations while retaining participant history."""
        from src.agent.catalogue import build_registry

        registry = build_registry()
        for row in await self.store.list_mode_conversations():
            await run_isolated_steps([
                ("close_conversation_row", partial(self._close_unavailable, row, registry))
            ])

    async def _close_unavailable(self, row, registry):
        if row["channel"] != self.channel.channel_id or row.get("closed_at") is not None:
            return
        if row["mode_id"] == "daily":
            return
        from src.agent.modes import UnknownModeError

        try:
            mode = registry[row["mode_id"]]
        except UnknownModeError:
            mode = None
        user = await self.store.get_user_by_id(row["user_id"])
        # A failed entitlement lookup raises here and leaves the row open.
        allowed = mode is not None and user is not None and await entitled(self.store, user, mode)
        if allowed and mode.status == "live":
            return
        try:
            if user is not None:
                ref = ConversationRef(row["channel"], row["endpoint"])
                recipient = await self.channel.recipient_for(user)
                if recipient is not None and await self.channel.recipient_matches(ref, recipient):
                    await self.channel.close_conversation(recipient, ref)
        finally:
            # Revocation is canonical even when the provider rejects closing its linked topic.
            await self.store.close_mode_conversation(
                row["user_id"], row["mode_id"], row["channel"]
            )
