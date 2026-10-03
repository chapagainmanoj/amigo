# Build Coach Mode with a Coaching Program

Status: open
Label: `ready-for-human`
Severity: `severity:medium`
Type: HITL
Owner: unassigned
Phase: 3 of 5 (part 2 of 2)
Blocked by: [03-switch-modes-with-confirmed-handoffs.md](03-switch-modes-with-confirmed-handoffs.md)

## Problem Statement

Amigo captures what a participant intends to do today. It can't help them work toward one goal
or habit over two weeks. Coach is the first specialized Mode in decision 14's sequence, because its
job is closest to Amigo's accountability promise. It is registered as `planned` and does nothing.

Decision 14 fixes the Coaching Program contract:
- one participant-chosen goal with a participant-written success measure;
- 14 days by default;
- participant-chosen check-in days and time;
- at most one proactive message a day, within quiet hours and the anti-nag budget;
- a weekly continue, adjust, pause, or stop review;
- no guilt, streak pressure, dependency language, or expert-coaching claims.

Nothing implements it.

## Solution

Coach becomes a live Mode that requires a grant, so it reaches at most five trial participants
through issue 03's grants. Its Toolsets are a new Coaching Toolset and the Handoffs Toolset. It has
no Task or Reminder Tools. Ordinary Tasks go to Daily through a confirmed handoff.

A Coaching Program is a durable record with the lifecycle `draft`, `active`, `paused`,
`completed`, or `stopped`. It outlives any Session. Check-ins and the weekly review are delivered
proactively through the existing scheduler and outbox. Coach's own evaluation suite and the
decision 14 release evidence decide whether it ships beyond the trial.

## User Stories

1. As a participant, I want to set up one goal or habit with my own measure of success, so that coaching is about what I chose.
2. As a participant, I want to review and approve my Coaching Program before it starts, so that nothing begins without my agreement.
3. As a participant, I want to choose my check-in days and time, so that coaching fits my week.
4. As a participant, I want at most one coaching message a day, never in my quiet hours, so that Coach never nags.
5. As a participant, I want at most one gentle follow-up after a missed check-in, then silence until I return, so that missing a day carries no pressure.
6. As a participant, I want to report my own progress, so that Amigo never claims improvement it can't know.
7. As a participant, I want a weekly review where I choose to continue, adjust, pause, or stop, so that I stay in control.
8. As a participant, I want Pause and Stop available at any moment, so that I can end coaching instantly.
9. As a participant, I want my program to end after 14 days unless I choose to extend it, so that it never runs on indefinitely.
10. As a participant, I want Coach to offer to hand a concrete next step to Daily as a Task, and ask me first, so that my Task list only changes when I say so.
11. As a participant, I want Coach never to use guilt, streaks, or claims of expert coaching, so that it stays supportive and honest.
12. As a participant, I want Coach to follow the same Crisis Referral and non-clinical rules as Daily, so that a hard moment is handled safely.
13. As a participant, I want to see my program and its history, and delete it, so that my coaching data stays mine.
14. As the founder, I want Coach limited to granted trial participants, so that it trials with at most five people.
15. As the founder, I want Coach's model behaviour evaluated with its own suite, so that it passes the model evaluation contract before shipping.
16. As the founder, I want check-in delivery and anti-nag compliance measured, so that I have the trial evidence decision 14 requires.
17. As the founder, I want to be able to make Coach a paid feature later by changing its declared entitlement, so that pricing stays configuration.
18. As a security reviewer, I want Coach unable to call Task or Reminder Tools, so that a coaching conversation can't change plans directly.
19. As a security reviewer, I want every program change to require clear participant intent, so that emotional conversation never starts, extends, or stops a program by itself.
20. As an operator, I want check-ins to go through the durable outbox, so that restarts don't lose or duplicate them.
21. As the Gate A evaluator, I want Daily unchanged, so that Daily's evidence stays valid.

## Implementation Decisions

- **Migration (protected; needs explicit human approval).** It adds `coaching_programs` with:
  participant, goal, success measure, check-in days and local time, timezone, lifecycle state,
  starts at, ends at, extended count, version, and timestamps. It also adds `coaching_entries` for
  participant-reported progress, check-in outcomes, and weekly review choices. Both tables have
  row-level security and an at-most-one-non-terminal-program-per-participant rule, and the migration
  bumps the application schema version. Check-in deliveries reuse the Reminder outbox pattern, with
  a coaching delivery kind added only if needed. It is drafted, then parked for approval.
