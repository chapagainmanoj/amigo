# Amigo Pre-Launch Gap Analysis

**Assessment date:** 2026-08-26
**Last reviewed against deployed UI:** 2026-08-29
**Scope:** Product, Telegram bot, web dashboard, backend, persistence, scheduling,
deployment, security, privacy, documentation, analytics, legal readiness, and customer demos.

> **Document role:** This is the dated baseline assessment that produced the current roadmap. Its
> observations are preserved as historical evidence, not as a live backlog. The
> [complete-product decision map](../.scratch/amigo-complete-product/MAP.md) is authoritative for
> decisions, and the [pre-launch implementation plan](pre-launch-implementation-plan.md) tracks
> current implementation status.

## Current disposition — 2026-08-30

- The beta promise, target segment, offer/support contract, privacy/retention contract,
  Task/Reminder lifecycle, cross-surface contract, runtime strategy, model-evaluation contract,
  Activation Journey, cohort protocol, pricing hypothesis, product boundaries, expansion posture,
  reliability semantics, and AGPL-3.0 contribution/security contract are now closed decisions.
- Local public copy has been narrowed to the Telegram Core Loop and unavailable Modes/WhatsApp
  have been hidden. Deployment and screenshot verification are still required before that evidence
  can close a release gate.
- `LICENSE`, `CONTRIBUTING.md`, and `SECURITY.md` now implement the repository source contract;
  enabling GitHub private vulnerability reporting still requires authenticated repository setup.
- The deprecated UTC calls and dead agent/context code identified here are removed. Python tests
  and Ruff pass without warnings; a clean dashboard install, lint, build, and npm audit also pass.
- Security/RLS hardening, canonical lifecycle implementation, shared backend dashboard commands,
  production validation, observability, data-rights operations, Activation, integration tests,
  and Gate A/B evidence remain open. Amigo is still in pre-beta development.

## Executive assessment

Amigo is **not ready for a public launch or an unqualified customer presentation**.

It is a credible technical prototype: the Telegram task/reminder loop exists, the dashboard
builds, backend lint passes, and all 69 unit tests passed at the 2026-08-29 review. The largest
risk is that the public
story describes a substantially more advanced product than the repository implements. That
truth gap, combined with privacy, pairing security, reminder consistency, integration testing,
and production-observability gaps, would undermine customer trust.

A controlled, founder-led prototype demo is possible if Amigo is presented honestly as an
early conversational task-and-reminder beta.

**Remediation update — 2026-08-29:** The local repository now has a canonical
[capability matrix](capability-matrix.md), and README, product overview, unpublished launch
article, default dashboard labels, onboarding/pairing copy, and the agent prompt have been aligned
to the narrow beta promise. The critical claim gap remains open for release purposes until these
changes are reviewed, deployed, and verified across every public surface.

## What currently works

- Natural-language task creation through a Pydantic AI agent.
- Telegram onboarding, sessions, reminders, Done/Skip/Later actions, and `/feedback`.
- Restart recovery for pending reminders.
- Supabase persistence and dashboard account pairing.
- Dashboard task, reminder, and session views with realtime refresh.
- Reasonable module separation and dependency injection.
- All 69 backend tests passed and Ruff passed at the 2026-08-29 review.
- The dashboard production build succeeds.

The automated tests use fakes. They do not prove that Gemini, Telegram, Supabase Auth/RLS,
migrations, realtime subscriptions, the browser workflow, and deployed infrastructure work
together.

## Current deployed-state review — 2026-08-29

The latest dashboard and Telegram evidence materially improves confidence in the narrow core
loop. A dashboard account can connect to Telegram, a natural-language request can create a task
and reminder, the reminder can arrive at the requested time, and Telegram presents Done, Skip,
and Later controls. The paired dashboard and connection screens are visually coherent enough for
an invitation beta. These observations are useful manual evidence, but they do not replace a
repeatable staging end-to-end test.

The same evidence exposes the following gaps that must be treated explicitly:

