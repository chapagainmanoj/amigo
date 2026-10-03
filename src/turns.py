"""Application orchestration for one participant Turn.

The model runtime plans and invokes its authorized Tools. This layer owns Session transcript I/O
and friendly failure mapping, keeping direct side effects out of ``src/agent/``.
"""

import logging
import time
from typing import Any

from src.agent.modes import ModeDefinition, ModeUnavailableError
from src.agent.runtime import (
    FAILURE_REPLY,
    ModeRunResult,
    ModeRuntime,
    SessionMessage,
    default_runtime,
)
from src.memory.context import ContextBuilder
from src.telemetry import TurnRecord, emit_turn_record, record_count
from src.tools.context import ToolContext

logger = logging.getLogger(__name__)


class SessionTurnOrchestrator:
    """Authorize, persist, and execute one Session-scoped participant Turn."""

    def __init__(self, runtime: ModeRuntime):
        self.runtime = runtime

    async def run_turn(
        self,
        context: ToolContext,
        text: str,
        *,
        requested_mode: str | None = None,
        model: Any | None = None,
    ) -> ModeRunResult:
        """Run a Turn with transcript persistence, propagating execution failures."""
        started = time.perf_counter()
        initial_count = record_count.get()
        try:
            mode = await self.runtime.resolve(context, requested_mode)
            return await self._run_authorized(mode, context, text, model=model)
        except Exception as error:
            if record_count.get() == initial_count:
                _record_unexecuted(context, error, started)
            raise

    async def handle_turn(
        self, context: ToolContext, text: str, *, requested_mode: str | None = None
    ) -> str:
        """Run one Turn and always return something the participant can read."""
        started = time.perf_counter()
        initial_count = record_count.get()
        try:
            mode = await self.runtime.resolve(context, requested_mode)
        except ModeUnavailableError as refusal:
            _record_unexecuted(context, refusal, started)
            return refusal.participant_message
        except Exception as error:
            _record_unexecuted(context, error, started)
            logger.error("Mode resolution failed: %s", type(error).__name__)
            return FAILURE_REPLY

        try:
            result = await self._run_authorized(mode, context, text, model=None)
            return result.output
        except Exception as error:
            if record_count.get() == initial_count:
                _record_unexecuted(context, error, started)
            logger.error("Agent run failed: %s", type(error).__name__)
            await context.store.add_message(
                context.session_id, context.user["user_id"], "assistant", FAILURE_REPLY
            )
            return FAILURE_REPLY

    async def _run_authorized(
        self,
        mode: ModeDefinition,
        context: ToolContext,
        text: str,
        *,
        model: Any | None,
    ) -> ModeRunResult:
        user_id = context.user["user_id"]
        await context.store.add_message(context.session_id, user_id, "user", text)
        stored = await ContextBuilder(context.store).get_truncated_messages(context.session_id)
        history = tuple(
            SessionMessage(role=message["role"], content=message["content"])
            for message in stored[:-1]
        )
        result = await self.runtime.run_mode(
            mode,
            context,
            text,
            model=model,
            history=history,
        )
        await context.store.add_message(context.session_id, user_id, "assistant", result.output)
        return result


default_turn_orchestrator = SessionTurnOrchestrator(default_runtime)


def _record_unexecuted(context, error, started):
    refusal = isinstance(error, ModeUnavailableError)
    mode_id = error.mode_id if refusal and error.reason != "unknown" else "unknown"
    emit_turn_record(
        TurnRecord(
            schema_version=1,
            turn_id=context.turn_id,
            user_id=context.user["user_id"],
            mode_id=mode_id,
            requested_model=None,
            answering_model=None,
            fallback_used=False,
            tools=(),
            outcome="refused" if refusal else "failed",
            error_class=type(error).__name__,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            input_tokens=0,
            output_tokens=0,
            estimated_cost_usd=None,
        )
    )