- **Commands.** Program changes go through shared Commands with optimistic versioning, like Task
  Commands. Tools call these Commands, and so do the Pause and Stop buttons.
- **Coaching Toolset.** Its Tools are `draft_program`, `activate_program` (only after the
  participant explicitly approves the drafted summary), `record_progress`, `pause_program`,
  `resume_program`, `stop_program`, `extend_program`, and `record_weekly_choice`. Every Tool
  requires clear intent and exactly one owned program.
- **Coach definition.**
  - Status `live`, with `entitlement="grant"`.
  - Toolsets: Coaching and Handoffs. Handoff targets: `("daily",)`.
  - Turn Context providers: the active program, recent entries, and today's local time.
  - Model policy: the configured default.
  - Evaluation suite: `evals/coach/v1/cases.json`.
  - Its instructions are new text and include the Safety Core.
- **Proactive check-ins.** The scheduler plans a check-in on the participant's chosen days and
  time. It sends none if the program isn't `active` or if the participant is in quiet hours
  (between the profile's sleep and wake times), and it counts against `daily_message_budget`. At
  most one coaching message is sent per local day. One missed check-in allows one follow-up, then
  none until the participant replies.
  - **Open decision:** there is currently no code that enforces the shared anti-nag budget across
    Reminders and coaching. This issue must define and enforce it; it is not optional.
- **Weekly review.** Every seventh program day, the check-in is replaced by a review prompt with
  Continue, Adjust, Pause, and Stop buttons. On the final day, the program completes unless the
  participant extends it.
- **Data rights.** Coaching data is included in the existing export and deletion paths. It never
  becomes Memory and creates no mood, risk, or profile inference.
- **Coach evaluation suite.** It covers program lifecycle consent, anti-nag timing, no guilt or
  streak language, no expert or clinical claims, Crisis Referral, handoff-instead-of-Task, and
  untrusted content. It runs under the per-Mode runner from issue 02. A full model run is a
  decision 09 event and needs the billing-enabled provider credential.

## Testing Decisions

- **Through the bot handlers, with a scripted model:**
  - the full lifecycle, from draft through approve, check-ins, weekly review, and complete or
    extend;
  - pause, resume, and stop work from buttons and from Tools;
  - no activation without explicit approval;
  - a second program is refused while one is active;
  - Coach calling a Task Tool is rejected;
  - a next step becomes a Task only through a confirmed handoff.
- **Scheduler tests with a fixed Clock:**
  - check-ins happen on the chosen days only;
  - none in quiet hours;
  - at most one a day;
  - one follow-up, then silence;
  - restart recovery sends no duplicates;
  - a paused or stopped program sends nothing.
- **Store contract tests** run against all three implementations. SQL assertions cover RLS and the
  one-program rule.
- **Export and deletion** include coaching data.
- **Coach evaluation:** the suite validates, and the deterministic subset runs in CI.
- **Unchanged Daily:** the Tool-schema hash and golden instructions pass unchanged.

## Out of Scope

- Interaction Style adaptation and proposals.
- Multiple concurrent programs, shared or group programs, or streaks and gamification.
- Paid entitlements, billing, or pricing changes.
- Reflect, Recommender, or any wellbeing exercise.
- Coach-initiated Task or Reminder creation without a confirmed handoff.

## Further Notes

- **Human touchpoints:**
  - approving the migration;
  - approving Coach's instruction text and entry/limits copy;
  - the billing-enabled credential for the model run;
  - the moderated usability sessions with five people;
  - the 14-day trial with no more than five participants.
- **Release rule (decision 14).** Coach ships beyond the trial only after its demand gate,
  deterministic tests, a passing model evaluation, moderated usability, and its trial all pass. It
  also needs three participants engaged for at least seven days, compliant timing, and no reported
  increase in guilt, pressure, or dependency. Building it doesn't ship it.
- **Premium.** Decision 12 excludes feature tiers from the first price validation. Coach's
  `entitlement` value is the only switch needed if that changes. No code here assumes either
  outcome.

## Comments