| Gap | Why it matters | Severity | Recommended fix | Gate |
|---|---|---:|---|---|
| Dashboard task, progress, and reminder sets contradict one another | The deployed dashboard shows `0 of 0` and “No tasks pending” while displaying an active reminder. The current task query uses `created_date`, while pending reminders are fetched independently. A reminder can therefore exist without its task appearing in the task list or progress count. | **High** | Define canonical “today” semantics using due/scheduled date and lifecycle status rather than creation audit metadata. Return one server-derived dashboard snapshot with tested invariants across tasks, progress, and reminders. | Before external beta |
| Dashboard and Telegram implement different snooze policies | The dashboard offers a direct 15-minute database update, while Telegram uses 60 minutes, then 30 minutes, then defer. A direct dashboard write also does not reliably reschedule the live job. The same reminder behaves differently depending on surface and can still fire at the old time. | **High** | Create one backend snooze policy/domain operation used by every channel; return the selected delay and resulting schedule, reschedule atomically or compensate, and test both surfaces. | Before external beta |
| Session state and duration are not trustworthy | A conversation from 26 August remains “ongoing” on 29 August, ended sessions display durations such as `85881m`, and raw values such as `morning_planning` leak into the UI. This makes the dashboard look broken and casts doubt on all activity data. | **High** | Close or reconcile stale sessions, derive active state from last activity plus a documented timeout, humanize types, and format bounded durations in useful units. | Before showing customers |
| Telegram connection management is incomplete | The connected state exposes a raw Telegram chat ID but provides no disconnect, relink, linked-account identity, connection time, or recovery action. Raw internal identifiers add risk without helping the user. | **Medium** | Hide internal IDs. Add authenticated disconnect/relink with confirmation, ownership checks, token invalidation, audit logging, and a human-readable connection status. | Before broader beta |
| Reminder time lacks sufficient context | A card such as `05:00 PM` does not show its date, timezone, or whether it is overdue. Around midnight, travel, or stale data, a user cannot tell what will actually happen. | **Medium** | Show localized date, time, timezone, and overdue/delivered state; keep the exact scheduled timestamp available in details. | Before broader beta |
| First-chat copy still weakens trust | The deployed greeting lowercases the user's name, claims the bot is “doing great,” stacks two questions, and the reminder copy appears to contain a typo. These are small individually but visible in the first product interaction. | **Medium** | Preserve preferred-name casing, use transparent assistant language, ask one primary question per turn, and add reviewed deterministic copy plus snapshot/evaluation coverage. | Before showing customers |

## Product, positioning, and business gaps

| Gap | Why it matters | Severity | Recommended fix | Gate |
|---|---|---:|---|---|
| Public claims materially exceed the implemented product | The launch article claims scheduled morning outreach, evening accountability, anti-nag controls, adaptive coaching, temporal memory, a Memory Inspector, pgvector, Claude routing, and sentiment gating. Customers will experience the discrepancy as misrepresentation. | **Critical** | Rewrite all public copy around conversational task capture, Telegram reminders, status updates, and the task dashboard. Clearly label future capabilities as roadmap. | Before any customer showing |
| The claimed differentiator, “reaches out first,” is mostly absent | Amigo sends user-created reminders but does not initiate scheduled morning planning, evening review, meal check-ins, or general companion conversations. | **Critical** | Implement one dependable scheduled morning check-in or reposition as “a conversational planner that follows up on tasks.” | Before launch |
| Product identity is split | Productivity tool, loneliness companion, and future mental-health product imply different users, safety expectations, and value propositions. | **High** | Pick one Phase 1 positioning. Recommended: “Telegram accountability companion for people who struggle to keep using conventional task apps.” | Before customer discovery |
| No evidence of problem validation | There is no interview synthesis, activation hypothesis, retention evidence, user outcomes, or willingness-to-pay evidence. | **High** | Run 10–15 target-user interviews and a 5–10-user concierge beta. | Before paid launch |
| No concrete target customer | “People who want a friend” is too broad to drive product or messaging decisions. | **High** | Define one first segment, triggering problem, alternatives, desired outcome, and disqualifiers. | Before customer showing |
| Pricing and business model are unresolved | “Completely free and open source” conflicts with a customer-sales goal; the premium voice idea is not an actual offer. | **High** | Choose hosted subscription, managed deployment, open-core, or another explicit model. Publish a beta offer and pricing hypothesis. | Before selling |
| Unit economics are unsupported | Cost claims are not based on recorded production usage; `log_usage()` exists but is not invoked. | **Medium** | Record model tokens, latency, tool steps, and cost per active user, then recalculate pricing. | Before charging |
| No project license | Source visibility does not grant permission to use, modify, or redistribute the project. | **High** | Select and add an explicit license plus contribution and security-reporting guidance. | Before calling it open source |

