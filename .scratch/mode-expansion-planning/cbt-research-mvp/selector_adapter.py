"""Offline typed selector boundary. No live provider, network client, logging, or credentials."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from research_engine import FIXTURES, MAX_QUESTIONS, QUESTIONS, VERSION, RunState


@dataclass(frozen=True)
class SelectionRequest:
    version: str
    fixture_id: str
    fictional_event: str
    consumed_responses: tuple[tuple[str, str], ...]
    asked: tuple[str, ...]
    eligible_ids: tuple[str, ...]
    remaining_requests: int


@dataclass(frozen=True)
class SelectionResult:
    status: Literal["ok", "blocked", "stopped", "timeout", "transport_failed", "invalid_response"]
    question_id: str | None = None


Transport = Callable[[SelectionRequest], Awaitable[object]]


class SelectionRejectedError(Exception):
    """Fixed error text only; never contains a transport response or exception body."""


async def eligible_question_ids(state: RunState) -> tuple[str, ...]:
    """Provisional deterministic eligibility, independent of any transport's output."""
    if (
        state.fixture_id not in FIXTURES
        or state.strategy not in {"fixed", "adaptive"}
        or state.status not in {"idle", "asking"}
        or not 0 <= state.selections <= MAX_QUESTIONS
        or len(state.asked) >= MAX_QUESTIONS
        or len(set(state.asked)) != len(state.asked)
        or not set(state.asked).issubset(QUESTIONS)
        or not set(state.answered).issubset(state.asked)
        or not set(state.skipped).issubset(state.asked)
        or set(state.answered) & set(state.skipped)
    ):
        return ()
    if not state.asked:
        return ("fact",)
    if state.asked[0] != "fact" or "takeaway" in state.asked:
        return ()
    if len(state.asked) == MAX_QUESTIONS - 1:
        return ("takeaway",)
    if state.strategy == "fixed":
        return (("fact", "thought", "alternative", "takeaway")[len(state.asked)],)
    if "thought" not in state.asked:
        ids = ("thought",)
        if (
            FIXTURES[state.fixture_id].branch == "clarify_fact"
            and "fact" in state.answered
            and "clarify_fact" not in state.asked
        ):
            ids += ("clarify_fact",)
        return ids
    ids = ("alternative",)
    if (
        FIXTURES[state.fixture_id].branch == "uncertainty"
        and {"fact", "thought"}.issubset(state.answered)
    ):
        ids += ("uncertainty",)
    return tuple(question_id for question_id in ids if question_id not in state.asked)


class OfflineSelectorAdapter:
    """Inject a mock async transport; one instance per run, max four dispatches, zero retries."""

    def __init__(self, transport: Transport, *, timeout_seconds: float = 1.0):
        if not 0 < timeout_seconds <= 1.0:
            raise ValueError("offline timeout must be positive and at most one second")
        self._transport = transport
        self._timeout = timeout_seconds
        self._requests = 0
        self._stopped = False
        self._pending: asyncio.Task | None = None
        self._select_lock = asyncio.Lock()

    async def stop(self) -> None:
        """Model-independent stop: prevent future dispatch and cancel an in-flight mock call."""
        self._stopped = True
        if self._pending is not None:
            self._pending.cancel()

    async def select(self, state: RunState) -> SelectionResult:
        async with self._select_lock:
            if self._stopped:
                return SelectionResult("stopped")
            ids = await eligible_question_ids(state)
            if not ids or self._requests >= MAX_QUESTIONS:
                return SelectionResult("blocked")
            fixture = FIXTURES[state.fixture_id]
            responses = dict(fixture.responses)
            request = SelectionRequest(
                version=VERSION,
                fixture_id=state.fixture_id,
                fictional_event=fixture.event,
                consumed_responses=tuple(
                    (question_id, responses[question_id])
                    for question_id in state.asked
                    if question_id in state.answered and question_id in responses
                ),
                asked=state.asked,
                eligible_ids=ids,
                remaining_requests=MAX_QUESTIONS - self._requests,
            )
            self._requests += 1  # Includes timeout, invalid output, and failed dispatch.
            try:
                self._pending = asyncio.ensure_future(self._transport(request))
                response = await asyncio.wait_for(self._pending, timeout=self._timeout)
            except TimeoutError:
                return SelectionResult("timeout")
            except asyncio.CancelledError:
                if not self._stopped:
                    raise
                return SelectionResult("stopped")
            except Exception:
                return SelectionResult("transport_failed")
            finally:
                self._pending = None
            if self._stopped:
                return SelectionResult("stopped")
            # Do not parse prose, coerce IDs, retain output, or expose extra fields.
            if (
                type(response) is not dict
                or set(response) != {"question_id"}
                or not isinstance(response["question_id"], str)
                or response["question_id"] not in ids
            ):
                return SelectionResult("invalid_response")
            return SelectionResult("ok", response["question_id"])

    async def choose(self, state: RunState) -> str:
        """Duck-typed engine provider; failure becomes a fixed content-free exception."""
        result = await self.select(state)
        if result.status != "ok":
            raise SelectionRejectedError("offline selection did not succeed")
        return result.question_id
