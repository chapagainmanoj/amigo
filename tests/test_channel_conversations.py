"""Explicit Telegram delivery addressing and channel-neutral immutable references."""

import asyncio
from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram.error import BadRequest

from src.channels.base import ChannelCapabilities, ConversationRef, ConversationUnavailableError
from src.channels.cli import CLIChannel
from src.channels.telegram import TelegramChannel


def threaded_channel():
    channel = TelegramChannel()
    channel.capabilities = ChannelCapabilities(threads=True)
    channel.bot = SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=42)),
        create_forum_topic=AsyncMock(return_value=SimpleNamespace(message_thread_id=235)),
        close_forum_topic=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
    )
    return channel


def test_conversation_is_an_immutable_detached_json_mapping():
    endpoint = {"chat_id": 123, "nested": {"ids": [1, 2]}}
    ref = ConversationRef("telegram", endpoint)
    endpoint["chat_id"] = 999
    assert ref.endpoint["chat_id"] == 123
    with pytest.raises(FrozenInstanceError):
        ref.channel = "other"
    with pytest.raises(TypeError):
        ref.endpoint["chat_id"] = 999
    with pytest.raises(TypeError):
        ref.endpoint["nested"]["ids"][0] = 999


@pytest.mark.parametrize("endpoint", [{"value": float("nan")}, {"value": object()}, [1]])
def test_conversation_rejects_non_json_endpoint(endpoint):
    with pytest.raises(ValueError):
        ConversationRef("telegram", endpoint)


@pytest.mark.parametrize(
    ("topics", "user_threads"), [(True, True)]
)
async def test_production_refuses_unsafe_topic_settings(topics, user_threads):
    channel = TelegramChannel()
    channel.bot = SimpleNamespace(
        get_me=AsyncMock(
            return_value=SimpleNamespace(
                username="test_bot",
                has_topics_enabled=topics,
                allows_users_to_create_topics=user_threads,
            )
        )
    )
    with pytest.raises(RuntimeError, match="Threaded Mode"):
        await channel.initialize(production=True)


async def test_initialize_sets_thread_capability_and_chat_deep_link():
    channel = threaded_channel()
    channel.bot.get_me = AsyncMock(
        return_value=SimpleNamespace(
            username="test_bot",
            has_topics_enabled=True,
            allows_users_to_create_topics=False,
        )
    )
    assert await channel.initialize(production=True) == "test_bot"
    assert channel.capabilities.threads
    assert (
        await channel.conversation_link(ConversationRef("telegram", {"chat_id": 123}))
        == "https://t.me/test_bot"
    )


async def test_development_warns_for_unthreaded_bot(caplog):
    channel = TelegramChannel()
    channel.bot = SimpleNamespace(
        get_me=AsyncMock(return_value=SimpleNamespace(username="test_bot"))
    )
    await channel.initialize()
    assert not channel.capabilities.threads
    assert "topics disabled" in caplog.text


async def test_explicit_conversation_is_the_only_delivery_thread():
    channel = threaded_channel()
    ref = ConversationRef("telegram", {"chat_id": 123, "thread_id": 227})
    await channel.send_message(123, "Coach", conversation=ref)
    assert channel.bot.send_message.await_args.kwargs["message_thread_id"] == 227
    channel.bot.create_forum_topic.assert_not_awaited()


async def test_unpaired_replies_create_no_topics_or_unthreaded_sends():
    channel = threaded_channel()
    await asyncio.gather(channel.send_message(123, "Pair"), channel.send_message(123, "Denied"))
    channel.bot.create_forum_topic.assert_not_awaited()
    channel.bot.send_message.assert_not_awaited()


async def test_implicit_reply_uses_durable_default_resolver_before_bootstrap():
    channel = threaded_channel()
    ref = ConversationRef("telegram", {"chat_id": 123, "thread_id": 99})
    channel.default_conversation_resolver = AsyncMock(return_value=ref)
    await channel.send_message(123, "Reminder")
    channel.default_conversation_resolver.assert_awaited_once_with(123)
    assert channel.bot.send_message.await_args.kwargs["message_thread_id"] == 99
    channel.bot.create_forum_topic.assert_not_awaited()


@pytest.mark.parametrize(
    "ref",
    [
        ConversationRef("cli", {"chat_id": 123}),
        ConversationRef("telegram", {"chat_id": 999, "thread_id": 1}),
        ConversationRef("telegram", {"chat_id": 123, "thread_id": -1}),
        ConversationRef("telegram", {"chat_id": 123}),
    ],
)
async def test_wrong_endpoint_never_sends(ref):
    channel = threaded_channel()
    with pytest.raises(ValueError):
        await channel.send_message(123, "Cannot send", conversation=ref)
    channel.bot.send_message.assert_not_awaited()


async def test_missing_thread_raises_repair_signal_and_never_resends_without_thread():
    channel = threaded_channel()
    channel.bot.send_message.side_effect = BadRequest("Message thread not found")
    ref = ConversationRef("telegram", {"chat_id": 123, "thread_id": 227})
    with pytest.raises(ConversationUnavailableError) as error:
        await channel.send_message(123, "Retry later", conversation=ref)
    assert error.value.conversation == ref
    channel.bot.send_message.assert_awaited_once()
    assert channel.bot.send_message.await_args.kwargs["message_thread_id"] == 227