## Feature and promise gaps

| Gap | Why it matters | Severity | Recommended fix | Gate |
|---|---|---:|---|---|
| No temporal or semantic memory | Current memory is message history, tasks, and optional session summaries. There is no Graphiti, pgvector, contradiction handling, or routine learning. | **High** | Remove current claims. Later define memory provenance, confidence, expiry, correction, retrieval, and deletion before implementation. | Claim removal before launch; feature later |
| No Memory Inspector or learning controls | Users cannot inspect, correct, export, pause, or delete learned memories, and the promised memory objects do not exist. | **Critical** | Remove the claim or build the complete trust surface, including deletion propagation. | Before advertising memory |
| Adaptive coaching is only a stored default | `coaching_profile` exists but is not learned or applied dynamically; the agent uses a static persona. | **High** | Describe the current personality as fixed. Define signals, safe bounds, overrides, and evaluation before adaptation. | Before claiming adaptation |
| Anti-nag fields are inert | The daily budget and coaching fields are not enforced; there is no cooldown, ignored-message tracking, or back-off. | **High** | Add a deterministic governor before any proactive-send path. | Before proactive check-ins |
| No user-facing reminder preferences | Users cannot set quiet hours, wake/sleep times, categories, cadence, or notification limits. | **High** | Add minimal Preferences UI and Telegram controls for mute, quiet hours, timezone, and reminder intensity. | Before broader beta |
| Dashboard snooze does not reschedule the live job | React updates the reminder row directly, but APScheduler is not notified; the old in-memory job may still fire. Its 15-minute policy also conflicts with Telegram's 60-minute, then 30-minute policy. | **High** | Route dashboard mutations through authenticated backend endpoints and one shared snooze policy used by Telegram and the dashboard. | Before external beta |
| “Deferred to tomorrow” is incomplete | A deferred task is not proactively carried over or scheduled for review; it is only seen when the user initiates another turn. | **High** | Define carry-over semantics and schedule a next-day check-in or create a correctly dated task. | Before claiming automatic follow-up |
| Ambiguous times can resolve incorrectly | A direct check resolved `at 8` to `00:00`; phrases such as `dinner at 8` did not parse. | **High** | Ask for clarification when meridiem/date is ambiguous; support common phrases and add locale/DST tests. | Before launch |
| Dashboard exposes unavailable modes | Recommender, Coach, Reflect, and WhatsApp are prominent despite being unavailable. Unavailable mode chips are still clickable. | **Medium** | Hide unfinished modes from customer builds or place them on a clearly labeled roadmap. | Before customer demo |

## Onboarding, UX, design, and accessibility gaps

| Gap | Why it matters | Severity | Recommended fix | Gate |
|---|---|---:|---|---|
| Dashboard-first onboarding is not yet a complete guided journey | The founder decision is dashboard account first, superseding the earlier Telegram-first recommendation. The current screens support account pairing but do not visibly guide account → Telegram → profile/timezone → first reminder → return to dashboard as one resumable flow. | **High** | Make the dashboard the canonical entry and implement a progress-based, recoverable journey ending in a delivered five-minute test reminder and automatic dashboard unlock. | Before external beta |
| Aha moment is too slow and uncertain | Onboarding collects identity data but does not guarantee a successful near-term reminder. | **High** | End onboarding with a guided five-minute test reminder and explicit confirmation. | Before beta |
| Timezone onboarding assumes Nepal | Every user is initially told they are probably in `Asia/Kathmandu`. | **High** | Treat locale as a weak hint, offer common choices, and use browser timezone during dashboard onboarding. | Before general launch |
| Auth lacks customer essentials | No forgot-password flow, password rules, resend-confirmation flow, legal consent, support link, or explanation of why an account is needed. | **High** | Add recovery and verification states, benefits, consent, and support contact. | Before launch |
| Signed-in mobile layout is incomplete | The authenticated shell uses a persistent desktop sidebar without a mobile navigation replacement. | **High** | Add bottom navigation or a drawer and test all signed-in views at 320–430 px widths. | Before showing mobile users |
| Accessibility is incomplete | Icon-only controls lack accessible names; labels are not explicitly bound to inputs; visually disabled mode controls remain actionable. | **Medium** | Add names, label associations, true disabled behavior, keyboard tests, status announcements, and automated accessibility checks. | Before public launch |
| Data-loading failures are silent | Failed Supabase reads commonly render empty panels rather than error or retry states. | **High** | Add explicit loading, empty, permission, offline, failure, and retry states. | Before launch |
| Branding is coherent but generic | The auth surface lacks a distinctive mark, product demonstration, trust cues, screenshots, and evidence. | **Medium** | Add a brand mark, a precise promise, a short demo, privacy cues, and beta/testimonial framing. | Before customer showing |

