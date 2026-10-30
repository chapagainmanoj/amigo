"""Telegram update replay and participant ordering tests."""

import asyncio

from src.bot.update_claims import ChannelUpdateCoordinator
from tests.fakes import FakeStore


async def test_concurrent_duplicate_update_executes_only_once():
    store = FakeStore()
    coordinator = ChannelUpdateCoordinator(store)
    started = asyncio.Event()
    release = asyncio.Event()
    executions = 0

    async def process() -> None:
        nonlocal executions
        executions += 1
        started.set()
        await release.wait()

    first = asyncio.create_task(
        coordinator.run(
            update_id=101,
            chat_id=7,
            update_kind="message",
            process=process,
        )
    )
    await started.wait()
    duplicate = await coordinator.run(
        update_id=101,
        chat_id=7,
        update_kind="message",
        process=process,
    )
    release.set()
    original = await first

    assert original.outcome == "completed"
    assert duplicate.outcome == "duplicate"
    assert executions == 1
    assert store.telegram_updates[101]["status"] == "completed"


async def test_failed_update_is_acknowledged_and_inspectable():
    store = FakeStore()
    coordinator = ChannelUpdateCoordinator(store)

    async def fail() -> None:
        raise RuntimeError("sensitive internal detail")

    result = await coordinator.run(
        update_id=102,
        chat_id=7,
        update_kind="message",
        process=fail,
    )

    assert result.outcome == "failed"
    assert store.telegram_updates[102]["status"] == "failed"
    assert store.telegram_updates[102]["failure_code"] == "RuntimeError"
    assert "sensitive" not in str(store.telegram_updates[102])


async def test_same_participant_turns_execute_in_arrival_order():
    store = FakeStore()
    coordinator = ChannelUpdateCoordinator(store)
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    order: list[str] = []

    async def first_process() -> None:
        order.append("first-start")
        first_started.set()
        await release_first.wait()
        order.append("first-end")

    async def second_process() -> None:
        order.append("second")

    first = asyncio.create_task(
        coordinator.run(
            update_id=201,
            chat_id=8,
            update_kind="message",
            process=first_process,
        )
    )
    await first_started.wait()
    second = asyncio.create_task(
        coordinator.run(
            update_id=202,
            chat_id=8,
            update_kind="message",
            process=second_process,
        )
    )
    await asyncio.sleep(0)
    assert order == ["first-start"]

    release_first.set()
    await asyncio.gather(first, second)
    assert order == ["first-start", "first-end", "second"]


async def test_different_participants_can_execute_concurrently():
    store = FakeStore()
    coordinator = ChannelUpdateCoordinator(store)
    both_started = asyncio.Event()
    release = asyncio.Event()
    started: set[int] = set()

    async def process(chat_id: int) -> None:
        started.add(chat_id)
        if len(started) == 2:
            both_started.set()
        await release.wait()

    turns = [
        asyncio.create_task(
            coordinator.run(
                update_id=300 + chat_id,
                chat_id=chat_id,
                update_kind="message",
                process=lambda chat_id=chat_id: process(chat_id),
            )
        )
        for chat_id in (9, 10)
    ]
    await asyncio.wait_for(both_started.wait(), timeout=1)
    release.set()
    await asyncio.gather(*turns)
    assert started == {9, 10}


async def _overlap(store, first, second, first_ids, second_ids) -> bool:
    """Run two updates whose first blocks; report whether the second ran meanwhile."""
    release, started, overlapped = asyncio.Event(), asyncio.Event(), False

    async def slow() -> None:
        started.set()
        await release.wait()

    async def fast() -> None:
        nonlocal overlapped
        overlapped = not release.is_set()

    task = asyncio.create_task(first.run(**first_ids, update_kind="message", process=slow))
    await started.wait()
    other = asyncio.create_task(second.run(**second_ids, update_kind="message", process=fast))
    await asyncio.sleep(0.01)
    release.set()
    await asyncio.gather(task, other)
    return overlapped


async def test_one_participant_serializes_across_channels():
    store = FakeStore()
    user = await store.create_user(7101)
    store._identity_state.link(user["user_id"], "fake2", "ext-7101")
    telegram = ChannelUpdateCoordinator(store)
    fake2 = ChannelUpdateCoordinator(store, telegram.serializer, channel_id="fake2")

    assert not await _overlap(
        store, telegram, fake2,
        {"update_id": 301, "chat_id": 7101}, {"update_id": "f-1", "chat_id": "ext-7101"},
    )
    assert store.telegram_updates[301]["status"] == "completed"
    assert (await store.finish_channel_update("fake2", "f-1", status="completed"))[
        "status"
    ] == "completed"


async def test_different_participants_on_different_channels_do_not_block():
    store = FakeStore()
    await store.create_user(7201)
    telegram = ChannelUpdateCoordinator(store)
    fake2 = ChannelUpdateCoordinator(store, telegram.serializer, channel_id="fake2")

    assert await _overlap(
        store, telegram, fake2,
        {"update_id": 302, "chat_id": 7201}, {"update_id": "f-2", "chat_id": "unpaired"},
    )


async def test_failed_participant_lookup_finishes_the_claim_as_failed(monkeypatch):
    store = FakeStore()
    coordinator = ChannelUpdateCoordinator(store)

    async def unavailable(*_args):
        raise ConnectionError("database unavailable")

    monkeypatch.setattr(store, "get_user_by_channel_identity", unavailable)
    processed = []

    async def process() -> None:
        processed.append(True)

    result = await coordinator.run(
        update_id=401, chat_id=7401, update_kind="message", process=process
    )
    assert result.outcome == "failed" and not processed
    assert store.telegram_updates[401]["status"] == "failed"
    assert store.telegram_updates[401]["failure_code"] == "ConnectionError"


async def test_first_contact_pairing_keeps_the_next_message_behind_it():
    """The /start Turn links the sender mid-Turn; the next message still waits for it."""
    store = FakeStore()
    coordinator = ChannelUpdateCoordinator(store)
    linked, release, overlapped = asyncio.Event(), asyncio.Event(), False

    async def pairing() -> None:
        await store.create_user(7501)  # Pairing creates and links the participant.
        linked.set()
        await release.wait()

    async def next_message() -> None:
        nonlocal overlapped
        overlapped = not release.is_set()

    first = asyncio.create_task(coordinator.run(
        update_id=501, chat_id=7501, update_kind="message", process=pairing
    ))
    await linked.wait()
    second = asyncio.create_task(coordinator.run(
        update_id=502, chat_id=7501, update_kind="message", process=next_message
    ))
    await asyncio.sleep(0.01)
    release.set()
    await asyncio.gather(first, second)
    assert not overlapped
