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
Something the user intends to do, extracted from conversation. Has a title, category, canonical
state (`pending`, `completed`, `skipped`, or `cancelled`), optional planning `due_date`, and zero or
one active Reminder. A Task without a planning day belongs to Inbox. `overdue` and `deferred` are
conditions/events, not states.
_Avoid_: Todo, item, goal

**Reminder**:
A scheduled notification tied to a Task, delivered at an exact resolved instant. The **Later**
policy acknowledges the current Reminder and creates a replacement after 1 hour, then 30 minutes,
then on the next local planning day at wake time. A Reminder row never transitions from a terminal
state back to pending.
_Avoid_: Alert, notification, alarm

**Session**:
A bounded conversation window. Rolls over at local midnight or after inactivity timeout. Typed: `morning_planning`, `default`, `proactive_checkin`.
_Avoid_: Conversation, thread, chat

**Memory**:
A durable, participant-confirmed fact used to preserve useful continuity across Sessions. A Message,
Session summary, or unconfirmed model inference is not Memory. Initial eligible categories are a
preference, routine or constraint, ongoing goal or project, and minimal task-relevant personal
context.
_Avoid_: Conversation history, transcript, session summary, inferred profile

**Mode**:
A temporary, participant-entered interaction contract within a Session that constrains purpose,
available Tools, context, and behavior. Daily is the default workspace; Recommender, Coach, and
Reflect are specialized Modes. A persistent program or preference is not an active Mode.
_Avoid_: Persona, personality, hidden router, feature page

**Interaction Style**:
The participant-controlled warmth, directiveness, verbosity, and challenge settings that shape
Amigo's expression across Modes. It is neither Memory nor an inferred personality profile.
_Avoid_: Coaching profile, personality, mood model

**Coaching Program**:
A bounded, participant-approved Coach Mode program for one chosen goal or habit, with an explicit
success measure, check-in cadence, duration, progress review, and stop controls. It may persist
across Sessions even though Coach Mode itself does not remain active.
_Avoid_: Treatment plan, streak, active mode, expert coaching

**Mood Entry**:
A participant-entered mood label with optional intensity and note, used for personal journaling.
It is not an inferred mood, symptom score, diagnosis, health profile, or durable Memory.
_Avoid_: Mood score, assessment, screening result, emotional profile

**Wellbeing Exercise**:
A bounded, participant-chosen non-clinical reflective or self-regulation activity. It makes no
treatment claim and is not therapy.
_Avoid_: Intervention, treatment, CBT treatment, therapy exercise

**Crisis Referral**:
A limitation-first response that directs a person to a verified crisis line, local emergency
service, emergency department, or trusted nearby person. It is not monitoring, risk assessment,
dispatch, or a crisis service provided by Amigo.
_Avoid_: Crisis support, escalation, intervention, safety monitoring

**Messaging Channel**:
An external service that carries conversational Messages and Reminders between a participant and
Amigo, such as Telegram or WhatsApp.
_Avoid_: Voice, dashboard, mobile app, surface

**Interaction Modality**:
The form in which a participant communicates within a supported surface, such as text or voice.
_Avoid_: Channel, app

**Client Surface**:
An Amigo-operated application interface such as the dashboard, PWA, or native mobile app.
_Avoid_: Messaging channel, modality

**Surface Expansion**:
The evidence-gated portfolio for adding Messaging Channels, Interaction Modalities, and Client
Surfaces without fragmenting identity or the Core Loop.
_Avoid_: Channel expansion

**Primary Messaging Channel**:
The participant-selected linked Messaging Channel that receives proactive Messages and Reminders.
Conversational replies may return through any linked channel, but proactive delivery does not fan
out by default.
_Avoid_: Default app, notification channel, user identity

**Turn Context**:
Facts about the current turn assembled by TurnProcessor and passed to the agent: user profile, session metadata, pending tasks, timezone. The agent uses this to compose prompts and make tool decisions. TurnProcessor provides facts; the agent decides behavior.
_Avoid_: Request context, execution context

**Tool Context**:
Runtime dependencies injected into tool functions: user_id, chat_id, session_id, timezone. Not visible to the model — injected by the agent framework.
_Avoid_: Execution context, tool environment