## Reliability and performance gaps

| Gap | Why it matters | Severity | Recommended fix | Gate |
|---|---|---:|---|---|
| No end-to-end integration suite | Passing fake-based tests do not validate the actual product path. | **High** | Add staging coverage for onboarding → task → reminder → callback → dashboard update. | Before launch |
| Webhook processing is not idempotent | Telegram retries can process the same update again after an exception; update IDs are not claimed or recorded. | **High** | Persist and atomically claim Telegram `update_id`; safely acknowledge delivery and separately retry internal work. | Before launch |
| No per-user turn serialization | Concurrent messages can race session creation, context, tools, and responses. | **Medium** | Add a per-user lock or ordered queue and burst tests. | Before scale; recommended for beta |
| Synchronous Supabase calls run inside async methods | Slow database calls can block the event loop, delay turns, and make reminder delivery late. | **High** | Instrument event-loop delay, then adopt a supported async client or isolate synchronous calls behind a bounded worker-thread adapter with explicit limits and timeouts. | Before external beta |
| Repeated reads inflate latency and cost | Turn context fetches task data more than once and tools add further network calls. | **Medium** | Assemble one immutable Turn Context snapshot and reuse it. | After beta |
| No explicit dependency timeouts | Slow model, database, auth, or Telegram calls can tie up the process. | **High** | Define bounded connect/read/total timeouts, retries, and user-safe fallbacks per dependency. | Before launch |
| Health check proves only process liveness | `/health` can return healthy while the scheduler or dependencies are broken. | **High** | Separate liveness and readiness; add a scheduler heartbeat and synthetic checks. | Before launch |
| Deployment strategy is contradictory | Render and Fly configurations point at different production URLs; whichever instance starts last can replace the Telegram webhook. | **High** | Select one production platform, one canonical URL, and one scheduler owner. Archive the alternative. | Before launch |
| In-process scheduling imposes a strict topology | Timing is safe only while exactly one always-on scheduler owner exists. | **High** | Enforce and document single ownership now; use a durable queue/worker when scaling. | Before launch |
| No representative burst or capacity testing | A burst of concurrent conversations or reminders can block the single event loop, exhaust provider/database connections, and make time-sensitive reminders late. Correct single-user tests do not establish safe beta capacity. | **High** for a representative beta burst; **Medium** for later capacity/soak depth | Define SLOs and run a beta-sized mixed workload of concurrent turns and due reminders while measuring event-loop delay, reminder lateness, latency, errors, connections, CPU, and memory. Add larger capacity and soak tests before broader scale. | Representative burst before external beta; capacity/soak before broader launch |
| Deprecated UTC construction creates warning noise | Test fakes and session tests still call `datetime.utcnow()`, violating the repository clock rule and producing 100 warnings in the reviewed test run. Warning noise can hide new regressions and the naive timestamps weaken time-sensitive tests. | **Low** | Replace calls with the project UTC clock/helper or injected test clock, preserve timestamp semantics, and make the test run warning-clean. | After critical beta blockers; before enforcing warnings in CI |

## Security and privacy gaps

