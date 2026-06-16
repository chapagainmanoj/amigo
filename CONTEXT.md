# Amigo

A conversational AI friend delivered as a Telegram bot that helps a single user stay on track with their day through task extraction, reminders, and session-aware context.

## Language

**Turn**:
One user message through to one final reply, regardless of how many internal LLM steps or tool calls happen in between.
_Avoid_: Round, exchange, interaction

**Step**:
A single LLM invocation within a turn. The model may take multiple steps (calling tools, observing results) before producing the turn's final reply.
_Avoid_: Call, round-trip

**Tool**:
A side-effect-bearing function the agent can invoke during a turn — creating tasks, scheduling reminders, updating status. Tools receive runtime context (user, session, timezone) via injection, not from the model.
_Avoid_: Action, command, handler

**Task**:
Something the user intends to do, extracted from conversation. Has a title, category, status, and optional reminder time.
_Avoid_: Todo, item, goal

**Reminder**:
A scheduled notification tied to a task, delivered at a resolved time. Has a snooze escalation policy (1hr → 30min → defer).
_Avoid_: Alert, notification, alarm

**Session**:
A bounded conversation window. Rolls over at local midnight or after inactivity timeout. Typed: `morning_planning`, `default`, `proactive_checkin`.
_Avoid_: Conversation, thread, chat

**Turn Context**:
Facts about the current turn assembled by TurnProcessor and passed to the agent: user profile, session metadata, pending tasks, timezone. The agent uses this to compose prompts and make tool decisions. TurnProcessor provides facts; the agent decides behavior.
_Avoid_: Request context, execution context

**Tool Context**:
Runtime dependencies injected into tool functions: user_id, chat_id, session_id, timezone. Not visible to the model — injected by the agent framework.
_Avoid_: Execution context, tool environment
