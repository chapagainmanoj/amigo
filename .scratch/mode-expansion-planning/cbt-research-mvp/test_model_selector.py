"""Fiction-only mocked ladder tests; never invokes a live model."""

import asyncio
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from model_selector import (
    MODEL,
    ClaudeModels,
    ModelSelectorProvider,
    SharedRequestBudget,
    _selection_config,
    build_selector,
    google_http_options,
)
from research_engine import ResearchEngine, RunState
from selector_adapter import SelectionRejectedError


def provider(transport, **kwargs):
    client = SimpleNamespace(models=SimpleNamespace(generate_content=transport))
    return ModelSelectorProvider(client, SharedRequestBudget(), **kwargs)


async def test_dispatch_count_and_payload_four_per_run_no_batch_cap():
    calls = []
    budget = SharedRequestBudget()

    async def transport(**kwargs):
        import json

        calls.append(kwargs)
        payload = json.loads(kwargs["contents"].split("\n", 1)[1])
        return SimpleNamespace(parsed={"question_id": payload["eligible_question_ids"][0]})

    for _ in range(3):
        selector = ModelSelectorProvider(
            SimpleNamespace(models=SimpleNamespace(generate_content=transport)), budget
        )
        engine = ResearchEngine(selector)
        state = await engine.start("meeting", "adaptive")
        while state.status == "asking":
            state = await engine.advance(state, "answer")
        assert state.status == "complete"
        assert len(selector.metrics) == 4
        with pytest.raises(SelectionRejectedError):
            await selector.choose(RunState(fixture_id="meeting"))
    assert len(calls) == budget.used == 12
    assert "consumed_fictional_responses" in calls[1]["contents"]
    config = _selection_config(("fact",))
    assert config.max_output_tokens == 64
    assert config.tools == []
    assert config.automatic_function_calling.disable
    assert google_http_options().retry_options.attempts == 1


@pytest.mark.parametrize(
    "parsed",
    [
        None,
        "fact",
        {},
        {"question_id": "fact", "extra": "secret"},
        {"question_id": "takeaway"},
        {"question_id": ["fact"]},
        {"question_id": " fact "},
        {"question_id": "unknown"},
    ],
)
async def test_strict_output_and_safe_errors(parsed, caplog, capsys):
    transport = AsyncMock(return_value=SimpleNamespace(parsed=parsed))
    selector = provider(transport)
    with pytest.raises(SelectionRejectedError, match="invalid output"):
        await selector.choose(RunState(fixture_id="meeting"))
    assert transport.await_count == 1
    assert "secret" not in str([asdict(item) for item in selector.metrics])
    assert caplog.text == capsys.readouterr().out == ""


async def test_repeat_id_rejected():
    selector = provider(AsyncMock(return_value=SimpleNamespace(parsed={"question_id": "fact"})))
    state = RunState(fixture_id="meeting", asked=("fact",), answered=("fact",), selections=1)
    with pytest.raises(SelectionRejectedError):
        await selector.choose(state)


async def test_failure_private_and_counted_no_retries(caplog, capsys):
    transport = AsyncMock(side_effect=RuntimeError("key-private-fixture-secret"))
    selector = provider(transport)
    state = await ResearchEngine(selector).start("meeting")
    assert state.error == "provider_failed"
    assert selector.metrics[0].status == "provider_failed"
    assert transport.await_count == 1
    captured = repr(state) + repr(selector.metrics) + caplog.text + capsys.readouterr().out
    assert "secret" not in captured


async def test_coordinated_stop_clears_inflight_engine_and_blocks_restart():
    started = asyncio.Event()

    async def transport(**kwargs):
        started.set()
        await asyncio.sleep(10)

    selector = provider(transport)
    engine = ResearchEngine(selector)
    pending = asyncio.create_task(engine.start("recipe"))
    await started.wait()
    assert await engine.stop() == RunState(status="stopped")
    assert await pending == RunState(status="stopped")
    assert await engine.start("meeting") == RunState(status="stopped")
    assert selector.metrics[0].status == "stopped"


