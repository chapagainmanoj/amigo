"""Development/eval Gemini accounting uses public request results, never production writes."""

import asyncio
import json
import threading
from unittest.mock import AsyncMock, patch

import pytest
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.usage import RequestUsage

from src.agent.catalogue import build_registry
from src.agent.runtime import ModeRuntime
from src.config import Settings
from src.model_usage import LoggedGoogleModel, record_gemini_request


async def test_request_log_is_metadata_only_and_counts_each_request(tmp_path):
    path = tmp_path / "usage.jsonl"
    await record_gemini_request(
        "google:gemini-test", input_tokens=12, output_tokens=4, path=path
    )
    await record_gemini_request("google:gemini-test", outcome="error", path=path)
    records = [json.loads(line) for line in path.read_text().splitlines()]
    assert sum(item["requests"] for item in records) == 2
    assert records[0]["input_tokens"] == 12
    assert records[1]["input_tokens"] is None
    assert records[1]["output_tokens"] is None
    assert set(records[0]) == {
        "at", "model_id", "requests", "input_tokens", "output_tokens", "outcome"
    }


async def test_log_filesystem_work_runs_off_event_loop(tmp_path, monkeypatch):
    import os

    loop_thread = threading.get_ident()
    write_threads = []
    original_write = os.write

    def checked_write(descriptor, payload):
        write_threads.append(threading.get_ident())
        return original_write(descriptor, payload)

    monkeypatch.setattr("src.model_usage.os.write", checked_write)
    await record_gemini_request("gemini-test", path=tmp_path / "usage.jsonl")
    assert write_threads and all(thread != loop_thread for thread in write_threads)


@pytest.mark.parametrize("outcome", ["ok", "error", "cancelled"])
async def test_public_request_result_counts_usage_failures_and_cancellation(monkeypatch, outcome):
    model = LoggedGoogleModel("gemini-test", provider=GoogleProvider(api_key="private-key"))
    response = ModelResponse(
        parts=[TextPart("private-output")],
        usage=RequestUsage(input_tokens=13, output_tokens=8),
    )
    request = AsyncMock(return_value=response)
    if outcome == "error":
        request.side_effect = ModelHTTPError(503, "gemini-test", body="private-input private-key")
    elif outcome == "cancelled":
        request.side_effect = asyncio.CancelledError()
    monkeypatch.setattr(GoogleModel, "request", request)
    record = AsyncMock()
    monkeypatch.setattr("src.model_usage.record_gemini_request", record)
    if outcome == "ok":
        assert await model.request([], None, None) is response
    else:
        with pytest.raises(ModelHTTPError if outcome == "error" else asyncio.CancelledError):
            await model.request([], None, None)
    assert request.await_count == record.await_count == 1
    assert record.call_args.args == ("google:gemini-test",)
    metadata = record.call_args.kwargs
    assert metadata.get("input_tokens") == (13 if outcome == "ok" else None)
    assert metadata.get("output_tokens") == (8 if outcome == "ok" else None)
    assert metadata.get("outcome", "ok") == outcome
    assert "private" not in str(record.call_args)
    assert "_generate_content" not in LoggedGoogleModel.__dict__
    assert "_build_content_and_config" not in LoggedGoogleModel.__dict__


async def test_local_validation_failure_is_not_logged_as_provider_request(monkeypatch):
    model = LoggedGoogleModel("gemini-test", provider=GoogleProvider(api_key="private-key"))
    monkeypatch.setattr(GoogleModel, "request", AsyncMock(side_effect=ValueError("invalid")))
    record = AsyncMock()
    monkeypatch.setattr("src.model_usage.record_gemini_request", record)
    with pytest.raises(ValueError):
        await model.request([], None, None)
    record.assert_not_called()


@pytest.mark.parametrize("prefix", ["google", "google-gla"])
async def test_production_factory_builds_plain_google_model_without_logging(prefix, monkeypatch):
    runtime = ModeRuntime(build_registry())
    record = AsyncMock()
    monkeypatch.setattr("src.model_usage.record_gemini_request", record)
    response = ModelResponse(parts=[TextPart("fictional response")])
    monkeypatch.setattr(GoogleModel, "request", AsyncMock(return_value=response))
    with patch("src.config.settings", Settings(
        _env_file=None, app_env="production", google_api_key="test-key"
    )):
        model = await runtime.model_for(f"{prefix}:gemini-test")
        assert type(model) is GoogleModel
        assert await model.request([], None, None) is response
    record.assert_not_awaited()


async def test_production_factory_does_not_reuse_cached_development_logging_model():
    runtime = ModeRuntime(build_registry())
    with patch("src.config.settings", Settings(_env_file=None, google_api_key="test-key")):
        development = await runtime.model_for("google:gemini-test")
        assert isinstance(development, LoggedGoogleModel)
    with patch("src.config.settings", Settings(
        _env_file=None, app_env="production", google_api_key="test-key"
    )):
        production = await runtime.model_for("google:gemini-test")
        assert type(production) is GoogleModel
        assert production is await runtime.model_for("google:gemini-test")


async def test_explicit_eval_runner_keeps_accounting_in_production_environment():
    from scripts.run_gate_a_eval import RateLimitedGoogleModel

    with patch("src.config.settings", Settings(_env_file=None, app_env="production")):
        model = RateLimitedGoogleModel(
            "gemini-test", provider=GoogleProvider(api_key="test-key"),
            minimum_interval_seconds=0,
        )
        assert isinstance(model, LoggedGoogleModel)


async def test_log_failure_does_not_disclose_os_error_or_break_model(tmp_path, caplog):
    blocked = tmp_path / "file"
    blocked.write_text("not a directory")
    await record_gemini_request("gemini-test", path=blocked / "secret-location")
    assert "could not be recorded" in caplog.text
    assert "secret-location" not in caplog.text


async def test_malformed_provider_response_still_counts_dispatched_request(monkeypatch):
    from google.genai import types
    from pydantic_ai.exceptions import UnexpectedModelBehavior
    from pydantic_ai.models import ModelRequestParameters

    model = LoggedGoogleModel("gemini-test", provider=GoogleProvider(api_key="fictional-key"))
    response = types.GenerateContentResponse(candidates=[
        types.Candidate(content=types.Content(parts=[types.Part()])),
    ])
    dispatch = AsyncMock(return_value=response)
    monkeypatch.setattr(model.client.aio.models, "generate_content", dispatch)
    record = AsyncMock()
    monkeypatch.setattr("src.model_usage.record_gemini_request", record)
    with pytest.raises(UnexpectedModelBehavior):
        await model.request([], None, ModelRequestParameters())
    assert dispatch.await_count == 1
    record.assert_awaited_once_with("google:gemini-test", outcome="error")
