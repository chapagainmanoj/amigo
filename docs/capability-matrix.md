# Amigo Capability Matrix

**Last reviewed against the repository:** 2026-10-22
**Release scope:** Invitation-only beta  
**Canonical beta promise:** Tell Amigo what you need to do. It turns the conversation into a Task
and sends a Telegram Reminder at the time you choose, with Done, Skip, or Later controls.

This is the source of truth for product copy and demonstrations. “Shipped” means implemented in
the current repository; it does not mean production reliability, security, or usability gates
have passed. A beta experiment must be presented as experimental. A roadmap item must never be
described in the present tense.

The checked-in schema chain reaches migration 021 and the application requires exact version 21.
The channel-neutral Mode routing, isolated Sessions, grants, confirmed handoffs, and dashboard
availability implementation are release-gated pending integration review and complete owner
application-flow evidence. The owner's topic spike passed on Desktop and iOS; Android was not
tested. No Supabase migration or production deployment is asserted. Daily and Coach are live
Modes; Reflect and Recommender are Planned. Activation also remains release-gated pending
clean-account staging evidence.

| Shipped in the current prototype | Beta experiment or release-gated | Roadmap, not available |
|---|---|---|
| Dashboard email signup, confirmation, and sign-in through Supabase Auth | Dashboard-first Activation application code awaiting clean-account staging/usability evidence | Durable personal Memory and semantic/temporal retrieval |
| Expiring single-use dashboard-to-Telegram account Pairing | Cross-surface Task, Reminder, and Session staging evidence | Memory Inspector, export controls, and learning/use pauses |
| Telegram text conversation | Natural-language task extraction accuracy and clarification behavior | Recommender, Coach, and Reflect Modes |
| Dashboard profile setup with validated name, IANA timezone, and quiet hours | First-message-of-day planning using recent Task context; Amigo does not initiate it | Adaptive Interaction Style or automatic Mode routing |
| Natural-language Task creation and Task status updates | Task creation and lifecycle accuracy under the release model evaluation | Non-clinical reflection exercises and Mood Entries |
| User-scheduled Telegram Reminders | Dashboard Task, Reminder, progress, and Session staging verification | Localized Crisis Referral beyond the separately gated wellbeing release |
| Telegram Done, Skip, and canonical Later replacement controls | Session-scoped conversation continuity and a recent-session summary | Scheduled general morning/evening check-ins and an anti-nag governor |
| Authoritative Reminder reconciliation, immutable attempt evidence, and readiness checks | Staging Reminder reliability evidence, synthetics, and alerts | WhatsApp |
| Atomic dashboard snapshot and shared Task/Reminder/Later command controls | Render deployment, monitoring, and backup verification | Voice interaction |
| Dashboard realtime refresh from Supabase | Free 30-day invitation-beta offer and founder-operated support | Native mobile apps; a PWA requires its own demand gate |
| `/feedback` capture | Eight-person external beta and willingness-to-pay research | Multi-machine scheduling and paid billing |
| Local CLI development mode | English output with code-mixed input comprehension | Automatic sentiment-based intervention or emotional profiling |
| Reproducible dashboard install, lint, and production build | Channel-neutral Mode conversations, `/mode` commands, grant maintenance, isolated Sessions, confirmed handoff execution, and authenticated Mode chips | — |

## Important Limits in the Current Prototype

- “Reaches out first” currently means delivering a Reminder the participant explicitly asked
  Amigo to schedule. It does not mean autonomous companion check-ins.
- Conversation history, recent summaries, profile fields, and Task context are not the approved
  durable personal Memory product.
- Dashboard and Telegram now share the canonical Task and Reminder command paths locally, but the
  cross-surface flow still needs staging evidence before it can pass the release gate.
- Telegram production supports topics off; if enabled, user-created threads must be off. Every
  threaded send needs an explicit conversation; deleting a topic does not unsubscribe its Mode.
- Dashboard Mode chips show server availability and grant expiry. Planned or unentitled Modes
  have no actionable link; a visible name does not mean the Mode can run.
- Python tests use fakes and CI exercises migrations/RLS on PostgreSQL. They do not prove Telegram,
  Gemini, Supabase Auth, realtime delivery, and Render work together.
