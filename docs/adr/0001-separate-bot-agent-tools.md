# ADR 0001: Separate Bot, Agent, and Tools

## Status

Superseded by [ADR 0002](0002-agentic-tool-calling-loop.md)

## Context

Amigo currently has the right pieces for a clean reminder flow, but the
responsibilities are blended across a few classes:

- `TurnProcessor` routes authenticated messages, detects task/status intent,
  creates tasks, schedules reminders, stores messages, and sends replies.
- `AmigoAgent` performs LLM-backed chat, task extraction, reminder-time
  resolution, and status detection.
- `ReminderActions` coordinates reminder persistence/scheduling and also owns
  Done/Skip/Later callback handling.
- `ReminderScheduler` wraps APScheduler and publishes reminder notifications
  back through `MessageChannel`.

That shape works for Phase 1a, but it makes future agent capabilities harder
to test and reason about because classification, planning, and side effects are
not explicit boundaries.

## Decision

Separate the runtime flow into these layers:

```text
Bot -> ConversationApp/TurnProcessor -> AgentPlanner -> ToolExecutor -> Tools
    -> Scheduler/Store -> Channel
```

- Bot/channel code adapts Telegram or CLI input/output.
- The agent classifies the user message, extracts details, and returns an
  `AgentDecision` with requested `ToolCall`s.
- The app layer owns session/context orchestration and executes requested tools.
- Tools perform side effects such as creating tasks, updating task status,
  cancelling reminders, and scheduling reminders.
- `ReminderScheduler` stays narrow: schedule, cancel, reload, and fire
  reminders through the channel abstraction.

The agent may decide which tools are needed, but it must not execute
side-effectful actions itself.

## Consequences

- Task/reminder behavior becomes easier to unit test at the planning and tool
  boundaries.
- New capabilities can be added by introducing tool calls instead of expanding
  `TurnProcessor`.
- The current behavior remains intact while the system gains a clearer path
  toward LLM tool calling later.
- There is slightly more plumbing: structured decisions, tool call arguments,
  and sequential tool execution with references between tool results.