async def test_topic_close_and_edit_buttons_validate_address():
    channel = threaded_channel()
    ref = ConversationRef("telegram", {"chat_id": 123, "thread_id": 227})
    await channel.close_conversation(123, ref)
    channel.bot.close_forum_topic.assert_awaited_once_with(chat_id=123, message_thread_id=227)
    await channel.edit_message_buttons(123, 42, conversation=ref)
    channel.bot.edit_message_reply_markup.assert_awaited_once_with(
        chat_id=123,
        message_id=42,
        reply_markup=None,
    )


@pytest.mark.parametrize("callback", [False, True])
async def test_update_decoding_is_neutral_and_preserves_unknown_threads(callback):
    channel = threaded_channel()
    message = {"chat": {"id": 123}, "message_id": 42, "text": "Hello", "message_thread_id": 999}
    data = {"update_id": 7, "message": message}
    if callback:
        data = {
            "update_id": 7,
            "callback_query": {"id": "cb", "data": "done:1", "message": message},
        }
    decoded = await channel.decode_update(data)
    assert decoded.chat_id == 123
    assert dict(decoded.conversation.endpoint) == {"chat_id": 123, "thread_id": 999}
    assert decoded.kind == ("callback_query" if callback else "message")
    assert decoded.data == ("done:1" if callback else None)


async def test_inaccessible_callback_message_is_ignored():
    channel = threaded_channel()
    decoded = await channel.decode_update(
        {
            "update_id": 7,
            "callback_query": {
                "id": "cb",
                "data": "done:1",
                "message": {
                    "date": 0,
                    "chat": {"id": 123},
                    "message_id": 42,
                },
            },
        }
    )
    assert decoded is None


async def test_nonthreaded_cli_accepts_its_own_neutral_endpoint(capsys):
    channel = CLIChannel()
    ref = await channel.create_conversation(123, "Daily")
    await channel.send_message(123, "Hello", conversation=ref)
    assert "Hello" in capsys.readouterr().out
    assert not channel.capabilities.threads
    assert await channel.conversation_link(None) is None
    await channel.close_conversation(123, ref)
    with pytest.raises(ValueError):
        await channel.send_message(999, "Cannot send", conversation=ref)


async def test_fake_channel_supports_neutral_threaded_and_unthreaded_contract():
    from tests.fakes import FakeChannel

    for threads in (False, True):
        channel = FakeChannel(threads=threads, channel_id="fake")
        ref = await channel.create_conversation(123, "Daily")
        await channel.send_message(123, "Reply", conversation=ref)
        await channel.edit_message_buttons(123, 1, conversation=ref)
        await channel.close_conversation(123, ref)
        assert channel.sent[-1]["conversation"] == ref
        assert channel.edited[-1]["conversation"] == ref
        assert channel.closed_conversations == [ref]
        assert channel.capabilities.threads is threads
        assert await channel.recipient_for({"telegram_chat_id": 123}) == 123


async def test_callback_acknowledgement_stays_inside_telegram_transport():
    channel = threaded_channel()
    channel.bot.answer_callback_query = AsyncMock()
    await channel.acknowledge_callback("callback-7")
    channel.bot.answer_callback_query.assert_awaited_once_with(callback_query_id="callback-7")


async def test_flat_update_has_no_thread_reference():
    channel = threaded_channel()
    decoded = await channel.decode_update(
        {
            "update_id": 7,
            "message": {"chat": {"id": 123}, "text": "Hello"},
        }
    )
    assert decoded.conversation is None


@pytest.mark.parametrize("user_threads", [True, False, None])
async def test_production_topics_off_uses_in_chat_commands(user_threads, caplog):
    channel = TelegramChannel()
    channel.bot = SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(
        username="test_bot", has_topics_enabled=False,
        allows_users_to_create_topics=user_threads,
    )))
    assert await channel.initialize(production=True) == "test_bot"
    assert channel.capabilities.threads is False
    assert "in-chat Mode commands" in caplog.text


@pytest.mark.parametrize("production", [True, False])
async def test_get_me_failure_only_blocks_production(production, caplog):
    channel = threaded_channel()
    channel.bot.get_me = AsyncMock(side_effect=RuntimeError("provider-private-detail"))
    if production:
        with pytest.raises(RuntimeError, match="capability check failed"):
            await channel.initialize(production=True)
    else:
        assert await channel.initialize(production=False) is None
    assert not channel.capabilities.threads
    assert "provider-private-detail" not in caplog.text


async def test_unknown_user_topic_flag_warns_without_claiming_it_is_enabled(caplog):
    channel = TelegramChannel()
    channel.bot = SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(
        username="test_bot", has_topics_enabled=True,
    )))
    assert await channel.initialize(production=True) == "test_bot"
    assert channel.capabilities.threads
    assert "user-created threads" in caplog.text