| Gap | Why it matters | Severity | Recommended fix | Gate |
|---|---|---:|---|---|
| `pairing_tokens` lacks RLS or explicit grant revocation | The public-schema table may be readable through Supabase API roles under common grants, exposing valid tokens and auth IDs. | **Critical** | Verify production grants immediately; enable RLS, revoke client access, and keep pairing behind backend/service-role operations. Rotate outstanding tokens if exposure is possible. | Before dashboard use |
| Profile update policy is too broad | Row-level security does not restrict columns; an authenticated client may update identity and internal profile fields. | **High** | Revoke broad update rights and expose only allowlisted fields through backend endpoints or safe RPCs. | Before launch |
| Production can accidentally allow everyone | An empty `ALLOWED_TELEGRAM_CHAT_IDS` means open access, including in production. | **High** | Fail production startup unless an explicit enrollment/access mode is configured. | Before launch |
| No abuse, rate, or spend controls | An open bot can generate unbounded model calls and database writes. | **High** | Add per-user limits, quotas, spend alarms, usage logging, and an emergency disable control. | Before public access |
| Task-status updates lack an ownership predicate | The store update is made by task ID before reminder cancellation applies the user ID. | **Medium** | Require `user_id` in the update predicate and fail closed on mismatch. | Before public beta |
| Full conversations have no lifecycle policy | Intimate messages, tasks, sessions, and feedback are retained without consent, export, deletion, or retention controls. | **Critical** | Define retention; implement account deletion, export, selective deletion, and provider-processing disclosure. | Before public launch |
| No security assurance workflow | CI lacks dependency audits, secret scanning, migration security checks, and multi-user RLS regression tests. | **Medium** | Add automated scans and tests in which two authenticated users attempt cross-tenant access. | Before launch |

## Operations, analytics, and feedback gaps

| Gap | Why it matters | Severity | Recommended fix | Gate |
|---|---|---:|---|---|
| No exception tracking or correlated tracing | Production failures cannot be reliably detected or connected across webhook, session, model, tool, and reminder steps. | **High** | Add structured, redacted logs and exception/tracing instrumentation. | Before beta |
| No launch metrics | Activation, delivery, lateness, completion, snooze, ignored-message, pairing, and retention behavior cannot be measured. | **High** | Define a minimal event taxonomy and activation/retention dashboard. | Before beta |
| Feedback has no operating loop | `/feedback` stores text but has no triage, ownership, user follow-up, or review surface. | **Medium** | Create a weekly feedback queue with severity, contact consent, owner, and status. | Before broader beta |
| No backup/restore evidence | Backup configuration, retention, and recovery have not been demonstrated. | **High** | Configure backups and perform a staging restore exercise. | Before public launch |
| No incident or rollback runbook | There is no defined response to a bad deploy, duplicate reminders, provider outage, leaked key, or failed migration. | **High** | Write deployment, rollback, key rotation, webhook recovery, and incident procedures. | Before launch |
| CI ignores the frontend | `npm run lint` currently fails because ESLint is not installed; frontend build and accessibility checks are absent from CI. | **High** | Fix the lint toolchain and add install, lint, test, build, and accessibility checks to CI. | Before launch |
| Generated-dependency cleanup is prepared but not complete | The index currently removes the previously tracked `web/node_modules` tree and `.gitignore` has a local ignore change, but the cleanup is not complete until those changes are reviewed, committed, and verified from a clean install. The current `HEAD` still contains the generated dependencies. | **Medium** | Review and commit the existing cleanup, then verify a clean dependency install, lint, test, and production build without checking generated files back in. | Before open-source announcement |

## Documentation, legal, and customer-demo gaps

| Gap | Why it matters | Severity | Recommended fix | Gate |
|---|---|---:|---|---|
| README uses `git clone <repo-url>` | The advertised quick start cannot be followed literally. | **Medium** | Insert the real URL and validate setup from a clean machine. | Before open-source announcement |
| Setup omits migration 002 | Following the README does not install dashboard pairing and RLS. | **High** | Add an ordered migration process or migration runner with schema-version validation. | Before self-hosting launch |
| Documentation contradicts itself | Gemini 2.5 vs 3.5, Railway vs Render vs Fly, implemented vs future features, and test counts differ. | **High** | Establish a capability matrix and release checklist as the documentation source of truth. | Before customer showing |
| Blog links and images are unfinished | The bot link is `t.me/YoursAmigoBot`, and referenced screenshots are missing. | **High** | Add verified links and real screenshots or keep the article unpublished. | Before publication |
| No user help or FAQ | Users have no guidance for corrections, timezone changes, missed reminders, muting, deletion, pairing, or support. | **Medium** | Add `/help`, FAQ, troubleshooting, and a support contact. | Before public beta |
| No privacy policy or terms | Users are not told what is collected, where it goes, how long it remains, or which third parties process it. | **Critical** | Publish reviewed privacy and terms material covering Telegram, Supabase, model providers, retention, deletion, security, limitations, and acceptable use. | Before public launch |
| No wellbeing safety boundary | Loneliness, CBT-informed, mood-journaling, and emotional-support messaging can be mistaken for diagnosis, treatment, therapy, or monitored crisis care without explicit product boundaries, referral behavior, and evaluation. | **Critical** | Establish and evaluate a non-clinical wellbeing contract: supportive reflection and resource referral may proceed only with clear limitations, consent, sensitive-data controls, and prohibited clinical outputs. | Before wellbeing features or marketing |
| No age policy or consent model | A companion product can attract minors while collecting sensitive conversational data. | **High** | Define eligibility, consent, prohibited use, and enforcement. | Before public launch |
| No polished deterministic demo | Live model and scheduler behavior is uncertain, and there is no seeded account or fallback recording. | **High** | Build and rehearse a three-minute demo with a recorded fallback. | Before customer demo |

