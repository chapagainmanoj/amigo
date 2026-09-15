# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

**Primary — prospective and active participants.** English-speaking adults in the United States
and Canada who repeatedly abandon conventional task apps. They capture intentions in
conversation and lose momentum between planning and action; maintaining a task system has itself
become a task. Use is ordinary and non-safety-critical: Amigo is not built for medication,
medical appointments, or anything where a missed Reminder causes harm.

**Second durable audience — prospective investors.** Public surfaces are also read by people
evaluating whether this is worth building. They need the wedge, the market and the mechanism, not
only the product promise.

**Explicitly not a surface audience — beta-cohort candidates.** The first cohort is recruited
through warm second-degree referrals and at most two permitted communities. Decision 11 forbids
recruiting it through a public signup, paid advertising, Product Hunt, or an uncontrolled public
link. A waitlist is a mailing list, never a recruitment funnel.

Open-source contributors are a real constituency of the repository but were not made a durable
design audience for product surfaces.

## Product Purpose

Tell Amigo what you need to do, in a normal sentence. It turns that into a Task and sends a
Telegram Reminder at the time you asked for, with Done, Skip, and Later controls in the chat.

Success for the current release is evidence, not growth: participants reach Activation without
founder rescue, Reminders arrive reliably and on time, Task state stays consistent across
Telegram and the dashboard, the loop is useful without becoming annoying, and some participants
want to continue after the free 30 days.

## Positioning

Every competing accountability tool adds a surface the person has to return to — a session to
book, a pet to feed, another chat window to remember. Amigo removes one: it lives in a messenger
already open, and appears only at the moment the participant asked it to.

The mechanism a neighboring product cannot truthfully copy is the resolution loop. Each Done,
Skip, or Later is a specific, labeled fact about when this person can actually follow through,
collected at the moment of action — which no task app is positioned to learn, because nobody
opens a task app at the moment of truth.

## Operating Context

- **Activation Journey (dashboard-led, resumable):** create and confirm a Dashboard Account →
  acknowledge beta limits → pair Telegram through an expiring, single-use link → set preferred
  name, IANA timezone, and quiet hours → schedule the guided test Reminder → receive and resolve
  it in Telegram with Done, Skip, or Later.
- **Surface split:** Telegram is the conversation and Reminder surface. The dashboard is the
  account, connection, and review surface. A participant crosses between them mid-activation.
- **Reaching out first** currently means delivering a Reminder the participant explicitly asked
  for. Amigo does not initiate morning planning, evening reviews, check-ins, or companion
  conversation.
- **Support is founder-operated.** Assistance is recorded in the Intervention Log, and
  Unassisted Activation is measured separately from assisted.
- **Release gates:** Internal Preflight (Gate A) → External Invitation Beta (Gate B) → Customer
  Readiness (Gate C). A capability is not presentable because it is implemented.
- **Known constraint:** the signed-in shell uses a persistent desktop sidebar with no mobile
  navigation replacement, and signed-in views are unverified at 320–430 px.

## Capabilities and Constraints

**Shipped in the current prototype:** dashboard email signup/sign-in through Supabase Auth;
expiring single-use dashboard-to-Telegram Pairing; Telegram text conversation; profile setup with
validated name, IANA timezone and quiet hours; natural-language Task creation and status updates;
user-scheduled Telegram Reminders; Done, Skip and canonical Later replacement; authoritative
Reminder reconciliation with immutable attempt evidence; atomic dashboard snapshot and shared
Task/Reminder command paths; realtime dashboard refresh; `/feedback` capture; local CLI mode.

**Copy authority.** `docs/capability-matrix.md` is the source of truth for every product claim.
Roadmap capability is never written in the present tense; no dates or "coming soon" without an
approved release gate. Terminology is fixed by `UBIQUITOUS_LANGUAGE.md` — Task, Reminder,
Session, Pairing, Activation, Later, Inbox, Planning Day, Task Outcome, Missed Reminder, Beta
Participant, Roadmap Capability — and its listed aliases are to be avoided.

