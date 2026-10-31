"""Inbound update claiming and participant-scoped Turn serialization."""

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Literal

from src.channels.base import Recipient

logger = logging.getLogger(__name__)

UpdateOutcome = Literal["completed", "duplicate", "failed"]


@dataclass(frozen=True)
class UpdateResult:
    """Safe webhook outcome for one inbound delivery."""

    outcome: UpdateOutcome
    update_id: str | int


def participant_key(user: dict) -> str:
    """One lock per participant, whichever channel their Turn arrives on (ADR 0004)."""
    return f"user:{user['user_id']}"


async def inbound_participant_key(store, channel_id: str, recipient: Recipient) -> str:
    """Lock key for an inbound update; unpaired senders lock on their channel address."""
    user = await store.get_user_by_channel_identity(channel_id, str(recipient))
    return participant_key(user) if user else f"{channel_id}:{recipient}"


class ParticipantTurnSerializer:
    """Serialize Turns per participant across channels within the beta web process."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._registry_lock = asyncio.Lock()

    @asynccontextmanager
    async def hold(self, key: str) -> AsyncIterator[None]:
        """Hold the stable lock for one participant key while a Turn executes."""
        async with self._registry_lock:
            lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            yield


class ChannelUpdateCoordinator:
    """Claim once, acknowledge safely, serialize, and retain processing outcome."""

    def __init__(
        self,
        store,
        serializer: ParticipantTurnSerializer | None = None,
        *,
        channel_id: str = "telegram",
    ) -> None:
        self.store = store
        self.serializer = serializer or ParticipantTurnSerializer()
        self.channel_id = channel_id

    async def run(
        self,
        *,
        update_id: str | int,
        chat_id: Recipient,
        update_kind: str,
        process: Callable[[], Awaitable[None]],
        acknowledge: Callable[[], Awaitable[None]] | None = None,
        acknowledge_first: bool = False,
    ) -> UpdateResult:
        """Process only the first delivery and make any internal failure inspectable.

        `acknowledge_first` is for providers with a hard acknowledgement deadline (Discord: three
        seconds), which never redeliver an interaction, so acknowledging before the claim is safe.
        """
        if acknowledge is not None and acknowledge_first:
            await acknowledge()
        claim = await self.store.claim_channel_update(
            self.channel_id, str(update_id), str(chat_id), update_kind
        )
        if acknowledge is not None and not acknowledge_first:
            await acknowledge()
        if not claim["claimed"]:
            logger.info(
                "Acknowledged duplicate update channel=%s update_id=%s status=%s",
                self.channel_id,
                update_id,
                claim["status"],
            )
            return UpdateResult("duplicate", update_id)

        try:
            async with self._hold_inbound(chat_id):
                await process()
        except Exception as exc:
            # Includes a failed participant lookup: the claim must never stay "processing",
            # or the provider's redelivery would be acknowledged as a duplicate and lost.
            await self.store.finish_channel_update(
                self.channel_id,
                str(update_id),
                status="failed",
                failure_code=type(exc).__name__,
            )
            logger.exception("Update failed channel=%s update_id=%s", self.channel_id, update_id)
            return UpdateResult("failed", update_id)

        await self.store.finish_channel_update(
            self.channel_id, str(update_id), status="completed"
        )
        return UpdateResult("completed", update_id)

    @asynccontextmanager
    async def _hold_inbound(self, chat_id: Recipient) -> AsyncIterator[None]:
        """Address lock first, then the participant lock, always in that order.

        A first-contact Pairing Turn runs before its sender is linked; the address lock keeps the
        sender's next message behind it even though that message resolves to the participant.
        Other holders take only participant locks, so the fixed order cannot deadlock.
        """
        async with self.serializer.hold(f"{self.channel_id}:{chat_id}"):
            user = await self.store.get_user_by_channel_identity(self.channel_id, str(chat_id))
            if user is None:
                yield
                return
            async with self.serializer.hold(participant_key(user)):
                yield
