"""Live Gemini adapter for the approved fixed-fiction batch; never accepts personal input."""

import asyncio
import json
import re
import time
from dataclasses import dataclass
from typing import Literal, Protocol

from google import genai
from google.genai import types

from research_engine import FIXTURES, MAX_QUESTIONS, VERSION, RunState
from selector_adapter import SelectionRejectedError, SelectionRequest, eligible_question_ids

MODEL = "gemini-3.5-flash"
MAX_BATCH_REQUESTS = 8
MAX_RUN_REQUESTS = MAX_QUESTIONS
MAX_OUTPUT_TOKENS = 64
REQUEST_TIMEOUT_SECONDS = 20.0
_SAFE_MODEL = re.compile(r"^gemini-[a-z0-9.-]{1,64}$")


class AsyncModels(Protocol):
    async def generate_content(self, *, model: str, contents: str, config: object) -> object: ...


class AsyncClient(Protocol):
    models: AsyncModels


@dataclass(frozen=True)
class RequestMetric:
    request_index: int
    fixture_id: str
    status: Literal[
        "ok", "stopped", "timeout", "provider_failed", "invalid_response", "budget_exhausted"
    ]
    selected_id: str | None = None
    requested_model: str = MODEL
    observed_model: str | None = None
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    thought_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: float = 0.0
    http_status: int | None = None


class SharedRequestBudget:
    """One process-local cap shared by both fictional runs in the batch."""

    def __init__(self, maximum: int = MAX_BATCH_REQUESTS):
        if maximum != MAX_BATCH_REQUESTS:
            raise ValueError("the approved live batch budget is exactly eight requests")
        self.maximum = maximum
        self.used = 0
        self._lock = asyncio.Lock()

    async def claim(self) -> int | None:
        """Count a dispatch before it starts, including failures and cancellation."""
        async with self._lock:
            if self.used >= self.maximum:
                return None
            self.used += 1
            return self.used


def google_http_options() -> types.HttpOptions:
    """Pin the SDK request timeout and disable its automatic transport retries."""
    return types.HttpOptions(
        api_version="v1beta",
        timeout=int(REQUEST_TIMEOUT_SECONDS * 1000),
        retry_options=types.HttpRetryOptions(attempts=1),
        async_client_args={"trust_env": False},
    )


def build_google_client(api_key: str) -> genai.Client:
    """Construct only after the runner's explicit opt-in and credential checks."""
    if not api_key or not api_key.strip():
        raise ValueError("a local Google API credential is required")
    return genai.Client(api_key=api_key, http_options=google_http_options())


def _selection_config(eligible_ids: tuple[str, ...]) -> types.GenerateContentConfig:
    schema = {
        "type": "object",
        "properties": {
            "question_id": {
                "type": "string",
                "enum": list(eligible_ids),
                "description": "The next eligible fictional question identifier.",
            }
        },
        "required": ["question_id"],
        "additionalProperties": False,
    }
    return types.GenerateContentConfig(
        temperature=0,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        response_mime_type="application/json",
        response_schema=schema,
        tools=[],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )


def _prompt(request: SelectionRequest) -> str:
    payload = {
        "version": request.version,
        "fixture_id": request.fixture_id,
        "fictional_event": request.fictional_event,
        "consumed_fictional_responses": [
            {"question_id": question_id, "response": response}
            for question_id, response in request.consumed_responses
        ],
        "asked_question_ids": list(request.asked),
        "eligible_question_ids": list(request.eligible_ids),
        "remaining_run_requests": request.remaining_requests,
    }
    return (
        "Select exactly one next question ID for this fixed fictional research fixture. "
        "Return only the schema object. Do not provide advice, diagnosis, treatment, rationale, "
        "question wording, a task, a tool call, or any additional field. The eligible list is "
        "authoritative.\n"
        + json.dumps(payload, sort_keys=True, separators=(",", ":"))
    )


def _safe_int(value: object) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _safe_model(value: object) -> str | None:
    return value if isinstance(value, str) and _SAFE_MODEL.fullmatch(value) else None


def _safe_status(error: Exception) -> int | None:
    value = getattr(error, "code", None)
    return value if type(value) is int and 100 <= value <= 599 else None