async def test_timeout_and_external_cancellation_counted():
    async def transport(**kwargs):
        await asyncio.sleep(10)

    selector = provider(transport, timeout_seconds=0.01)
    with pytest.raises(SelectionRejectedError, match="timed out"):
        await selector.choose(RunState(fixture_id="meeting"))
    assert selector.metrics[0].status == "timeout"
    selector = provider(transport)
    task = asyncio.create_task(selector.choose(RunState(fixture_id="meeting")))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert selector.metrics[0].status == "stopped"


async def test_factory_default_backup_and_final_only(monkeypatch):
    assert (await build_selector()).model == "claude-cli:sonnet"
    assert (await build_selector("ollama:qwen3.5:4b")).model == "ollama:qwen3.5:4b"
    with pytest.raises(ValueError):
        await build_selector(MODEL)
    with pytest.raises(ValueError):
        await build_selector("anthropic:claude")
    aio = SimpleNamespace(models=object())

    def client_factory(key):
        return SimpleNamespace(aio=aio)

    monkeypatch.setattr("model_selector.build_google_client", client_factory)
    assert (await build_selector(MODEL, final_eval=True, api_key="secret"))._client is aio


async def test_cli_subscription_env_tools_output_and_privacy(monkeypatch):
    process = SimpleNamespace(
        returncode=0,
        communicate=AsyncMock(return_value=(b'{"result":"{\\"question_id\\":\\"fact\\"}"}', None)),
    )
    spawn = AsyncMock(return_value=process)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "private-key")
    response = await ClaudeModels().generate_content(
        model="claude-cli:sonnet", contents="fiction", config=None
    )
    assert response.parsed == {"question_id": "fact"}
    args, kwargs = spawn.call_args
    assert "ANTHROPIC_API_KEY" not in kwargs["env"]
    assert kwargs["env"]["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == "64"
    assert args[args.index("--tools") + 1] == ""
    assert "--no-session-persistence" in args
    assert "--safe-mode" in args


async def test_duplicate_json_fields_gemini_rejected_and_usage_logged(monkeypatch):
    logs = AsyncMock()
    monkeypatch.setattr("src.model_usage.record_gemini_request", logs)
    response = SimpleNamespace(
        parsed={"question_id": "fact"}, text='{"question_id":"takeaway","question_id":"fact"}'
    )
    selector = provider(AsyncMock(return_value=response), model=MODEL)
    with pytest.raises(SelectionRejectedError):
        await selector.choose(RunState(fixture_id="meeting"))
    assert logs.await_count == 1
    assert logs.call_args.kwargs["outcome"] == "error"


async def test_actual_gemini_metadata_writer_no_content_or_keys(monkeypatch, tmp_path):
    import json

    from src import model_usage

    path = tmp_path / "usage.jsonl"
    monkeypatch.setattr(model_usage, "DEFAULT_USAGE_PATH", path)
    selector = provider(AsyncMock(side_effect=RuntimeError("private-key-content")), model=MODEL)
    with pytest.raises(SelectionRejectedError):
        await selector.choose(RunState(fixture_id="meeting"))
    record = json.loads(path.read_text())
    assert record["requests"] == 1
    assert record["outcome"] == "error"
    assert "private" not in path.read_text()
    assert set(record) == {"at", "model_id", "requests", "input_tokens", "output_tokens", "outcome"}


@pytest.mark.parametrize(
    "text",
    [
        '{"question_id":NaN}',
        '{"question_id":Infinity}',
        '{"question_id":"fact","question_id":"fact"}',
    ],
)
async def test_nonstandard_json_and_duplicates_rejected(text):
    from model_selector import _strict_json

    with pytest.raises(ValueError):
        _strict_json(text)