**Product boundary.** Amigo is a non-clinical accountability companion. It is not therapy,
diagnosis, treatment, medication guidance, clinical monitoring, emergency dispatch, or a
monitored crisis service. A disclaimer does not move a capability inside the boundary.

**Licensing and commercial facts.** AGPL-3.0; supported self-hosting is not promised. The hosted
price is a Pricing Hypothesis of US$9 per month — revisable, not a plan. The intended first
release is a free 30-day invitation beta for at most eight participants plus a four-person
waitlist.

**Intended scope (confirmed direction, not a promise).** The narrow Task-to-Reminder loop is the
wedge, and the product is meant to grow into user-selected Modes — deliberately switched on,
never automatically routed. Each Mode passes its own gate and each may end in "do not build."
Future surfaces may show this as direction; none may present it as available.

**Undecided.** The waitlist storage provider is not chosen and `VITE_WAITLIST_ENDPOINT` is unset.
Which Modes ship, in what order, and under what entitlement is open.

## Brand Commitments

- **Name:** Amigo. **Repository:** `chapagainmanoj/amigo`.
- **Voice:** plain, specific, and anti-hype. States the limit in the same breath as the benefit,
  and never claims an unshipped capability. The honesty is a positioning asset with a segment
  that has been burned by six habit apps, not a disclaimer tax.
- **Shared palette across surfaces.** `site/src/styles/tokens.css` and `web/src/index.css`
  declare the same ten brand tokens by value, pinned by `tests/test_landing_page.py`: `--oat`,
  `--sand`, `--rule`, `--ink`, `--ink-2`, `--signal`, `--signal-ink`, `--signal-deep`, `--band`,
  `--band-soft`. `--signal` is reserved for the moment a Reminder is due; it is not spent on
  ordinary buttons. Type is Fraunces (display) and Inter (body), self-hosted, latin subset.
- **Volunteered reference:** the founder named Wellsy's restraint as the quality bar. Recorded as
  given, not expanded.

## Evidence on Hand

- **No participant evidence exists yet.** No users, testimonials, case studies, press, logos,
  ratings, benchmarks, or willingness-to-pay data. Future work must not fabricate any of these,
  and must not imply a cohort exists.
- **Real internal material:** `docs/capability-matrix.md`, `docs/what-is-amigo.md`,
  `docs/architecture.md`, `UBIQUITOUS_LANGUAGE.md`, `docs/pre-launch-implementation-plan.md`,
  `docs/pre-launch-gap-analysis.md`, and an unpublished blog post at
  `docs/blog_post-say-hi-to-amigo.mdx`. The public repository is real and inspectable.
- **Third-party market research used in landing copy** (label as external, never as Amigo's own
  data): roughly 52% of people abandon a habit app within the first month and about 70%
  discontinue lifestyle and wellbeing apps within 100 days; habit-tracking apps are around
  US$2.2B in 2026 growing to roughly US$6.4B by 2034.
- **Missing and required before broader release:** published privacy and terms content. The
  marketing footer deliberately carries no "Privacy" link until a real page exists.

## Product Principles

1. **Remove a surface, never add one.** Anything that asks the participant to open, groom, or
   return to something is moving the wrong way.
2. **The moment beats the list.** Value is created at the instant of the Reminder, not in
   organizing beforehand.
3. **Never punish a miss.** No streaks, no resets to zero, no guilt mechanics. Skip and Later are
   first-class outcomes, not failures.
4. **Claim only what is shipped, and say the limit in the same breath.** The capability matrix
   wins over any surface, demo, or deck.
5. **Scope grows only through gates that can answer "no."** A capability on the roadmap is a
   question, not a commitment.

## Accessibility & Inclusion

**Target: WCAG 2.1 AA, deferred.** This is the standard future work aims at, not a current
commitment and not yet evidenced. It is gated at Customer Readiness (Gate C). Do not claim
conformance anywhere.

Known open gaps recorded in `docs/pre-launch-gap-analysis.md`: icon-only controls lack accessible
names; labels are not explicitly bound to inputs; visually disabled mode controls remain
actionable; the signed-in shell has no mobile navigation; automated accessibility coverage in CI
is limited.
