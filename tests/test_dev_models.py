"""The development ladder is isolated from production and validates CLI tool proposals."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import TextPart, ToolCallPart
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.function import AgentInfo
from pydantic_ai.tools import ToolDefinition

from src.agent.catalogue import build_registry
from src.agent.claude_cli_model import ClaudeCLIError, _parse_reply, claude_cli_model
from src.agent.runtime import ModeRuntime, configured_model
from src.config import Settings
from src.runtime_config import (
    UnsafeProductionConfigurationError,
    require_agent_credentials,
    validate_runtime_configuration,
)


def _info():
    return AgentInfo(
        function_tools=[
            ToolDefinition(
                name="save",
                parameters_json_schema={
                    "type": "object",
                    "properties": {"title": {"type": "string"}},
                    "required": ["title"],
                    "additionalProperties": False,
                },
            )
        ],
        allow_text_output=True,
        output_tools=[],
        model_settings=None,
        model_request_parameters=ModelRequestParameters(),
        instructions="Fictional test",
    )


def _envelope(reply):
    return json.dumps({"is_error": False, "subtype": "success", "result": reply}).encode()


@pytest.mark.parametrize(
    "reply",
    [
        '{"text":"hello"}',
        '{"tool_calls":[{"name":"save","args":{"title":"Read"}}]}',
    ],
)
def test_cli_accepts_exact_text_or_valid_declared_tools(reply):
    response = _parse_reply(_envelope(reply), _info(), "claude-cli:sonnet")
    assert response.model_name == "claude-cli:sonnet"
    assert isinstance(response.parts[0], TextPart | ToolCallPart)


@pytest.mark.parametrize(
    "reply",
    [
        '```json\n{"text":"private"}\n```',
        '{"text":"private","extra":true}',
        '{"text":1}',
        '{"text":"private","text":"duplicate"}',
        '{"tool_calls":[]}',
        '{"tool_calls":[{"name":"shell","args":{}}]}',
        '{"tool_calls":[{"name":"save","args":{"title":1}}]}',
        '{"tool_calls":[{"name":"save","args":{"title":"private","extra":1}}]}',
        '{"tool_calls":[{"name":"save","args":{}}]}',
        '{"tool_calls":[{"name":"save","args":"private"}]}',
        '{"tool_calls":[{"name":"save","args":{"title":NaN}}]}',
    ],
)
def test_cli_rejects_malformed_or_undeclared_proposals_without_content(reply):
    with pytest.raises(ClaudeCLIError) as error:
        _parse_reply(_envelope(reply), _info(), "claude-cli:sonnet")
    assert str(error.value) == "Development model request failed."
    assert error.value.__suppress_context__


async def test_cli_subprocess_has_no_key_tools_or_persistence(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "private-key")
    process = SimpleNamespace(
        communicate=AsyncMock(return_value=(_envelope('{"text":"hello"}'), None)),
        returncode=0,
    )
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=process)) as spawn:
        result = await Agent(claude_cli_model("sonnet")).run("fictional test")
    assert result.output == "hello"
    args, kwargs = spawn.call_args
    assert args[:6] == ("claude", "-p", "--output-format", "json", "--model", "sonnet")
    assert args[args.index("--tools") + 1] == ""
    assert "--no-session-persistence" in args
    assert "--safe-mode" in args
    assert "--strict-mcp-config" in args
    assert args[args.index("--mcp-config") + 1] == '{"mcpServers":{}}'
    assert "ANTHROPIC_API_KEY" not in kwargs["env"]
    assert spawn.await_count == 1
    prompt = json.loads(process.communicate.call_args.args[0])
    assert prompt["messages"]


@pytest.mark.parametrize("failure", [asyncio.TimeoutError, asyncio.CancelledError])
async def test_cli_timeout_and_cancellation_kill_once_without_retry(failure):
    process = SimpleNamespace(
        communicate=AsyncMock(side_effect=failure),
        returncode=None,
        kill=Mock(),
        wait=AsyncMock(),
    )
    expected = asyncio.CancelledError if failure is asyncio.CancelledError else ClaudeCLIError
    with (
        patch("asyncio.create_subprocess_exec", AsyncMock(return_value=process)) as spawn,
        pytest.raises(expected),
    ):
        await Agent(claude_cli_model("sonnet")).run("fictional")
    process.kill.assert_called_once()
    process.wait.assert_awaited_once()
    assert spawn.await_count == 1


async def test_cli_nonzero_exit_and_launch_errors_are_generic():
    for process, error in [
        (
            SimpleNamespace(communicate=AsyncMock(return_value=(b"private", None)), returncode=1),
            None,
        ),
        (None, OSError("private-key")),
    ]:
        with (
            patch(
                "asyncio.create_subprocess_exec", AsyncMock(return_value=process, side_effect=error)
            ),
            pytest.raises(ClaudeCLIError, match="^Development model request failed.$"),
        ):
            await Agent(claude_cli_model("sonnet")).run("fictional")


async def test_factory_selects_and_caches_dev_providers_without_credentials():
    runtime = ModeRuntime(build_registry())
    settings = Settings(_env_file=None, dev_model="claude-cli:sonnet", google_api_key="")
    with patch("src.config.settings", settings):
        assert configured_model() == "claude-cli:sonnet"
        cli = await runtime.model_for("claude-cli:sonnet")
        assert cli.model_name == "claude-cli:sonnet"
        assert await runtime.model_for("claude-cli:sonnet") is cli
        ollama = await runtime.model_for("ollama:qwen3:4b")
        assert ollama.model_name == "qwen3:4b"
        assert str(ollama.client.base_url) == "http://localhost:11434/v1/"
        require_agent_credentials(settings)
        validate_runtime_configuration(settings)


@pytest.mark.parametrize("dev_model", ["claude-cli:sonnet", "ollama:qwen3:4b"])
def test_dev_credential_bypass_never_applies_in_production(dev_model):
    config = Settings(_env_file=None, app_env="production", dev_model=dev_model)
    with pytest.raises(UnsafeProductionConfigurationError, match="DEV_MODEL"):
        require_agent_credentials(config)
    with pytest.raises(UnsafeProductionConfigurationError, match="DEV_MODEL"):
        validate_runtime_configuration(config)


async def test_factory_refuses_cli_even_if_called_directly_in_production():
    with (
        patch("src.config.settings", Settings(_env_file=None, app_env="production")),
        pytest.raises(ValueError, match="development-only"),
    ):
        await ModeRuntime(build_registry()).model_for("claude-cli:sonnet")


@pytest.mark.parametrize(
    "envelope",
    [
        {"is_error": True, "subtype": "success", "result": '{"text":"private"}'},
        {"is_error": False, "subtype": "error_during_execution", "result": "private"},
        {"result": '{"text":"private"}'},
    ],
)
def test_cli_rejects_error_envelopes(envelope):
    with pytest.raises(ClaudeCLIError, match="^Development model request failed.$"):
        _parse_reply(json.dumps(envelope).encode(), _info(), "claude-cli:sonnet")


async def test_ollama_uses_configured_url_and_needs_no_google_key():
    config = Settings(
        _env_file=None,
        dev_model="ollama:qwen3:4b",
        google_api_key="",
        ollama_base_url="http://127.0.0.1:20000/v1",
    )
    with patch("src.config.settings", config):
        require_agent_credentials(config)
        model = await ModeRuntime(build_registry()).model_for(config.dev_model)
    assert str(model.client.base_url) == "http://127.0.0.1:20000/v1/"


@pytest.mark.parametrize("dev_model", ["claude-cli:", "ollama:"])
def test_empty_development_model_names_fail_before_execution(dev_model):
    config = Settings(_env_file=None, dev_model=dev_model, google_api_key="")
    with pytest.raises(UnsafeProductionConfigurationError, match="model name"):
        require_agent_credentials(config)