## Must fix before launch

1. Remove or label all unimplemented product claims.
2. Audit and lock down pairing tokens and profile updates.
3. Publish privacy, terms, retention, export, and deletion behavior.
4. Remove clinical wellbeing claims and enforce the approved non-clinical safety boundary.
5. Route dashboard reminder mutations through backend scheduling logic.
6. Add webhook idempotency and safe failure handling.
7. Choose one production platform and one scheduler owner.
8. Add production configuration validation, rate limits, usage tracking, and spend controls.
9. Add monitoring, exception tracking, readiness checks, and alerts.
10. Pass a real staging end-to-end test.
11. Fix ambiguous time handling and timezone/DST coverage.
12. Add backup/restore and rollback procedures.
13. Add a project license before describing Amigo as open source.
14. Fix frontend CI and signed-in mobile behavior.
15. Make task, progress, and reminder data consistent and define canonical daily-task semantics.
16. Reconcile stale sessions and remove raw internal identifiers/enums from customer views.

## Should fix before showing customers

1. Narrow the value proposition and first target user.
2. Implement the decided dashboard-first onboarding path end to end.
3. Guarantee a first reminder during onboarding.
4. Hide unfinished modes and WhatsApp.
5. Add real bot/dashboard links and screenshots.
6. Improve auth recovery, support, consent, and trust cues.
7. Prepare a deterministic three-minute demo and recording.
8. Add basic activation and reminder metrics.
9. Resolve documentation contradictions.
10. Add FAQ, `/help`, timezone, mute, and quiet-hour controls.
11. Collect real beta outcomes or testimonials.
12. Describe the dashboard as a task-control surface, not a Memory Inspector.

## Evidence-gated after Customer Readiness

- Potential temporal and semantic Memory, only if its demand and trust gates pass.
- Potential participant-controlled Interaction Style and specialized Modes, each independently
  gated; automatic routing remains an open decision.
- Non-clinical supportive reflection, CBT-informed exercises, mood journaling, and crisis-resource
  referral only after safety, consent, sensitive-data, referral, and evidence gates pass.
- Diagnosis, clinical treatment, therapy, and monitored crisis response are outside the current
  Amigo product destination.
- WhatsApp, voice, PWA, and native mobile remain **No Expansion Yet** until observed demand opens
  the matching decision ticket.
- Distributed scheduling when multiple workers are required.
- Prompt caching and database-round-trip optimization.
- PACT-style session evaluation.
- Sophisticated routine learning and personalization.
- Advanced experimentation and analytics.
- Premium tiers based on measured usage and demand.

## Top five changes most likely to increase trial or purchase intent

1. Make one narrow promise demonstrably true: tell Amigo what to do and it follows up in
   Telegram until the task is resolved.
2. Deliver a successful reminder within the first three minutes of onboarding.
3. Make reminder timing, snoozing, deduplication, and quiet hours trustworthy.
4. Build trust with honest privacy language and export/delete controls.
5. Show proof rather than roadmap: a polished demo, real user outcomes, retention metrics,
   and a clear beta offer.

## Final readiness decision

**Not ready yet.**

The strongest current product is a conversational Telegram task planner with reminders. The
marketed product is a memory-rich, adaptive, proactive companion with a transparent Memory
Inspector. Those are materially different products.

After the security, privacy, reminder-consistency, deployment, integration-testing, and
truth-in-marketing gaps are addressed, Amigo would be appropriate for a small,
invitation-only beta. Temporal memory, adaptive coaching, extra modes, and voice can wait;
trustworthy reminders, honest positioning, fast onboarding, and privacy cannot.
