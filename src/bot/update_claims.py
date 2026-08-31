"""Telegram update claiming and participant-scoped Turn serialization."""

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

UpdateOutcome = Literal["completed", "duplicate", "failed"]


@dataclass(frozen=True)
class UpdateResult:
    """Safe webhook outcome for one Telegram delivery."""

    outcome: UpdateOutcome
    update_id: int


class ParticipantTurnSerializer:
    """Serialize Turns per Telegram participant within the beta web process."""

    def __init__(self) -> None:
        self._locks: dict[int, asyncio.Lock] = {}
        self._registry_lock = asyncio.Lock()

    @asynccontextmanager
    async def hold(self, chat_id: int) -> AsyncIterator[None]:
        """Hold the stable lock for one participant while a Turn executes."""
        async with self._registry_lock:
            lock = self._locks.setdefault(chat_id, asyncio.Lock())
        async with lock:
            yield


class TelegramUpdateCoordinator:
    """Claim once, acknowledge safely, serialize, and retain processing outcome."""

    def __init__(self, store, serializer: ParticipantTurnSerializer | None = None) -> None:
        self.store = store
        self.serializer = serializer or ParticipantTurnSerializer()

    async def run(
        self,
        *,
        update_id: int,
        chat_id: int,
        update_kind: str,
        process: Callable[[], Awaitable[None]],
        acknowledge: Callable[[], Awaitable[None]] | None = None,
    ) -> UpdateResult:
        """Process only the first delivery and make any internal failure inspectable."""
        claim = await self.store.claim_telegram_update(update_id, chat_id, update_kind)
        if acknowledge is not None:
            await acknowledge()
        if not claim["claimed"]:
            logger.info(
                "Acknowledged duplicate Telegram update update_id=%s status=%s",
                update_id,
                claim["status"],
            )
            return UpdateResult("duplicate", update_id)

        async with self.serializer.hold(chat_id):
            try:
                await process()
            except Exception as exc:
                await self.store.finish_telegram_update(
                    update_id,
                    status="failed",
                    failure_code=type(exc).__name__,
                )
                logger.exception("Telegram update failed update_id=%s", update_id)
                return UpdateResult("failed", update_id)

            await self.store.finish_telegram_update(update_id, status="completed")
            return UpdateResult("completed", update_id)
