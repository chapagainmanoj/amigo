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
    ActivatedParticipants,
    EntitlementPolicy,
    ExplicitThenDefault,
    RoutingPolicy,
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

    model = settings.default_model
    # Pydantic AI uses provider-prefixed names for Google models
    if model.startswith("gemini-"):
        return f"google:{model}"
    return model


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
        self.entitlements = entitlements or ActivatedParticipants()
        self._agents: dict[str, Agent[ToolContext, str]] = {}
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
        return mode

    async def instructions_for(self, mode: ModeDefinition, context: ToolContext) -> str:
        """The Safety Core, the Mode's own instructions, then its Turn Context sections."""
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

        agent = await self.agent_for(mode)
        requested = mode.model.primary or configured_model()
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
                            model=primary,
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
                        model=fallback,
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
    combined: AbstractToolset[ToolContext] = CombinedToolset(list(mode.toolsets))
    if not mode.tool_order:
        return combined
    rank = {name: index for index, name in enumerate(mode.tool_order)}

    async def in_declared_order(ctx, tool_defs):
        return sorted(tool_defs, key=lambda tool: rank.get(tool.name, len(rank)))

    return PreparedToolset(combined, in_declared_order)


default_runtime = ModeRuntime(build_registry())
