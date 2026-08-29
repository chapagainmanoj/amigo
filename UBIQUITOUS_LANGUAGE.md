# Ubiquitous Language

This glossary supplements `CONTEXT.md` with product-launch terms. Runtime terms such as **Turn**,
**Task**, **Reminder**, **Session**, and **Turn Context** retain their definitions in `CONTEXT.md`.

## Identity and onboarding

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

## Release lifecycle

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

## Reliability evidence

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

## Task and Reminder lifecycle

| Term | Definition | Aliases to avoid |
|---|---|---|
| **Inbox** | Unscheduled Tasks with no `due_date`; excluded from daily progress until the participant chooses a planning day. | Backlog, today |
| **Planning Day** | The local calendar day in the participant's IANA timezone represented by a Task's `due_date`. | Created day |
| **Later** | The single user action that acknowledges the current Reminder and creates its policy-defined replacement while leaving the Task pending. | Snooze, defer |
| **Carried over** | Presentation of an overdue pending Task under its original `due_date`; midnight does not move it automatically. | Deferred, today's task |
| **Task Outcome** | One terminal Task state: `completed`, `skipped`, or `cancelled`. | Done flag, deletion |
| **Missed Reminder** | A Reminder more than 15 minutes late that is not delivered and becomes terminal while its Task remains pending. | Failed Task, overdue Task |

## Relationships

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

## Example dialogue

> **Founder:** “Can we call Amigo launched after account creation and pairing work?”

> **Developer:** “No. That proves **Pairing**, but **Activation** also requires a delivered and
> resolved test **Reminder**. Passing that internally contributes to **Internal Preflight**.”

> **Founder:** “When can we invite the first real users?”

> **Developer:** “After the **External Invitation Beta** gate has **Release Evidence**, including
> the **Representative Beta Burst** and a selected **Target Segment**.”

## Flagged ambiguities

- “Launch” has referred to internal testing, external beta, and public/customer availability.
  Use **Internal Preflight**, **External Invitation Beta**, or **Customer Readiness** explicitly.
- “User,” “account,” and “profile” have been used interchangeably. Use **Beta Participant** for
  the person, **Dashboard Account** for web authentication, and **Telegram Profile** for the
  linked Amigo record.
- “Onboarding complete” can mean account creation, pairing, profile setup, or first value. Use
  **Activation** only for the complete delivered-and-resolved test-Reminder outcome.
- “Snooze” and “defer” previously described separate or terminal actions. Use **Later** for the
  shared +60/+30/next-planning-day policy; the Task remains pending throughout.
