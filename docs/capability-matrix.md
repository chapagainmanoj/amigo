# Amigo Capability Matrix

**Last verified against the repository:** 2026-09-02
**Release scope:** Invitation-only beta  
**Canonical beta promise:** Tell Amigo what you need to do. It turns the conversation into a Task
and sends a Telegram Reminder at the time you choose, with Done, Skip, or Later controls.

This is the source of truth for product copy and demonstrations. “Shipped” means implemented in
the current repository; it does not mean production reliability, security, or usability gates
have passed. A beta experiment must be presented as experimental. A roadmap item must never be
described in the present tense.

The current preflight worktree stages application code that requires protected migrations
014. That migration is not yet checked in, so the Activation application code is not in the
“shipped” column and this worktree must not be deployed until the schema chain is approved.

| Shipped in the current prototype | Beta experiment or release-gated | Roadmap, not available |
|---|---|---|
| Dashboard email signup, confirmation, and sign-in through Supabase Auth | Dashboard-first Activation application code awaiting migration 014, then clean-account staging/usability evidence | Durable personal Memory and semantic/temporal retrieval |
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
| Reproducible dashboard install, lint, and production build | — | — |

## Important Limits in the Current Prototype

- “Reaches out first” currently means delivering a Reminder the participant explicitly asked
  Amigo to schedule. It does not mean autonomous companion check-ins.
- Conversation history, recent summaries, profile fields, and Task context are not the approved
  durable personal Memory product.
- Dashboard and Telegram now share the canonical Task and Reminder command paths locally, but the
  cross-surface flow still needs staging evidence before it can pass the release gate.
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
