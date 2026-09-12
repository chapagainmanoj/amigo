"""Canonical Dashboard-first Activation Journey commands."""

import hashlib
import json
from datetime import datetime

from src.activation import ACTIVATION_TEST_TASK_TITLE, validate_test_time
from src.commands.base import CommandContext
from src.utils import Clock, default_clock


class CreateActivationTestCommand:
    """Atomically create or retry the owned private Activation test Reminder."""

    def __init__(self, store, clock: Clock = default_clock):
        self.store = store
        self.clock = clock

    async def run(
        self,
        context: CommandContext,
        *,
        scheduled_at: datetime,
        timezone: str,
        retry: bool = False,
    ) -> dict:
        schedule = validate_test_time(scheduled_at, timezone, self.clock.utc_now())
        payload = {
            "command": "create_activation_test",
            "surface": context.surface,
            "scheduled_at": schedule["scheduled_time"],
            "timezone": timezone,
            "retry": retry,
        }
        payload_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return await self.store.create_activation_test_command(
            user_id=context.actor_user_id,
            idempotency_key=context.idempotency_key,
            payload_hash=payload_hash,
            title=ACTIVATION_TEST_TASK_TITLE,
            retry=retry,
            **schedule,
        )