class GeminiSelectorProvider:
    """One selector per fictional run: four requests, no retries, no fallback, no raw output."""

    def __init__(
        self,
        client: AsyncClient,
        budget: SharedRequestBudget,
        *,
        timeout_seconds: float = REQUEST_TIMEOUT_SECONDS,
    ):
        if not 0 < timeout_seconds <= REQUEST_TIMEOUT_SECONDS:
            raise ValueError("live timeout must be positive and at most twenty seconds")
        self._client = client
        self._budget = budget
        self._timeout = timeout_seconds
        self._requests = 0
        self._stopped = False
        self._pending: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self.metrics: list[RequestMetric] = []

    async def stop(self) -> None:
        """Prevent another dispatch and discard a response from an in-flight request."""
        self._stopped = True
        if self._pending is not None:
            self._pending.cancel()

    async def choose(self, state: RunState) -> str:
        async with self._lock:
            if self._stopped:
                raise SelectionRejectedError("live selection stopped")
            eligible_ids = await eligible_question_ids(state)
            if not eligible_ids or self._requests >= MAX_RUN_REQUESTS:
                await self._record(state, "budget_exhausted", 0.0)
                raise SelectionRejectedError("live selection unavailable")
            request_index = await self._budget.claim()
            if request_index is None:
                await self._record(state, "budget_exhausted", 0.0)
                raise SelectionRejectedError("live selection unavailable")

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
                eligible_ids=eligible_ids,
                remaining_requests=MAX_RUN_REQUESTS - self._requests,
            )
            self._requests += 1
            started = time.perf_counter()
            try:
                self._pending = asyncio.create_task(
                    self._client.models.generate_content(
                        model=MODEL,
                        contents=_prompt(request),
                        config=_selection_config(eligible_ids),
                    )
                )
                response = await asyncio.wait_for(self._pending, timeout=self._timeout)
            except TimeoutError:
                await self._record(
                    state, "timeout", _elapsed_ms(started), request_index=request_index
                )
                raise SelectionRejectedError("live selection timed out") from None
            except asyncio.CancelledError:
                if not self._stopped:
                    raise
                await self._record(
                    state, "stopped", _elapsed_ms(started), request_index=request_index
                )
                raise SelectionRejectedError("live selection stopped") from None
            except Exception as error:
                await self._record(
                    state,
                    "provider_failed",
                    _elapsed_ms(started),
                    request_index=request_index,
                    http_status=_safe_status(error),
                )
                raise SelectionRejectedError("live selection failed") from None
            finally:
                self._pending = None

            if self._stopped:
                await self._record(
                    state, "stopped", _elapsed_ms(started), request_index=request_index
                )
                raise SelectionRejectedError("live selection stopped")
            parsed = getattr(response, "parsed", None)
            if (
                type(parsed) is not dict
                or set(parsed) != {"question_id"}
                or not isinstance(parsed["question_id"], str)
                or parsed["question_id"] not in eligible_ids
            ):
                await self._record(
                    state,
                    "invalid_response",
                    _elapsed_ms(started),
                    response=response,
                    request_index=request_index,
                )
                raise SelectionRejectedError("live selection returned invalid output")
            selected = parsed["question_id"]
            await self._record(
                state,
                "ok",
                _elapsed_ms(started),
                response=response,
                selected_id=selected,
                request_index=request_index,
            )
            return selected

    async def _record(
        self,
        state: RunState,
        status: RequestMetric.__annotations__["status"],
        latency_ms: float,
        *,
        response: object | None = None,
        selected_id: str | None = None,
        request_index: int | None = None,
        http_status: int | None = None,
    ) -> None:
        usage = getattr(response, "usage_metadata", None)
        self.metrics.append(
            RequestMetric(
                request_index=request_index or self._budget.used,
                fixture_id=state.fixture_id if state.fixture_id in FIXTURES else "unknown",
                status=status,
                selected_id=selected_id,
                observed_model=_safe_model(getattr(response, "model_version", None)),
                prompt_tokens=_safe_int(getattr(usage, "prompt_token_count", None)),
                output_tokens=_safe_int(getattr(usage, "candidates_token_count", None)),
                thought_tokens=_safe_int(getattr(usage, "thoughts_token_count", None)),
                total_tokens=_safe_int(getattr(usage, "total_token_count", None)),
                latency_ms=round(latency_ms, 2),
                http_status=http_status,
            )
        )


def _elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000
