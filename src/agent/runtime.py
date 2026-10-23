"""The Mode runtime: the owned model-execution boundary for every Mode.

It resolves and authorizes the Mode before anything is written, composes the Safety Core with the
Mode's instructions and Turn Context, and runs the model with only that Mode's Toolsets. Session
history and persistence belong to the application Turn orchestrator outside ``src/agent/``.
Pydantic AI stays behind this module and the Toolsets (ADR 0002).
"""

import time
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic_ai import Agent, RunContext
from pydantic_ai.capabilities import Instrumentation
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models import Model, infer_model
from pydantic_ai.providers import Provider, infer_provider
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.toolsets import AbstractToolset, CombinedToolset, PreparedToolset
from pydantic_ai.usage import RunUsage

from src.agent.catalogue import build_registry
from src.agent.modes import (
    PLACEHOLDER_FACTS,
    ModeDefinition,
    ModeUnavailableError,
    TurnFacts,
)
from src.agent.policies import (
    EntitlementPolicy,
    ExplicitThenDefault,
    RoutingPolicy,
    TieredEntitlements,
)
from src.agent.registry import ModeRegistry
from src.agent.safety import (
    safety_core_block,
    states_safety_core,
    without_participant_text,
)
from src.telemetry import TurnRecord, emit_turn_record, estimated_cost, framework_instrumentation
from src.tools.context import ToolContext
from src.tools.observed import ObservedToolset, executed_tools

FAILURE_REPLY = "Sorry, having trouble thinking right now. Try again in a minute? 🙏"


@dataclass(frozen=True)
class SessionMessage:
    """Framework-independent Session history supplied by the application layer."""

    role: str
    content: str


@dataclass(frozen=True)
class ModeRunResult:
    """Owned result boundary; provider message objects remain opaque to callers."""

    output: str
    messages: list[Any]
    usage: Any


def configured_model() -> str:
    """Resolve the configured model lazily so importing this module never reads settings."""
    from src.config import settings

    dev_model = settings.dev_model
    model = dev_model if isinstance(dev_model, str) and dev_model else settings.default_model
    # Pydantic AI uses provider-prefixed names for Google models
    if model.startswith("gemini-"):
        return f"google:{model}"
    return model


def _provider_for(name: str) -> Provider[Any]:
    """Google credentials come from Settings, which also reads .env, not just os.environ."""
    if name in ("google", "google-gla"):
        from src.config import settings

        return GoogleProvider(api_key=settings.google_api_key or None)
    if name == "anthropic":
        from pydantic_ai.providers.anthropic import AnthropicProvider

        from src.config import settings

        return AnthropicProvider(api_key=settings.anthropic_api_key)
    if name == "openai":
        from pydantic_ai.providers.openai import OpenAIProvider

        from src.config import settings

        return OpenAIProvider(api_key=settings.openai_api_key or None)
    if name == "deepseek":
        from pydantic_ai.providers.deepseek import DeepSeekProvider

        from src.config import settings

        return DeepSeekProvider(api_key=settings.deepseek_api_key or None)
    if name == "ollama":
        from pydantic_ai.providers.ollama import OllamaProvider

        from src.config import settings

        return OllamaProvider(base_url=settings.ollama_base_url)
    return infer_provider(name)


