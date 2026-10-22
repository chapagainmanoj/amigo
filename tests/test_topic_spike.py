"""The topic spike uses only a disposable bot; all HTTP is mocked here."""

import json

import httpx
import pytest

from scripts import spike_private_topics as spike

TOKEN = "123:private-test-token"
PRIVATE = "private-message-and-provider-error"


def _update(update_id, text, *, thread=77, chat_id=42):
    return {
        "update_id": update_id,
        "message": {
            "chat": {"id": chat_id}, "message_thread_id": thread, "text": text,
        },
    }


async def _prompt(_):
    pass


class Scenario:
    def __init__(self, *, failure=None):
        self.calls = []
        self.poll = 0
        self.sends = 0
        self.failure = failure

    async def handle(self, request):
        method = request.url.path.rsplit("/", 1)[-1]
        params = json.loads(request.content)
        self.calls.append((method, params))
        if self.failure == method:
            return httpx.Response(401, json={"ok": False, "description": TOKEN + PRIVATE})
        if method == "getMe":
            result = {"has_topics_enabled": True}
        elif method == "getWebhookInfo":
            result = {"url": ""}
        elif method == "getChat":
            result = {"type": "private", "id": 42}
        elif method == "createForumTopic":
            result = {"message_thread_id": 77}
        elif method == "sendMessage":
            self.sends += 1
            if self.sends == 3:
                return httpx.Response(400, json={
                    "ok": False, "description": "Bad Request: message thread not found " + PRIVATE,
                })
            result = {"message_id": self.sends}
        elif method == "getUpdates":
            self.poll += 1
            result = (
                [_update(1, PRIVATE)] if self.poll == 1
                else [_update(self.poll, f"spike-{('desktop', 'ios', 'android')[self.poll - 2]}")]
            )
        else:
            raise AssertionError(method)
        return httpx.Response(200, json={"ok": True, "result": result})


async def _run_scenario(scenario):
    async with httpx.AsyncClient(transport=httpx.MockTransport(scenario.handle)) as client:
        await spike.run_spike(spike.TestBotAPI(TOKEN, client), 42, prompt=_prompt, polls=1)


async def test_all_stages_and_metadata_only_output(capsys):
    scenario = Scenario()
    await _run_scenario(scenario)
    output = capsys.readouterr().out
    assert TOKEN not in output and PRIVATE not in output and "https:" not in output
    records = [json.loads(line) for line in output.splitlines() if line.startswith("{")]
    assert records == [
        {"has_topics_enabled": True}, {"message_thread_id": 77},
        {"update_id": 2, "message_thread_id": 77},
        {"update_id": 3, "message_thread_id": 77},
        {"update_id": 4, "message_thread_id": 77},
        {"deleted_topic_rejected": True},
    ]
    sends = [params for method, params in scenario.calls if method == "sendMessage"]
    assert sends[0]["message_thread_id"] == sends[2]["message_thread_id"] == 77
    assert "message_thread_id" not in sends[1]
    offsets = [
        p["offset"] for method, p in scenario.calls if method == "getUpdates" and "offset" in p
    ]
    assert offsets == [2, 3, 4]


@pytest.mark.parametrize("method", ["getMe", "getWebhookInfo", "getChat", "createForumTopic",
                                    "sendMessage", "getUpdates"])
async def test_provider_errors_are_generic(method, capsys):
    with pytest.raises(spike.SpikeError) as error:
        await _run_scenario(Scenario(failure=method))
    assert TOKEN not in str(error.value) and PRIVATE not in str(error.value)
    assert PRIVATE not in capsys.readouterr().out


