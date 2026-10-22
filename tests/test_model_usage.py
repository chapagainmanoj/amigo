"""Gemini accounting follows actual dispatches without retaining request content."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic_ai.providers.google import GoogleProvider

from src.model_usage import LoggedGoogleModel, record_gemini_request


@pytest.mark.asyncio
async def test_request_log_is_metadata_only_and_counts_each_dispatch(tmp_path):
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


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["ok", "error", "cancelled"])
async def test_sdk_dispatch_counts_failures_and_cancellation(monkeypatch, outcome):
    model = LoggedGoogleModel("gemini-test", provider=GoogleProvider(api_key="private-key"))
    monkeypatch.setattr(
        model, "_build_content_and_config", AsyncMock(return_value=(["private-input"], {}))
    )
    response = SimpleNamespace(
        usage_metadata=SimpleNamespace(
            prompt_token_count=13, candidates_token_count=5, thoughts_token_count=3
        )
    )
    dispatch = AsyncMock(return_value=response)
    if outcome == "error":
        dispatch.side_effect = RuntimeError("private-input private-key")
    elif outcome == "cancelled":
        dispatch.side_effect = asyncio.CancelledError()
    monkeypatch.setattr(model.client.aio.models, "generate_content", dispatch)
    record = AsyncMock()
    monkeypatch.setattr("src.model_usage.record_gemini_request", record)
    if outcome == "ok":
        assert await model._generate_content([], False, {}, None) is response
    else:
        with pytest.raises(RuntimeError if outcome == "error" else asyncio.CancelledError):
            await model._generate_content([], False, {}, None)
    assert dispatch.await_count == record.await_count == 1
    record.assert_awaited_once_with(
        "google:gemini-test", input_tokens=13 if outcome == "ok" else None,
        output_tokens=8 if outcome == "ok" else None, outcome=outcome,
    )
    assert "private" not in str(record.call_args)


@pytest.mark.asyncio
async def test_local_validation_failure_is_not_a_provider_request(monkeypatch):
    model = LoggedGoogleModel("gemini-test", provider=GoogleProvider(api_key="private-key"))
    monkeypatch.setattr(
        model, "_build_content_and_config", AsyncMock(side_effect=ValueError("invalid"))
    )
    record = AsyncMock()
    monkeypatch.setattr("src.model_usage.record_gemini_request", record)
    with pytest.raises(ValueError):
        await model._generate_content([], False, {}, None)
    record.assert_not_called()


@pytest.mark.asyncio
async def test_log_failure_does_not_disclose_os_error_or_break_model(tmp_path, caplog):
    blocked = tmp_path / "file"
    blocked.write_text("not a directory")
    await record_gemini_request("gemini-test", path=blocked / "secret-location")
    assert "could not be recorded" in caplog.text
    assert "secret-location" not in caplog.text
