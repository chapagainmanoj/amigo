# Agentic Tool-Calling Loop (supersedes ADR 0001)

The sequential chain-of-LLM-calls pattern in `plan_message` (classify → extract → resolve time → per task) added 2-4 round-trips per user message, couldn't handle multi-intent messages ("done with slides, also call dentist"), and required manual orchestration code that duplicated what native tool-calling provides.

We replace this with a single Pydantic AI `Agent` that owns the tool-calling loop internally. The model sees the user message, decides which tools to call, observes results, and produces a final reply — all in one turn. Side effects execute through injected tool implementations (store, scheduler), keeping testability via fakes.

**Supersedes ADR 0001** ("agent plans, app executes"): The plan/execute split was right before native tool-calling existed. Preserving it now would force simulated tool observations, adding complexity without benefit. The new boundary: TurnProcessor owns the user-visible turn; the agent owns internal steps and executes side effects only through injected services.

## Considered Options

- **Keep plan/execute split (ADR 0001)** — Agent returns `AgentDecision` with `ToolCall` list, app layer executes. Rejected: requires faking tool observations in a loop, loses multi-intent handling, adds latency from sequential classify-then-extract calls.
- **Custom tool-calling loop on google.genai** — Write the loop manually (~50 lines). Preserves `ModelProvider` protocol. Rejected: reimplements what Pydantic AI already handles (retry, validation, observation formatting) and the dependency is already installed.
- **Pydantic AI Agent (chosen)** — Framework handles loop, retries, tool arg validation. Amigo wraps it behind an owned interface so Pydantic AI doesn't leak into TurnProcessor or bot layers.

## Consequences

- `plan_message`, `chat`, `extract_tasks`, `detect_status_update`, `resolve_reminder_time` collapse into one `handle_message` method.
- `AgentDecision`, `ToolCall`, `ExtractionResult`, `TaskStatusUpdate`, `ReminderTimeResolution` models are deleted. Tool schemas are inferred from function signatures.
- `ModelProvider` protocol and `GeminiProvider` are superseded by Pydantic AI's model handling.
- `ToolExecutor` is superseded by Pydantic AI's native tool dispatch.
- `TaskMatcher` is deleted — model picks `task_id` directly from tasks listed in context.
- Time resolution moves from LLM to deterministic `dateparser` inside the `schedule_reminder` tool.
- Testability preserved: fake store/scheduler/channel injected into agent, same pattern as before.
