"""Content-free Turn accounting and model framework instrumentation.

No exporter is installed here. Operators may install a global OTel provider. Framework spans
have content capture disabled; exception messages and status descriptions are also suppressed
because provider and Tool errors can quote participant content.
"""

import json
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from types import SimpleNamespace

from genai_prices import calc_price
from opentelemetry import trace
from opentelemetry.trace import Status
from pydantic_ai.models.instrumented import InstrumentationSettings

logger = logging.getLogger(__name__)
record_count: ContextVar[int] = ContextVar("turn_record_count", default=0)


@dataclass(frozen=True)
class TurnRecord:
    schema_version: int
    turn_id: str
    user_id: str
    mode_id: str
    requested_model: str | None
    answering_model: str | None
    fallback_used: bool
    tools: tuple[str, ...]
    outcome: str
    error_class: str | None
    latency_ms: float
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float | None


def estimated_cost(usage, model: str | None) -> float | None:
    if not isinstance(model, str) or not model:
        return None
    try:
        return float(calc_price(usage, model.split(":", 1)[-1]).total_price)
    except (LookupError, ValueError):
        return None


def emit_turn_record(record: TurnRecord) -> None:
    record_count.set(record_count.get() + 1)
    payload = asdict(record)
    logger.info(
        "turn_record %s", json.dumps(payload, sort_keys=True), extra={"turn_record": payload}
    )
    # Serialize only these explicitly allowed fields, never arbitrary framework state.
    with trace.get_tracer("amigo.turns").start_as_current_span(
        "amigo.turn", record_exception=False, set_status_on_exception=False
    ) as span:
        span.set_attributes({key: value for key, value in payload.items() if value is not None})


def _private_span(span):
    """OTel's synchronous protocol adapter; public application methods remain asynchronous."""

    def record_exception(exception, *args, **kwargs):
        span.add_event("exception", {"exception.type": type(exception).__name__})

    def set_status(status, description=None):
        span.set_status(Status(status.status_code if isinstance(status, Status) else status))

    def set_attribute(key, value):
        if _permitted_attribute(key):
            span.set_attribute(key, value)

    def set_attributes(attributes):
        span.set_attributes(_private_attributes(attributes))

    def add_event(name, attributes=None, timestamp=None):
        span.add_event(name, _private_attributes(attributes or {}), timestamp)

    return SimpleNamespace(
        end=span.end,
        get_span_context=span.get_span_context,
        is_recording=span.is_recording,
        set_attribute=set_attribute,
        set_attributes=set_attributes,
        add_event=add_event,
        update_name=span.update_name,
        record_exception=record_exception,
        set_status=set_status,
    )


def _permitted_attribute(key):
    return key in {
        "gen_ai.operation.name",
        "gen_ai.tool.name",
        "gen_ai.request.model",
        "gen_ai.response.model",
        "gen_ai.provider.name",
        "gen_ai.system",
        "exception.type",
    } or key.startswith(("gen_ai.usage.", "gen_ai.aggregated_usage."))


def _private_attributes(attributes):
    return {key: value for key, value in attributes.items() if _permitted_attribute(key)}


def framework_instrumentation() -> InstrumentationSettings:
    options = InstrumentationSettings(include_content=False, include_binary_content=False)
    tracer = options.tracer

    def start_span(*args, **kwargs):
        if "attributes" in kwargs:
            kwargs["attributes"] = _private_attributes(kwargs["attributes"] or {})
        return _private_span(tracer.start_span(*args, **kwargs))

    @contextmanager
    def start_as_current_span(*args, **kwargs):
        # Framework spans use the global provider but redact exception text at the source.
        span = start_span(*args, **kwargs)
        with trace.use_span(span, end_on_exit=True):
            yield span

    options.tracer = SimpleNamespace(
        start_span=start_span, start_as_current_span=start_as_current_span
    )
    return options
