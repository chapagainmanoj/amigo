"""Development-only Claude subscription adapter. No tools execute in the subprocess."""

import asyncio
import json
import os
from contextlib import suppress
from typing import Any

from jsonschema import Draft202012Validator
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelResponse,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

_FAILURE = "Development model request failed."
_TIMEOUT_SECONDS = 60
_MAX_OUTPUT_BYTES = 1_048_576
# PATH resolves the CLI; HOME/USER allow its normal local subscription/keychain identity;
# LANG/TERM preserve text/terminal behavior. Only the documented subscription OAuth token
# may supply explicit authentication. Application/API credentials and provider overrides never
# enter this subprocess. Tool access and session persistence remain disabled.
_SUBSCRIPTION_ENVIRONMENT = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "LANG",
        "TERM",
        "CLAUDE_CODE_OAUTH_TOKEN",
    }
)


def subscription_cli_environment() -> dict[str, str]:
    """Copy only OS identity/text settings and explicit subscription OAuth authentication."""
    return {name: value for name, value in os.environ.items() if name in _SUBSCRIPTION_ENVIRONMENT}


class ClaudeCLIError(RuntimeError):
    """Generic failure that never includes model content or subprocess diagnostics."""


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _json(value: str | bytes) -> Any:
    def invalid_constant(value: str) -> None:
        raise ValueError("Invalid JSON constant")

    return json.loads(value, object_pairs_hook=_object, parse_constant=invalid_constant)


def _parse_reply(output: bytes, info: AgentInfo, model_name: str) -> ModelResponse:
    """Accept only the Claude CLI envelope and the declared text/tool JSON contract."""
    try:
        if len(output) > _MAX_OUTPUT_BYTES:
            raise ValueError("Oversized response")
        envelope = _json(output)
        if (
            not isinstance(envelope, dict)
            or envelope.get("is_error") is not False
            or envelope.get("subtype") != "success"
            or not isinstance(envelope.get("result"), str)
        ):
            raise ValueError("Invalid envelope")
        reply = _json(envelope["result"])
        if not isinstance(reply, dict):
            raise ValueError("Invalid contract")
        if set(reply) == {"text"}:
            if not info.allow_text_output or not isinstance(reply["text"], str):
                raise ValueError("Invalid text")
            return ModelResponse(parts=[TextPart(reply["text"])], model_name=model_name)
        if set(reply) != {"tool_calls"}:
            raise ValueError("Invalid contract")
        calls = reply["tool_calls"]
        if not isinstance(calls, list) or not calls:
            raise ValueError("Invalid tool calls")
        tools = {tool.name: tool for tool in [*info.function_tools, *info.output_tools]}
        parts: list[ToolCallPart] = []
        for call in calls:
            if not isinstance(call, dict) or set(call) != {"name", "args"}:
                raise ValueError("Invalid tool call")
            name, args = call["name"], call["args"]
            if not isinstance(name, str) or name not in tools or not isinstance(args, dict):
                raise ValueError("Undeclared tool or invalid arguments")
            Draft202012Validator(tools[name].parameters_json_schema).validate(args)
            parts.append(ToolCallPart(tool_name=name, args=args))
        return ModelResponse(parts=parts, model_name=model_name)
    except Exception:
        raise ClaudeCLIError(_FAILURE) from None


def claude_cli_model(
    model_name: str, *, timeout_seconds: float = _TIMEOUT_SECONDS
) -> FunctionModel:
    """Build one-attempt requests with a timeout and a credential-free CLI environment."""
    if not model_name or model_name.startswith("-"):
        raise ClaudeCLIError(_FAILURE)
    reference = f"claude-cli:{model_name}"

    async def request(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        tools = [*info.function_tools, *info.output_tools]
        prompt = json.dumps(
            {
                "contract": (
                    'Return exactly one JSON object: {"text":"..."} or '
                    '{"tool_calls":[{"name":"declared_tool","args":{...}}]}. '
                    "No markdown, extra fields or commentary. Tool calls are proposals only. "
                    "Use only the supplied tools. Do not use any CLI tools."
                ),
                "instructions": info.instructions,
                "messages": json.loads(ModelMessagesTypeAdapter.dump_json(messages)),
                "tools": [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters_json_schema,
                    }
                    for tool in tools
                ],
            },
            ensure_ascii=False,
        )
        environment = subscription_cli_environment()
        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                "claude",
                "-p",
                "--output-format",
                "json",
                "--model",
                model_name,
                "--tools",
                "",
                "--no-session-persistence",
                "--safe-mode",
                "--strict-mcp-config",
                "--mcp-config",
                '{"mcpServers":{}}',
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env=environment,
            )
            output, _ = await asyncio.wait_for(
                process.communicate(prompt.encode()), timeout=timeout_seconds
            )
            if process.returncode != 0:
                raise ClaudeCLIError(_FAILURE)
            return _parse_reply(output, info, reference)
        except asyncio.CancelledError:
            raise
        except Exception:
            raise ClaudeCLIError(_FAILURE) from None
        finally:
            if process is not None and process.returncode is None:
                with suppress(ProcessLookupError):
                    process.kill()
                await process.wait()

    return FunctionModel(request, model_name=reference)
