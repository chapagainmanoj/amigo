"""Model policy and privacy observed through the participant Turn seam."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage

from scripts.check_gate_a_evidence import check_evidence
from scripts.run_gate_a_eval import _run_execution
from scripts.run_gate_a_eval import run as run_provider_eval
from scripts.run_mode_deterministic_eval import run as run_deterministic
from src.agent.catalogue import DAILY, build_registry
from src.agent.modes import ModelPolicy
from src.agent.registry import ModeRegistry
from src.agent.runtime import FAILURE_REPLY, ModeRuntime
from src.evaluation.gate_a import dependency_versions, load_suite
from src.evaluation.model_policy import fallback_currency, require_evaluated_fallback
from src.turns import SessionTurnOrchestrator
from tests.fakes import FakeStore
from tests.gate_a_fixtures import passing_gate_a_evidence
from tests.test_modes import _deliver, _journal, _participant, _runtime_for


def _record(caplog):
    records = [r.turn_record for r in caplog.records if hasattr(r, "turn_record")]
    assert len(records) == 1
    return records[0]


def _policy_runtime():
    # Provider requests are scripted; evidence enforcement is covered separately with an actual
    # full artifact. No production Mode gains a fallback from this test fixture.
    mode = replace(DAILY, model=ModelPolicy("google:gemini-2.5-flash", "google:gemini-2.0-flash"))
    with patch("src.agent.registry.require_evaluated_fallback"):
        return ModeRuntime(ModeRegistry((mode,)))


async def _turn(primary, fallback, caplog, *, runtime=None):
    store = FakeStore()
    await _participant(store, 1001)
    runtime = runtime or _policy_runtime()
    with caplog.at_level("INFO"):
        async with runtime.override(model=FunctionModel(primary), fallback=FunctionModel(fallback)):
            channel = await _deliver(store, "Add my task", 1001, runtime)
    return store, channel, _record(caplog)


async def test_provider_failure_uses_exactly_one_fallback_request_and_persists_reply(caplog):
    calls = []

    def primary(messages, info):
        calls.append("primary")
        raise ModelHTTPError(503, "gemini-2.5-flash")

    def fallback(messages, info):
        calls.append("fallback")
        return ModelResponse(parts=[TextPart("We can continue.")])

    store, channel, record = await _turn(primary, fallback, caplog)
    assert calls == ["primary", "primary", "fallback"]
    assert channel.last_text == "We can continue."
    assert [m["content"] for m in store.messages] == ["Add my task", "We can continue."]
    assert record["fallback_used"] is True
    assert record["outcome"] == "ok"
    assert record["requested_model"] == "google:gemini-2.5-flash"


async def test_failure_after_tool_dispatch_never_repeats_side_effect(caplog):
    calls = []

    def primary(messages, info):
        calls.append("primary")
        if len(calls) == 1:
            return ModelResponse(parts=[ToolCallPart("create_task", {"title": "One task"})])
        raise ModelHTTPError(503, "gemini-2.5-flash")

    def fallback(messages, info):
        calls.append("fallback")
        return ModelResponse(parts=[TextPart("bad fallback")])

    store, channel, record = await _turn(primary, fallback, caplog)
    assert calls == ["primary", "primary"]
    assert [t["title"] for t in store.tasks] == ["One task"]
    assert channel.last_text == FAILURE_REPLY
    assert record["tools"] == ("create_task",)
    assert record["fallback_used"] is False
    assert record["outcome"] == "failed"


@pytest.mark.parametrize(
    "error",
    [
        ValueError("invalid content"),
        UnexpectedModelBehavior("bad output"),
        ModelHTTPError(400, "gemini-2.5-flash"),
        ModelHTTPError(403, "gemini-2.5-flash"),
    ],
)
async def test_content_validation_and_auth_errors_never_fallback(caplog, error):
    calls = []

    def primary(messages, info):
        raise error

    def fallback(messages, info):
        calls.append("fallback")
        return ModelResponse(parts=[TextPart("bad fallback")])

    _, channel, record = await _turn(primary, fallback, caplog)
    assert calls == []
    assert channel.last_text == FAILURE_REPLY
    assert record["fallback_used"] is False


async def test_fallback_failure_is_friendly_and_never_loops(caplog):
    calls = []

    def primary(messages, info):
        calls.append("primary")
        raise httpx.ConnectError("connection unavailable")

    def fallback(messages, info):
        calls.append("fallback")
        raise httpx.ReadTimeout("timeout")

    _, channel, record = await _turn(primary, fallback, caplog)
    assert calls == ["primary", "primary", "fallback"]
    assert channel.last_text == FAILURE_REPLY
    assert record["outcome"] == "failed"
    assert record["fallback_used"] is True


async def test_malformed_fallback_output_is_not_retried(caplog):
    calls = []

    def primary(messages, info):
        raise ModelHTTPError(503, "gemini-2.5-flash")

    def fallback(messages, info):
        calls.append("fallback")
        return ModelResponse(parts=[ToolCallPart("unknown_tool", {})])

    _, channel, record = await _turn(primary, fallback, caplog)
    assert calls == ["fallback"]
    assert channel.last_text == FAILURE_REPLY
    assert record["outcome"] == "failed"


async def test_refusal_has_no_model_fields_no_store_writes(caplog):
    store = FakeStore()
    user = await _participant(store, 1002)
    from src.tools.context import ToolContext
    from tests.fakes import FakeChannel, FakeScheduler

    context = ToolContext(
        store=store,
        user=user,
        session_id="unused",
        chat_id=1002,
        timezone="UTC",
        turn_id="refusal",
        channel=FakeChannel(),
        scheduler=FakeScheduler(),
    )
    with caplog.at_level("INFO"):
        reply = await SessionTurnOrchestrator(ModeRuntime(build_registry())).handle_turn(
            context, "private", requested_mode="coach"
        )
    record = _record(caplog)
    assert "isn't available" in reply
    assert record["outcome"] == "refused"
    assert record["requested_model"] is None and record["answering_model"] is None
    assert store.messages == [] and store.tasks == []


async def test_operational_logs_and_framework_spans_never_include_participant_content(caplog):
    store = FakeStore()
    user = await _participant(store, 1003)
    await store.update_user(user["user_id"], {"name": "NAME_SENTINEL_abcdef"})
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    responses = [
        ModelResponse(parts=[ToolCallPart("create_task", {"title": "TITLE_SENTINEL_abcdef"})]),
        ModelResponse(parts=[TextPart("REPLY_SENTINEL_abcdef")]),
    ]

    def scripted(messages, info):
        return responses.pop(0)

    runtime = ModeRuntime(build_registry())
    with (
        caplog.at_level("INFO"),
        patch("opentelemetry.trace.get_tracer_provider", return_value=provider),
        patch("pydantic_ai.models.instrumented.get_tracer_provider", return_value=provider),
    ):
        async with runtime.override(model=FunctionModel(scripted)):
            await _deliver(store, "MESSAGE_SENTINEL_abcdef", 1003, runtime)
    spans = exporter.get_finished_spans()
    assert any(span.name == "amigo.turn" for span in spans)
    assert len(spans) >= 4  # framework agent/model/Tool instrumentation is enabled
    captured = caplog.text + str([(s.attributes, s.events, s.status) for s in spans])
    for sentinel in ("NAME_SENTINEL", "TITLE_SENTINEL", "REPLY_SENTINEL", "MESSAGE_SENTINEL"):
        assert sentinel not in captured
    assert _record(caplog)["tools"] == ("create_task",)


async def test_provider_error_text_is_not_captured_in_framework_spans_or_logs(caplog):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    def failed(messages, info):
        raise ModelHTTPError(400, "gemini-2.5-flash", {"error": "ERROR_SENTINEL"})

    with (
        patch("opentelemetry.trace.get_tracer_provider", return_value=provider),
        patch("pydantic_ai.models.instrumented.get_tracer_provider", return_value=provider),
    ):
        await _turn(failed, failed, caplog)
    spans = exporter.get_finished_spans()
    assert spans
    assert "ERROR_SENTINEL" not in caplog.text + str(
        [(s.attributes, s.events, s.status) for s in spans]
    )


@pytest.mark.parametrize("model,known", [("gemini-2.5-flash", True), ("unlisted-model-abc", False)])
async def test_record_prices_observed_model_and_unknown_price_is_null(caplog, model, known):
    def reply(messages, info):
        return ModelResponse(
            parts=[TextPart("hello")],
            model_name=model,
            usage=RequestUsage(input_tokens=100, output_tokens=20),
        )

    runtime = ModeRuntime(build_registry())
    store = FakeStore()
    await _participant(store, 1001)
    with caplog.at_level("INFO"):
        async with runtime.override(model=FunctionModel(reply, model_name=model)):
            await _deliver(store, "hello", 1001, runtime)
    record = _record(caplog)
    assert record["input_tokens"] == 100 and record["output_tokens"] == 20
    assert record["answering_model"] == model
    if known:
        assert record["estimated_cost_usd"] > 0
    else:
        assert record["estimated_cost_usd"] is None


@pytest.mark.parametrize("suite", [None, "evals/not-existing.json"])
def test_live_mode_requires_existing_suite(suite):
    with pytest.raises(ValueError, match="existing evaluation suite"):
        ModeRegistry((_journal(eval_suite=suite),))


def test_live_fallback_requires_passing_manifest_evidence():
    with pytest.raises(ValueError, match="no passing Gate A evidence"):
        ModeRegistry((replace(DAILY, model=ModelPolicy(fallback="google:gemini-2.0-flash")),))


def test_all_live_fallbacks_have_complete_passing_evidence():
    root = Path(__file__).resolve().parents[1]
    for mode in build_registry():
        if mode.status == "live":
            require_evaluated_fallback(mode, root)
    assert DAILY.model == ModelPolicy()


def test_fallback_evidence_recomputes_full_case_results(tmp_path):
    root = Path(__file__).resolve().parents[1]
    evidence = passing_gate_a_evidence("a" * 40)
    evidence["purpose"] = "baseline"
    model = evidence["release_inputs"]["provider_model"]
    mode = replace(DAILY, model=ModelPolicy(fallback=model))
    currency = fallback_currency(mode, root)
    evidence["release_inputs"]["fallback_currency"] = currency
    (tmp_path / "evals/gate_a/v1").mkdir(parents=True)
    (tmp_path / "evals/gate_a/v1/cases.json").write_bytes(
        (root / "evals/gate_a/v1/cases.json").read_bytes()
    )
    artifact_path = tmp_path / "passed.json"
    artifact_path.write_text(json.dumps(evidence))

    def manifest():
        (tmp_path / "evals/fallback-evidence.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "entries": [
                        {
                            "mode_id": "daily",
                            "model": model,
                            "artifact": "passed.json",
                            "sha256": hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
                        }
                    ],
                }
            )
        )

    manifest()
    # Historical evidence verification only needs archived suite and recorded hashes, not copies
    # of the implementation sources. Keep fingerprints rooted in the actual repo during this test.
    with (
        patch("scripts.check_gate_a_evidence.current_fingerprints", return_value={}),
        patch("src.evaluation.model_policy.fallback_currency", return_value=currency),
    ):
        require_evaluated_fallback(mode, tmp_path)
        evidence["executions"][0]["turns"][0]["response"] = "you failed"
        artifact_path.write_text(json.dumps(evidence))
        manifest()
        with pytest.raises(ValueError, match="no passing Gate A evidence"):
            require_evaluated_fallback(mode, tmp_path)


@pytest.mark.parametrize("field", ["source_sha256", "dependency_versions", "tool_order"])
def test_fallback_evidence_rejects_stale_execution_source_sdk_or_order(tmp_path, field):
    from copy import deepcopy

    root = Path(__file__).resolve().parents[1]
    evidence = passing_gate_a_evidence("a" * 40)
    evidence["purpose"] = "baseline"
    model = evidence["release_inputs"]["provider_model"]
    mode = replace(DAILY, model=ModelPolicy(fallback=model))
    currency = fallback_currency(mode, root)
    evidence["release_inputs"]["fallback_currency"] = deepcopy(currency)
    evidence["release_inputs"]["fallback_currency"][field] = "stale"
    (tmp_path / "evals").mkdir()
    artifact = tmp_path / "passed.json"
    artifact.write_text(json.dumps(evidence))
    (tmp_path / "evals/fallback-evidence.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "entries": [
                    {
                        "mode_id": mode.id,
                        "model": model,
                        "artifact": "passed.json",
                        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                    }
                ],
            }
        )
    )
    with (
        patch("src.evaluation.model_policy.fallback_currency", return_value=currency),
        pytest.raises(ValueError, match="no passing Gate A evidence"),
    ):
        require_evaluated_fallback(mode, tmp_path)


async def test_known_fallback_alias_with_unknown_observed_price_is_null(caplog):
    def primary(messages, info):
        raise ModelHTTPError(503, "gemini-2.5-flash")

    def fallback(messages, info):
        return ModelResponse(
            parts=[TextPart("hello")], usage=RequestUsage(input_tokens=100, output_tokens=20)
        )

    runtime = _policy_runtime()
    store = FakeStore()
    await _participant(store, 1001)
    with caplog.at_level("INFO"):
        async with runtime.override(
            model=FunctionModel(primary),
            fallback=FunctionModel(fallback, model_name="unknown-observed-model"),
        ):
            await _deliver(store, "hello", 1001, runtime)
    record = _record(caplog)
    assert record["fallback_used"] is True
    assert record["answering_model"] == "unknown-observed-model"
    assert record["estimated_cost_usd"] is None


async def test_every_live_mode_deterministic_subset_passes_without_provider():
    assert await run_deterministic() == 0


async def test_generic_provider_runner_resolves_non_daily_mode_and_declared_suite(caplog):
    from types import SimpleNamespace

    mode = _journal(model=ModelPolicy(settings={"temperature": 0.1}))
    registry = ModeRegistry((DAILY, mode))
    runtime = _runtime_for(mode)
    suite = load_suite(Path(__file__).resolve().parents[1] / DAILY.eval_suite)
    case = next(case for case in suite.cases if case.id == "ga-nonmut-01")

    def reply(messages, info):
        assert info.model_settings == {"temperature": 0.1}
        assert not info.function_tools
        return ModelResponse(
            parts=[TextPart("Hello!")], usage=RequestUsage(input_tokens=100, output_tokens=20)
        )

    with (
        caplog.at_level("INFO"),
        patch("scripts.run_gate_a_eval.build_registry", return_value=registry),
        patch(
            "scripts.run_gate_a_eval.default_turn_orchestrator", SessionTurnOrchestrator(runtime)
        ),
    ):
        assert (
            await run_provider_eval(SimpleNamespace(mode=mode.id, suite=None, validate_only=True))
            == 0
        )
        execution = await _run_execution(
            case, suite, 1, FunctionModel(reply, model_name="scripted-journal"), mode.id
        )
    assert execution["passed"] is True
    assert execution["observed_model_names"] == ["scripted-journal"]
    assert execution["usage"] == {"input_tokens": 100, "output_tokens": 20}
    assert execution["estimated_cost_usd"] is None
    assert execution["turns"][0]["estimated_cost_usd"] is None
    assert _record(caplog)["mode_id"] == "journal"


def test_generic_checker_accepts_unknown_cost_null_and_rejects_forged_fixed_price():
    from dataclasses import asdict

    root = Path(__file__).resolve().parents[1]
    mode = replace(DAILY, id="testmode")
    evidence = passing_gate_a_evidence("a" * 40)
    evidence["purpose"] = "baseline"
    evidence["pricing"] = {
        "source": "genai-prices",
        "version": dependency_versions()["genai-prices"],
    }
    evidence["release_inputs"].update(
        {
            "mode_id": mode.id,
            "model_policy": asdict(mode.model),
            "observed_model_names": ["unknown-price-sentinel"],
        }
    )
    evidence["totals"]["estimated_cost_usd"] = None
    for execution in evidence["executions"]:
        execution["observed_model_names"] = ["unknown-price-sentinel"]
        execution["estimated_cost_usd"] = None
        for turn in execution["turns"]:
            turn["estimated_cost_usd"] = None
    args = {
        "revision": "a" * 40,
        "root": root,
        "suite_path": root / mode.eval_suite,
        "mode_id": mode.id,
        "mode_definition": mode,
        "_historical_baseline": True,
    }
    assert check_evidence(evidence, **args) == []
    evidence["executions"][0]["estimated_cost_usd"] = 0.00033
    errors = check_evidence(evidence, **args)
    assert any("estimated_cost_usd" in error for error in errors)
    evidence["pricing"] = {"source": "Daily fixed pricing"}
    assert any("evidence.pricing" in error for error in check_evidence(evidence, **args))
