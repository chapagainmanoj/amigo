# Amigo

An AI accountability companion delivered through Telegram with a paired dashboard. The current
prototype supports conversational Task capture, participant-scheduled Reminders, and
Session-scoped context; it is not a human friend, durable-Memory system, clinical service, or
multi-channel product.

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
A bounded conversation window. It rolls over at local midnight or after an inactivity timeout.
Current prototype types include `morning_planning`, `check_in`, `evening`, and the store's default
`casual` value. Session types are context metadata, not user-selectable Modes.
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

## Launch vocabulary

Product-launch terms, using the runtime definitions above for **Turn**, **Task**,
**Reminder**, **Session** and **Turn Context**.

### Identity and onboarding

| Term | Definition | Aliases to avoid |
|---|---|---|
| **Dashboard Account** | The authenticated web identity from which a person begins Amigo onboarding. | Account, login |
| **Telegram Profile** | The Amigo user record linked to one Telegram chat identity. | Bot account, Telegram account |
| **Pairing** | The expiring, single-use process that links a **Dashboard Account** to a **Telegram Profile**. | Connection, sync |
| **Beta Participant** | A person admitted to the supported external invitation beta. | Customer, tester, user |
| **Activation** | Completion of pairing followed by one successfully delivered and resolved test **Reminder**. | Signup, onboarding completion |
| **Activation Journey** | The dashboard-led, resumable sequence from verified Dashboard Account through a delivered and resolved test Reminder reflected on the dashboard. | Signup flow, pairing flow |
| **Preflight Usability Panel** | Five separately disclosed participants who test the Activation Journey in staging before Gate B; they are not yet 30-day Beta Participants. | Beta cohort, pilot users |
| **Intervention Log** | The privacy-minimized record of founder help, its trigger, journey stage, type, time, and outcome. | Support notes, research transcript |
| **Unassisted Activation** | Activation completed without a founder hint, walkthrough, reset, admin mutation, or participant action performed by the founder. | Activation, successful onboarding |

### Release lifecycle

| Term | Definition | Aliases to avoid |
|---|---|---|
| **Internal Preflight** | Gate A evidence that Amigo's narrow core path is safe and reliable enough for internal verification. | Alpha, launch |
| **External Invitation Beta** | Gate B release to a small selected cohort with founder support and explicit stop conditions. | Public beta, launch |
| **Customer Readiness** | Gate C evidence that Amigo can be presented or opened more broadly with self-service rights, legal review, and customer proof. | Beta readiness, launch |
| **Development Environment** | The cost-minimized internal environment where sleeping infrastructure and unreliable scheduled execution are accepted and no external participant depends on Amigo. | Production, beta runtime |
| **Beta Runtime** | The always-on, instrumented, capacity-bounded topology that must pass Gate B before the first external invitation. | Development server, production someday |
| **Core Loop** | A **Beta Participant** expresses a **Task**, Amigo schedules and delivers its **Reminder**, and the participant resolves it. | Reminder flow, happy path |
| **Roadmap Capability** | A planned capability that has not passed its release gate and must not be presented as shipped. | Coming-soon feature, beta feature |
| **Target Segment** | The narrowly defined group sharing the triggering problem that the first beta is intended to validate. | Audience, everyone, users |
| **Product Claim** | A customer-facing statement about Amigo's current capability, outcome, or safety role. | Vision, aspiration |
| **Hosted Subscription** | The founder-operated paid Amigo service; it does not imply supported self-hosting, managed deployment, or enterprise installation. | Open core, managed service |
| **Pricing Hypothesis** | A revisable price tested through completed payments and measured cost/support evidence, not a permanent promise. | Price, founding deal |
| **Commercial Validation** | At least two eligible beta graduates complete an unsubsidized first-month payment while Customer Readiness and sustainability thresholds pass. | Interest, willingness to pay |
| **Memory Candidate** | An ephemeral suggestion that may become Memory only after the participant confirms its preview; it is never retrieved as durable Memory before confirmation. | Inferred memory, learned fact |

### Reliability evidence