- The current project is open source under AGPL-3.0, but supported self-hosting is not a shipped
  product or support promise.

## Outside the Product Boundary

Amigo is a non-clinical accountability companion. It does not provide psychotherapy, diagnosis,
medical or mental-health treatment, medication guidance, clinical monitoring, emergency dispatch,
or a monitored crisis service. A disclaimer does not make those capabilities part of the product.

## Copy and Demo Rule

Before publishing copy, screenshots, a demo script, or a sales claim:

1. Match every claimed capability to this matrix.
2. Call experimental behavior a beta experiment and state the relevant limitation.
3. Call future behavior roadmap and avoid dates or “coming soon” promises unless it has an
   approved release gate and committed delivery plan.
4. Update this matrix only after implementation evidence and the governing Wayfinder gate agree.


### Internal Mode candidates and admission controls (22 October 2026)

Migrations 018/019 add owned versioned Coaching Programs, exact-draft approval callbacks,
Program export/deletion, a shared proactive budget ledger and a fenced coaching outbox.
The profile budget covers Amigo-initiated Coach messages and recovery summaries only.
Participant-requested Reminders, Later, and Activation test Reminders never consume or get refused
by this budget. Existing Reminder commitments remain unchanged. Coaching uses selected days,
quiet hours, remaining proactive capacity, one check-in/day,
one missed follow-up then silence. Weekly review replaces a chosen check-in. Returning to Coach resumes that gate; program approval and extension remain separate choices.

Coach, Reflect and fictional laundry Recommender have authored instructions, isolated Toolsets
and versioned fictional evaluation suites. Coach is live on `google:gemini-3.8-flash` (48/48,
`.scratch/modular-modes/evals/coach-gemini-3.8-flash.json`) for every activated participant once
the owner sets `COACH_TRIAL_ENABLED`; each trial participant also taps I agree on its processing
notice. Reflect (56/60) and Recommender (43/48) failed their gemini-3.8-flash batches and remain
Planned. Candidate runner output cannot certify release/fallback.
No provider fallback is declared without complete current evidence and human review.

Coach and Reflect additionally deny real admission by default. Missing reviewed notices,
consent/retention/account-wide rights and qualified wellbeing evidence cannot be replaced with
an operator grant or a passing model test. Program export/deletion covers Program records and
entries only; retained conversation Messages/provider copies remain. Account-wide deletion and
backup erasure are not claimed. Reflect stores no Mood Entries, Memory, exercises or profile
inferences; its empty resource registry supplies only static general emergency guidance, never
stale contact details. CBT personal input remains off. No deployment or Supabase change occurred.


### Phase 6 candidates and explicit admission limits

Migrations020/021 extend the local chain to21. Memory uses owned versioned PostgreSQL records,
exact-preview confirmation, a content-free use ledger, separate learning/use pauses, lifecycle
filtering and scoped export/Forget. Unconfirmed text remains in bounded process-local previews,
not durable Memory. Dashboard inspection and JSON/CSV export do not establish backup erasure or
whole-account rights compliance. Memory saving/retrieval remains OFF pending reviewed eligibility,
privacy/readiness and the decision26 demand/decision30 technology review. Reflect receives no
automatic Memory. No embeddings, external Memory processor or automatic profile extraction.

Mode suggestions are a default-off deterministic application policy over current explicit job
requests. Owner/session/expiry/single-use/grant checks protect an Open Mode action; confirmation
opens a canonical conversation without transferring history or running a target Turn. Release,
friction, policy and affirmative per-Turn safety clearance remain required. A participant enabling
suggestion preferences does not enable those gates. No sentiment/silence/Task-behavior routing.

Coach declares workflow v1 over existing018/019 Program/outbox records and exposes owned metadata
inspection. Restart tests preserve occurrence identity, stale-token fencing and uncertain-send
nonretry. This is a declaration of current code, not a generic engine or persisted per-Program
version binding. A future definition change needs explicit binding/migration review. Issue07's
provisional triage reuses confirmed handoffs rather than adding a delegation graph; no recurring
job/benefit evidence has been invented. Provisional decisions and tests remain in the review queue.
