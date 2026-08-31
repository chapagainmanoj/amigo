"""Telegram update replay and participant ordering tests."""

import asyncio

from src.bot.update_claims import TelegramUpdateCoordinator
from tests.fakes import FakeStore


async def test_concurrent_duplicate_update_executes_only_once():
    store = FakeStore()
    coordinator = TelegramUpdateCoordinator(store)
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
    coordinator = TelegramUpdateCoordinator(store)

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
    coordinator = TelegramUpdateCoordinator(store)
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
    coordinator = TelegramUpdateCoordinator(store)
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
