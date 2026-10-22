#!/usr/bin/env python3
"""Owner-run private-topic probe. Reads a disposable token from TEST_BOT_TOKEN.

No application settings or .env are loaded. Console evidence contains only stage
names, booleans, update IDs and thread IDs; incoming text and API errors stay private.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from collections.abc import Awaitable, Callable

import httpx


class SpikeError(Exception):
    """A deliberately content-free probe failure."""


class ThreadMissingError(SpikeError):
    """Telegram specifically rejected the deleted topic."""


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise SpikeError("Invalid arguments; use --help for usage.")


class TestBotAPI:
    """Small direct HTTP adapter; never includes provider data in exceptions."""

    def __init__(self, token: str, client: httpx.AsyncClient):
        self._token = token
        self._client = client

    async def call(self, method: str, **params):
        try:
            response = await self._client.post(
                f"https://api.telegram.org/bot{self._token}/{method}", json=params
            )
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            raise SpikeError("Test-bot request failed.") from None
        if not isinstance(payload, dict):
            raise SpikeError("Test-bot response invalid.")
        if not response.is_success or payload.get("ok") is not True:
            description = payload.get("description")
            if (
                method == "sendMessage"
                and response.status_code == 400
                and isinstance(description, str)
                and "message thread not found" in description.lower().replace("_", " ")
            ):
                raise ThreadMissingError("Deleted topic rejected.")
            raise SpikeError("Test-bot request rejected.")
        return payload.get("result")


async def _prompt(message: str) -> None:
    await asyncio.to_thread(input, message + " Press Enter when ready: ")


async def _poll_reply(api, chat_id, thread_id, platform, offset, polls):
    for _ in range(polls):
        updates = await api.call(
            "getUpdates", offset=offset, timeout=10, allowed_updates=["message"]
        )
        if not isinstance(updates, list):
            raise SpikeError("Polling response invalid.")
        matched = None
        for update in updates:
            if not isinstance(update, dict) or type(update.get("update_id")) is not int:
                raise SpikeError("Polling response invalid.")
            offset = max(offset, update["update_id"] + 1)
            message = update.get("message") or {}
            if not isinstance(message, dict):
                continue
            chat = message.get("chat") or {}
            if (
                isinstance(chat, dict)
                and chat.get("id") == chat_id
                and message.get("text") == f"spike-{platform}"
            ):
                observed = message.get("message_thread_id")
                if observed is not None and type(observed) is not int:
                    raise SpikeError("Reply metadata invalid.")
                print(json.dumps({
                    "update_id": update["update_id"], "message_thread_id": observed,
                }))
                if observed != thread_id:
                    raise SpikeError("Reply did not arrive in the created topic.")
                matched = True
        if matched:
            return offset
    raise SpikeError("No matching client reply received within the polling window.")


async def run_spike(
    api: TestBotAPI,
    chat_id: int,
    *,
    prompt: Callable[[str], Awaitable[None]] = _prompt,
    polls: int = 6,
) -> None:
    me = await api.call("getMe")
    enabled = isinstance(me, dict) and me.get("has_topics_enabled") is True
    print(json.dumps({"has_topics_enabled": enabled}))
    if not enabled:
        raise SpikeError("Enable private topic mode on the test bot before this probe.")
    webhook = await api.call("getWebhookInfo")
    if not isinstance(webhook, dict) or webhook.get("url") != "":
        raise SpikeError("Use a test bot without a configured webhook.")
    chat = await api.call("getChat", chat_id=chat_id)
    if not isinstance(chat, dict) or chat.get("type") != "private" or chat.get("id") != chat_id:
        raise SpikeError("The probe requires an existing private test chat.")
    # Establish a watermark without printing or retaining the old queue's content.
    previous = await api.call("getUpdates", timeout=0, allowed_updates=["message"])
    if not isinstance(previous, list) or any(
        not isinstance(update, dict) or type(update.get("update_id")) is not int
        for update in previous
    ):
        raise SpikeError("Polling response invalid.")
    offset = max((update["update_id"] + 1 for update in previous), default=0)
    topic = await api.call("createForumTopic", chat_id=chat_id, name="Amigo topic spike")
    thread_id = topic.get("message_thread_id") if isinstance(topic, dict) else None
    if type(thread_id) is not int or thread_id <= 0:
        raise SpikeError("Topic response invalid.")
    print(json.dumps({"message_thread_id": thread_id}))
    await api.call(
        "sendMessage", chat_id=chat_id, message_thread_id=thread_id,
        text="Private-topic probe. Reply here from each requested client.",
    )
    for platform in ("desktop", "ios", "android"):
        await prompt(f"On Telegram {platform}, reply in the new topic with spike-{platform}.")
        offset = await _poll_reply(api, chat_id, thread_id, platform, offset, polls)
    await api.call("sendMessage", chat_id=chat_id, text="Probe sent without message_thread_id.")
    await prompt("Verify the unthreaded message's location, then delete the created topic.")
    try:
        await api.call(
            "sendMessage", chat_id=chat_id, message_thread_id=thread_id,
            text="Deleted-topic rejection probe.",
        )
    except ThreadMissingError:
        print(json.dumps({"deleted_topic_rejected": True}))
    else:
        raise SpikeError("Deleted-topic send unexpectedly succeeded; record as spike failure.")
    print("Probe passed. Record client observations for owner review.")


async def main(argv: list[str] | None = None) -> int:
    # HTTP client diagnostics may include the token-bearing URL. Keep them disabled.
    logging.getLogger("httpx").disabled = True
    logging.getLogger("httpcore").disabled = True
    parser = SafeParser(description=__doc__)
    parser.add_argument("--test-bot", action="store_true", help="Acknowledge disposable test bot")
    parser.add_argument("--chat-id", required=True, type=int, help="Positive private test chat ID")
    parser.add_argument("--polls", type=int, default=6, help="10-second polls per client, 1–12")
    try:
        args = parser.parse_args(argv)
        if not args.test_bot or args.chat_id <= 0 or not 1 <= args.polls <= 12:
            raise SpikeError("Test-bot acknowledgement and positive private chat required.")
        token = os.environ.get("TEST_BOT_TOKEN", "")
        if not token or not token.strip():
            raise SpikeError("TEST_BOT_TOKEN is required in the process environment.")
        if token == os.environ.get("TELEGRAM_BOT_TOKEN"):
            raise SpikeError("Refusing the configured application bot token.")
        async with httpx.AsyncClient(timeout=20, follow_redirects=False, trust_env=False) as client:
            await run_spike(TestBotAPI(token, client), args.chat_id, polls=args.polls)
        return 0
    except SpikeError as error:
        print(str(error))
        return 1
    except (KeyboardInterrupt, EOFError):
        print("Probe stopped by owner.")
        return 130
    except Exception:
        print("Probe failed; no provider details retained.")
        return 1


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("Probe stopped by owner.")
        sys.exit(130)
