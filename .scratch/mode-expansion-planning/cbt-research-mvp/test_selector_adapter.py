"""Offline mock-only contract checks; no real model/provider is constructed or dispatched."""

import asyncio
from dataclasses import replace

import pytest
from research_engine import MAX_QUESTIONS, ResearchEngine, RunState
from selector_adapter import OfflineSelectorAdapter, eligible_question_ids


@pytest.mark.parametrize(
    "response",
    [None, "free-form-sentinel", {}, {"question_id": "fact", "extra": "sentinel"},
     {"question_id": None}, {"question_id": ["fact"]}, {"question_id": "diagnose"},
     {"question_id": "takeaway"}, {"question_id": " fact "}],
)
async def test_invalid_missing_extra_and_out_of_state_outputs_rejected(response, caplog, capsys):
    calls = []

    async def transport(request):
        calls.append(request)
        return response

    adapter = OfflineSelectorAdapter(transport)
    result = await adapter.select(RunState(fixture_id="meeting", strategy="adaptive"))
    assert result.status == "invalid_response"
    assert result.question_id is None
    assert len(calls) == 1
    assert caplog.text == capsys.readouterr().out == ""


async def test_mock_engine_run_is_bounded_and_sends_only_consumed_fiction():
    requests = []

    async def transport(request):
        requests.append(request)
        return {"question_id": request.eligible_ids[-1]}

    engine = ResearchEngine(OfflineSelectorAdapter(transport))
    state = await engine.start("meeting", "adaptive")
    while state.status == "asking":
        state = await engine.advance(state, "skip" if state.question_id == "thought" else "answer")
    assert state.status == "complete"
    assert len(requests) == MAX_QUESTIONS
    assert requests[0].consumed_responses == ()
    assert requests[2].consumed_responses == (
        ("fact", "A suggestion was sent; no reply had arrived by noon."),
    )
    assert requests[2].eligible_ids == ("alternative",)
    assert "uncertainty" not in state.asked
    assert all(request.fixture_id == "meeting" for request in requests)
    assert [request.remaining_requests for request in requests] == [4, 3, 2, 1]


@pytest.mark.parametrize("status", ["complete", "stopped", "failed"])
async def test_terminal_state_prevents_dispatch(status):
    async def transport(request):
        pytest.fail("terminal state must not dispatch")

    result = await OfflineSelectorAdapter(transport).select(
        RunState(fixture_id="meeting", status=status)
    )
    assert result.status == "blocked"


async def test_unknown_fixture_and_inconsistent_answer_data_never_dispatch():
    async def transport(request):
        pytest.fail("untrusted state must not dispatch")

    adapter = OfflineSelectorAdapter(transport)
    for state in (
        RunState(fixture_id="personal-sentinel"),
        RunState(fixture_id="meeting", answered=("private-sentinel",)),
        RunState(fixture_id="meeting", asked=("fact",), answered=("fact",), skipped=("fact",)),
    ):
        assert (await adapter.select(state)).status == "blocked"


async def test_timeout_is_bounded_and_never_retries_or_exposes_exception(caplog, capsys):
    calls = []

    async def transport(request):
        calls.append(request)
        await asyncio.sleep(10)

    result = await OfflineSelectorAdapter(transport, timeout_seconds=0.01).select(
        RunState(fixture_id="meeting")
    )
    assert result.status == "timeout"
    assert len(calls) == 1
    assert caplog.text == capsys.readouterr().out == ""


async def test_transport_error_has_fixed_metadata_and_safe_engine_failure(caplog, capsys):
    calls = []

    async def transport(request):
        calls.append(request)
        raise RuntimeError("provider-error-private-sentinel")

    state = await ResearchEngine(OfflineSelectorAdapter(transport)).start("meeting", "adaptive")
    assert state.status == "failed"
    assert state.error == "provider_failed"
    assert len(calls) == 1
    assert "sentinel" not in repr(state) + caplog.text + capsys.readouterr().out


async def test_stop_before_dispatch_and_during_inflight_call():
    started = asyncio.Event()
    calls = []

    async def transport(request):
        calls.append(request)
        started.set()
        await asyncio.sleep(10)

    adapter = OfflineSelectorAdapter(transport)
    task = asyncio.create_task(adapter.select(RunState(fixture_id="meeting")))
    await started.wait()
    await adapter.stop()
    assert (await task).status == "stopped"
    assert (await adapter.select(RunState(fixture_id="meeting"))).status == "stopped"
    assert len(calls) == 1
    other = OfflineSelectorAdapter(transport)
    await other.stop()
    assert (await other.select(RunState(fixture_id="recipe"))).status == "stopped"
    assert len(calls) == 1


async def test_budget_counts_invalid_outputs_even_with_repeated_fresh_state():
    calls = []

    async def transport(request):
        calls.append(request)
        return None

    adapter = OfflineSelectorAdapter(transport)
    for _ in range(MAX_QUESTIONS):
        assert (await adapter.select(RunState(fixture_id="meeting"))).status == "invalid_response"
    assert (await adapter.select(RunState(fixture_id="meeting"))).status == "blocked"
    assert len(calls) == MAX_QUESTIONS


async def test_skipped_fact_excludes_missing_fact_branch_and_repeat():
    state = RunState(fixture_id="recipe", strategy="adaptive", asked=("fact",), skipped=("fact",))
    assert await eligible_question_ids(state) == ("thought",)
    end = replace(state, asked=("fact", "thought", "alternative"))
    assert await eligible_question_ids(end) == ("takeaway",)