| Term | Definition | Aliases to avoid |
|---|---|---|
| **Reminder Delivery Success** | A scheduled **Reminder** accepted by its channel within the documented delivery window. | Sent, worked |
| **Reminder Lateness** | The elapsed time between a **Reminder**'s scheduled timestamp and successful channel delivery. | Delay, latency |
| **Eligible Reminder** | A valid future Reminder occurrence that remains active when its scheduled instant arrives and therefore enters the reliability denominator. | Send attempt, pending row |
| **Representative Beta Burst** | A staging workload matching documented invitation-cohort concurrency and due-Reminder assumptions. | Load test, stress test |
| **Release Evidence** | A dated, attributable test result, staging observation, reviewed document, or runbook proving a gate criterion. | Done, checked |
| **Model Evaluation Case** | A versioned, non-sensitive scenario with expected and prohibited Tools, required clarification, acceptable response properties, and expected resulting state. | Prompt test, example chat |
| **Model Hard Invariant** | A model behavior whose single occurrence fails the applicable release gate, while deterministic code independently enforces the underlying security, lifecycle, or safety rule. | Low score, edge case |
| **Model Evaluation Run** | One predeclared execution of every applicable case and all three repetitions against an exact release candidate and recorded model inputs. | Retry, sample |

### Task and Reminder lifecycle

| Term | Definition | Aliases to avoid |
|---|---|---|
| **Inbox** | Unscheduled Tasks with no `due_date`; excluded from daily progress until the participant chooses a planning day. | Backlog, today |
| **Planning Day** | The local calendar day in the participant's IANA timezone represented by a Task's `due_date`. | Created day |
| **Later** | The single user action that acknowledges the current Reminder and creates its policy-defined replacement while leaving the Task pending. | Snooze, defer |
| **Carried over** | Presentation of an overdue pending Task under its original `due_date`; midnight does not move it automatically. | Deferred, today's task |
| **Task Outcome** | One terminal Task state: `completed`, `skipped`, or `cancelled`. | Done flag, deletion |
| **Missed Reminder** | A Reminder more than 15 minutes late that is not delivered and becomes terminal while its Task remains pending. | Failed Task, overdue Task |

### Relationships

- One **Dashboard Account** pairs with one **Telegram Profile** for the invitation beta.
- A **Beta Participant** reaches **Activation** only after completing one **Core Loop**.
- The **Activation Journey** resumes at its first incomplete step and cannot mark **Activation**
  complete from scheduling, timeout, or delivery failure alone.
- A **Preflight Usability Panel** run contributes to Gate-B usability evidence only when any
  founder help is captured in the **Intervention Log** and excluded from **Unassisted Activation**.
- **Internal Preflight** precedes **External Invitation Beta**, which precedes **Customer Readiness**.
- The **Development Environment** may support internal dogfooding, but only the **Beta Runtime** may
  host an **External Invitation Beta**.
- A **Roadmap Capability** becomes shipped only after its release gate has sufficient **Release Evidence**.
- A **Pricing Hypothesis** becomes **Commercial Validation** only through completed payment for the
  **Hosted Subscription** while the Customer Readiness evidence remains valid.
- A **Memory Candidate** remains ephemeral and cannot influence a Turn until a participant confirms
  it as **Memory**.
- The **Representative Beta Burst** tests the workload assumptions for the **External Invitation Beta**.
- A **Model Evaluation Run** produces **Release Evidence** only when every **Model Hard Invariant**
  and independently scored category passes its applicable threshold.

### Example dialogue

> **Founder:** “Can we call Amigo launched after account creation and pairing work?”

> **Developer:** “No. That proves **Pairing**, but **Activation** also requires a delivered and
> resolved test **Reminder**. Passing that internally contributes to **Internal Preflight**.”

> **Founder:** “When can we invite the first real users?”

> **Developer:** “After the **External Invitation Beta** gate has **Release Evidence**, including
> the **Representative Beta Burst** and a selected **Target Segment**.”

### Flagged ambiguities

- “Launch” has referred to internal testing, external beta, and public/customer availability.
  Use **Internal Preflight**, **External Invitation Beta**, or **Customer Readiness** explicitly.
- “User,” “account,” and “profile” have been used interchangeably. Use **Beta Participant** for
  the person, **Dashboard Account** for web authentication, and **Telegram Profile** for the
  linked Amigo record.
- “Onboarding complete” can mean account creation, pairing, profile setup, or first value. Use
  **Activation** only for the complete delivered-and-resolved test-Reminder outcome.
- “Snooze” and “defer” previously described separate or terminal actions. Use **Later** for the
  shared +60/+30/next-planning-day policy; the Task remains pending throughout.