class ModeRuntime:
    """Runs Turns for every Mode in a registry under replaceable routing and entitlement."""

    def __init__(
        self,
        registry: ModeRegistry,
        *,
        routing: RoutingPolicy | None = None,
        entitlements: EntitlementPolicy | None = None,
    ):
        self.registry = registry
        self.routing = routing or ExplicitThenDefault()
        self.entitlements = entitlements or TieredEntitlements()
        self._agents: dict[str, Agent[ToolContext, str]] = {}
        self._models: dict[tuple[str, bool], Model] = {}
        self._states_safety_core: dict[str, bool] = {}
        self._model_override: ContextVar[Any | None] = ContextVar(
            f"mode_runtime_model_{id(self)}", default=None
        )

    @asynccontextmanager
    async def override(self, *, model: Any, fallback: Any | None = None) -> AsyncIterator[None]:
        """Substitute the model for every Turn run inside the block. For tests and evaluation."""
        token = self._model_override.set((model, fallback))
        try:
            yield
        finally:
            self._model_override.reset(token)

    async def resolve(self, context: ToolContext, requested_mode: str | None) -> ModeDefinition:
        """Pick and authorize the Mode for a Turn. Refuses before anything is written."""
        selected = await self.routing.select(context, requested_mode)
        mode = await self.registry.get(selected)
        if mode.status != "live":
            raise ModeUnavailableError(mode.id, mode.status, f"{mode.name} isn't available yet.")
        if not await self.entitlements.allows(context, mode):
            raise ModeUnavailableError(
                mode.id, "not entitled", f"{mode.name} isn't available on your account."
            )
        if mode.entry_guard is not None:
            refusal = await mode.entry_guard(context)
            if refusal:
                raise ModeUnavailableError(mode.id, "readiness", refusal)
        return mode

    async def instructions_for(self, mode: ModeDefinition, context: ToolContext) -> str:
        """The Safety Core, the Mode's own instructions, then its Turn Context sections."""
        context.mode_id = mode.id
        user = context.user
        timezone = user.get("timezone") or "UTC"
        facts = TurnFacts(
            participant_name=user.get("name") or "friend",
            local_time=context.clock.now_in_tz(timezone).strftime("%Y-%m-%d %H:%M %A"),
        )
        if mode.id not in self._states_safety_core:
            self._states_safety_core[mode.id] = states_safety_core(
                mode.instructions(PLACEHOLDER_FACTS)
            )
        own = mode.instructions(facts)
        # Both renders must state it. The placeholder render stops participant data standing in
        # for the Mode; the real render, with participant text removed, catches a Mode whose facts
        # push clauses out.
        stated = self._states_safety_core[mode.id] and states_safety_core(
            without_participant_text(own, (facts.participant_name,))
        )
        sections = [own if stated else safety_core_block() + own]
        for provider in mode.context:
            section = await provider(context)
            if section:
                sections.append(section)
        return "\n".join(sections)

    async def model_for(
        self,
        reference: Any = None,
        *,
        mode: ModeDefinition | None = None,
        context: ToolContext | None = None,
        resolve_only: bool = False,
    ) -> Any:
        """Resolve owner routing once, or build an explicitly supplied evaluation model."""
        if reference is None:
            from src.config import settings
            from src.model_routing import resolve_model

            reference = resolve_model(
                settings,
                mode_id=mode.id if mode else "daily",
                user_id=context.user["user_id"] if context else None,
            )
            # Existing declared primary policies remain supported below operator routing.
            if mode and mode.model.primary:
                from src.model_routing import configured_routes

                _, dev, modes, pins = configured_routes(settings)
                if (
                    not dev
                    and mode.id not in modes
                    and (context is None or context.user["user_id"] not in pins)
                ):
                    reference = mode.model.primary
        if resolve_only:
            return reference
        if not isinstance(reference, str):
            return reference
        from src.model_routing import normalize_model

        reference = normalize_model(reference)
        from src.config import settings
        from src.runtime_config import is_production

        production = is_production(settings)
        if reference.startswith("claude-cli:") and production:
            raise ValueError("Claude CLI is development-only")
        cache_key = (reference, production)
        model = self._models.get(cache_key)
        if model is None:
            if reference.startswith("claude-cli:"):
                from src.agent.claude_cli_model import claude_cli_model

                model = claude_cli_model(reference.partition(":")[2])
            elif reference.partition(":")[0] in {"google", "google-gla"}:
                from pydantic_ai.models.google import GoogleModel

                model_type = GoogleModel
                if not production:
                    from src.model_usage import LoggedGoogleModel

                    model_type = LoggedGoogleModel
                provider, _, model_name = reference.partition(":")
                model = model_type(model_name, provider=_provider_for(provider))
            elif reference.startswith("ollama:") and not production:
                from pydantic_ai.models.ollama import OllamaModel

                # Bound the offline development profile; disable hidden thinking on
                # boolean-thinking models so small local backups return promptly.
                model = OllamaModel(
                    reference.partition(":")[2],
                    provider=_provider_for("ollama"),
                    settings={
                        "max_tokens": 512,
                        "openai_reasoning_effort": "none",
                        "timeout": 60,
                    },
                )
            elif reference.partition(":")[0] in {"openai", "deepseek"}:
                from pydantic_ai.models.openai import OpenAIChatModel

                # Chat Completions explicitly; a bare "openai:" changes API in Pydantic AI 2.
                provider, _, model_name = reference.partition(":")
                model = OpenAIChatModel(model_name, provider=_provider_for(provider))
            else:
                model = infer_model(reference, _provider_for)
            self._models[cache_key] = model
        return model

    async def execution_model_for(self, mode: ModeDefinition, context: ToolContext) -> Any:
        """The resolved primary model, preserving explicit test/evaluation substitution."""
        override = self._model_override.get()
        if override:
            return override[0]
        return await self.model_for(mode=mode, context=context)

    async def agent_for(self, mode: ModeDefinition, *, fallback=False) -> Agent[ToolContext, str]:
        """One cached agent per Mode, offered only that Mode's Toolsets."""
        cache_key = mode.id + (":fallback" if fallback else "")
        agent = self._agents.get(cache_key)
        if agent is None:
            agent = Agent(
                deps_type=ToolContext,
                output_type=str,
                retries=0 if fallback else 1,
                toolsets=[ObservedToolset(_presented(mode))],
                capabilities=[Instrumentation(framework_instrumentation())],
            )

            # Instructions, not a system prompt: a system prompt is only injected when a run
            # starts with empty history, so it vanished from every Turn after a Session's first.
            @agent.instructions
            async def _instructions(ctx: RunContext[ToolContext]) -> str:
                return await self.instructions_for(mode, ctx.deps)

            self._agents[cache_key] = agent
        return agent

    async def run_turn(
        self,
        context: ToolContext,
        text: str,
        *,
        requested_mode: str | None = None,
        model: Any | None = None,
        history: Sequence[SessionMessage] = (),
    ) -> ModeRunResult:
        """Resolve and execute a Turn without persisting any Session Messages."""
        mode = await self.resolve(context, requested_mode)
        return await self.run_mode(mode, context, text, model=model, history=history)

    async def run_mode(
        self,
        mode: ModeDefinition,
        context: ToolContext,
        text: str,
        *,
        model: Any | None,
        history: Sequence[SessionMessage] = (),
    ) -> ModeRunResult:
        """Execute an already-authorized Mode using supplied, framework-neutral history."""
        message_history: list[ModelRequest | ModelResponse] = []
        for message in history:
            if message.role == "user":
                message_history.append(
                    ModelRequest(parts=[UserPromptPart(content=message.content)])
                )
            else:
                message_history.append(ModelResponse(parts=[TextPart(content=message.content)]))

        context.mode_id = mode.id
        context.mode_registry = self.registry
        agent = await self.agent_for(mode)
        requested = await self.model_for(mode=mode, context=context, resolve_only=True)
        override = self._model_override.get()
        primary = model or (override[0] if override else None) or requested
        fallback = (
            None
            if model is not None
            else ((override[1] if override else None) or mode.model.fallback)
        )
        names: list[str] = []
        token = executed_tools.set(names)
        started = time.perf_counter()
        usage = RunUsage()
        fallback_used = False
        answering = None
        error_class = None
        outcome = "failed"
        cost = None
        try:
            try:
                for attempt in range(2):
                    try:
                        result = await agent.run(
                            text,
                            model=await self.model_for(primary),
                            deps=context,
                            message_history=message_history or None,
                            model_settings=mode.model.settings,
                            usage=usage,
                        )
                        break
                    except Exception as error:
                        if attempt or names or not provider_unavailable(error):
                            raise
            except Exception as error:
                if not (fallback and not names and provider_unavailable(error)):
                    raise
                fallback_used = True
                # One request chain on the fallback, never another primary attempt or replay.
                # Failed primary usage is retained separately and cannot be understated as free.
                primary_cost = estimated_cost(usage, requested)
                fallback_usage = RunUsage()
                try:
                    fallback_agent = await self.agent_for(mode, fallback=True)
                    result = await fallback_agent.run(
                        text,
                        model=await self.model_for(fallback),
                        deps=context,
                        message_history=message_history or None,
                        model_settings=mode.model.settings,
                        usage=fallback_usage,
                    )
                finally:
                    usage.incr(fallback_usage)
                fallback_responses = [
                    m for m in result.new_messages() if isinstance(m, ModelResponse)
                ]
                observed_fallback = (
                    fallback_responses[-1].model_name if fallback_responses else None
                )
                fallback_cost = estimated_cost(fallback_usage, observed_fallback)
                if primary_cost is not None and fallback_cost is not None:
                    cost = primary_cost + fallback_cost
            responses = [m for m in result.new_messages() if isinstance(m, ModelResponse)]
            answering = responses[-1].model_name if responses else None
            if not fallback_used:
                cost = estimated_cost(usage, answering)
            outcome = "ok"
            return ModeRunResult(
                output=result.output,
                messages=result.new_messages(),
                usage=usage,
            )
        except Exception as error:
            error_class = type(error).__name__
            raise
        finally:
            executed_tools.reset(token)
            emit_turn_record(
                TurnRecord(
                    schema_version=1,
                    turn_id=context.turn_id,
                    user_id=context.user["user_id"],
                    mode_id=mode.id,
                    entered_by=context.entered_by,
                    requested_model=requested,
                    answering_model=answering,
                    fallback_used=fallback_used,
                    tools=tuple(names),
                    outcome=outcome,
                    error_class=error_class,
                    latency_ms=round((time.perf_counter() - started) * 1000, 2),
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    estimated_cost_usd=cost,
                )
            )


def provider_unavailable(error: Exception) -> bool:
    """Only transport/provider availability errors qualify; refusal and validation never do."""
    return isinstance(error, httpx.ConnectError | httpx.TimeoutException) or (
        isinstance(error, ModelHTTPError)
        and (error.status_code in (408, 429) or 500 <= error.status_code <= 599)
    )


def _presented(mode: ModeDefinition) -> AbstractToolset[ToolContext]:
    """The Mode's Toolsets as one Toolset, presented in the Mode's declared Tool order."""
    toolsets = list(mode.toolsets)
    if mode.handoffs:
        from src.tools.handoffs import HANDOFFS

        if HANDOFFS not in toolsets:
            toolsets.append(HANDOFFS)
    combined: AbstractToolset[ToolContext] = CombinedToolset(toolsets)
    if not mode.tool_order:
        return combined
    rank = {name: index for index, name in enumerate(mode.tool_order)}

    async def in_declared_order(ctx, tool_defs):
        return sorted(tool_defs, key=lambda tool: rank.get(tool.name, len(rank)))

    return PreparedToolset(combined, in_declared_order)


default_runtime = ModeRuntime(build_registry())