@pytest.mark.parametrize("result,method", [
    ({"has_topics_enabled": False}, "getMe"),
    ({"url": "https://secret.example/" + TOKEN}, "getWebhookInfo"),
    ({"type": "supergroup", "id": 42}, "getChat"),
])
async def test_preconditions_refuse_before_topic_creation(result, method):
    scenario = Scenario()

    async def handler(request):
        if request.url.path.endswith("/" + method):
            scenario.calls.append((method, {}))
            return httpx.Response(200, json={"ok": True, "result": result})
        return await scenario.handle(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(spike.SpikeError):
            await spike.run_spike(spike.TestBotAPI(TOKEN, client), 42, prompt=_prompt)
    assert not any(name == "createForumTopic" for name, _ in scenario.calls)


@pytest.mark.parametrize("observed", [None, 99, PRIVATE])
async def test_wrong_or_invalid_thread_cannot_pass(observed, capsys):
    scenario = Scenario()

    async def handler(request):
        if request.url.path.endswith("/getUpdates") and scenario.poll:
            return httpx.Response(200, json={
                "ok": True, "result": [_update(2, "spike-desktop", thread=observed)],
            })
        return await scenario.handle(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(spike.SpikeError):
            await spike.run_spike(spike.TestBotAPI(TOKEN, client), 42, prompt=_prompt, polls=1)
    assert PRIVATE not in capsys.readouterr().out


async def test_deleted_topic_send_must_fail_specifically():
    scenario = Scenario()

    async def handler(request):
        if request.url.path.endswith("/sendMessage") and scenario.sends == 2:
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 3}})
        return await scenario.handle(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(spike.SpikeError, match="unexpectedly succeeded"):
            await spike.run_spike(spike.TestBotAPI(TOKEN, client), 42, prompt=_prompt, polls=1)


async def test_network_failure_never_exposes_token_url():
    async def handler(request):
        raise httpx.ConnectError(str(request.url) + PRIVATE, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(spike.SpikeError) as error:
            await spike.TestBotAPI(TOKEN, client).call("getMe")
    assert str(error.value) == "Test-bot request failed."


@pytest.mark.parametrize("args", [
    ["--token", TOKEN, "--chat-id", "42"],
    ["--token", TOKEN, "--test-bot", "--chat-id", "-42"],
    ["--token", TOKEN, "--test-bot", "--chat-id", PRIVATE],
    ["--token", TOKEN, "--test-bot", "--chat-id", "42", "--polls", "0"],
])
async def test_cli_validation_does_not_echo_private_arguments(args, capsys):
    assert await spike.main(args) == 1
    output = capsys.readouterr().out
    assert TOKEN not in output and PRIVATE not in output


async def test_process_environment_production_token_is_refused(monkeypatch, capsys):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    assert await spike.main(["--token", TOKEN, "--test-bot", "--chat-id", "42"]) == 1
    assert capsys.readouterr().out == "Refusing the configured application bot token.\n"


@pytest.mark.parametrize("body", [PRIVATE, "[]", '{"ok":true}'])
async def test_malformed_provider_payload_is_safe(body):
    async def handler(request):
        return httpx.Response(200, text=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(spike.SpikeError) as error:
            await spike.run_spike(spike.TestBotAPI(TOKEN, client), 42, prompt=_prompt, polls=1)
    assert PRIVATE not in str(error.value)


async def test_unrelated_chat_reply_and_private_messages_do_not_pass_or_print(capsys):
    scenario = Scenario()

    async def handler(request):
        if request.url.path.endswith("/getUpdates") and scenario.poll:
            return httpx.Response(200, json={"ok": True, "result": [
                _update(2, "spike-desktop", chat_id=99), _update(3, PRIVATE),
            ]})
        return await scenario.handle(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(spike.SpikeError, match="No matching client reply"):
            await spike.run_spike(spike.TestBotAPI(TOKEN, client), 42, prompt=_prompt, polls=1)
    output = capsys.readouterr().out
    assert PRIVATE not in output and '"update_id"' not in output
    assert scenario.sends == 1


async def test_deleted_topic_other_errors_cannot_pass(capsys):
    scenario = Scenario()

    async def handler(request):
        if request.url.path.endswith("/sendMessage") and scenario.sends == 2:
            return httpx.Response(403, json={"ok": False, "description": TOKEN + PRIVATE})
        return await scenario.handle(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(spike.SpikeError, match="request rejected"):
            await spike.run_spike(spike.TestBotAPI(TOKEN, client), 42, prompt=_prompt, polls=1)
    output = capsys.readouterr().out
    assert "deleted_topic_rejected" not in output and PRIVATE not in output
