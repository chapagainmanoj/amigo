# What Is Amigo?

## Current Product

Amigo is an AI accountability companion for adults who struggle to follow through on everyday
Tasks and stop using conventional task apps.

The invitation-beta promise is deliberately narrow:

> Tell Amigo what you need to do. It turns the conversation into a Task and sends a Telegram
> Reminder at the time you choose, with simple Done, Skip, or Later controls.

A participant starts on the web dashboard, creates an account, and pairs Telegram. Telegram is
the conversation and Reminder surface; the dashboard is the account, connection, and prototype
review surface.

The [capability matrix](capability-matrix.md) is authoritative whenever this document, a demo, or
roadmap language becomes ambiguous.

## Problem

Most task tools assume people will repeatedly open an app, organize a list, and remember to review
it. That is a poor fit for someone who captures intentions in conversation but loses momentum
between planning and action.

Amigo tests a simpler hypothesis: conversational capture plus a requested follow-up may make it
easier to act than maintaining another task system.

This problem and solution are hypotheses until the external beta produces activation, retention,
outcome, and willingness-to-pay evidence.

## Current Loop

1. Create and confirm a dashboard account.
2. Pair the account with Telegram using a short-lived link.
3. Complete name and timezone chat setup.
4. Tell Amigo a Task and, optionally, when to send a Reminder.
5. Receive the Reminder in Telegram.
6. Choose Done, Skip, or Later, or update the Task conversationally.
7. Review the resulting prototype state on the dashboard.

Amigo currently reaches out first only when delivering a participant-requested Reminder. It does
not autonomously initiate general morning greetings, evening reviews, meal check-ins, or companion
conversations.

## Shipped Foundation

- Telegram text conversation and resumable chat setup.
- Natural-language Task creation and status updates using Gemini 2.5 Flash and Pydantic AI.
- User-scheduled Telegram Reminders with Done, Skip, and Later buttons.
- Supabase persistence, authentication, account pairing, and dashboard realtime refresh.
- Session-scoped context, recent Task context, and a recent-session summary.
- Local CLI development mode, automated tests, linting, and basic scheduler/channel smoke checks.

Some shipped prototype behavior is not beta-ready. In particular, cross-surface lifecycle
consistency, pairing security, reminder reliability, production observability, data rights, and
the complete Activation journey remain release gates.

## What Memory Means Today

The repository stores conversation messages, Tasks, Reminders, profile fields, Sessions, and a
recent Session summary. This helps maintain limited conversational continuity.

It is not the planned personal **Memory** product. Amigo does not yet provide approved durable
preference learning, semantic or temporal retrieval, a Memory Inspector, Memory export controls,
or separate Pause Learning and Pause Memory Use controls.

## Product Boundary

Amigo is a non-clinical accountability companion. It is not a therapist, clinician, diagnostic
tool, treatment, medical device, emergency responder, or monitored crisis service. The current
beta should not be recruited or demonstrated to people seeking those services.

Future non-clinical reflection exercises, Mood Entries, and Crisis Referral are separate,
evidence-gated maps with their own privacy, safety, review, and release requirements.

## Evidence-Gated Destination

The destination includes four future product maps, not current promises:

- **Memory:** explicit-first durable Memory and a complete Memory Inspector.
- **Modes:** user-controlled Recommender, Coach, and Reflect Modes with bounded contracts.
- **Wellbeing:** non-clinical reflection and Mood Entries with verified Crisis Referral.
- **Surface Expansion:** evidence-led WhatsApp, voice, PWA, or native mobile decisions.

Each map can conclude “do not build.” No capability ships merely because it appears on the
roadmap.

## Technology in the Current Repository

| Layer | Current implementation |
|---|---|
| Messaging | Telegram bot; local CLI for development |
| Backend | Python 3.12, FastAPI, Pydantic AI |
| Model | Gemini 2.5 Flash by default |
| Persistence and auth | Supabase PostgreSQL and Supabase Auth |
| Scheduling | APScheduler in one application process, with pending Reminder reload |
| Dashboard | React and Vite with Supabase realtime subscriptions |
| Canonical beta hosting | Render, subject to the always-on beta runtime gate |

Claude routing, pgvector Memory, Redis or multi-machine scheduling, Graphiti, voice models, and
native mobile technology are not part of the current shipped stack.

## Offer and Status

The intended first release is a closely supported, free 30-day invitation beta for a small cohort
of English-speaking adults in the United States and Canada. The product is not geo-blocked, but
Amigo must not claim evaluated support for markets it has not reviewed.

The hosted pricing hypothesis is US$9 per month after beta. That is a research hypothesis, not a
current paid plan. Amigo is open source under AGPL-3.0, but the project does not yet promise
supported self-hosting.

Amigo is not ready for public launch. Release status and required evidence are tracked in the
[pre-launch implementation plan](pre-launch-implementation-plan.md).
