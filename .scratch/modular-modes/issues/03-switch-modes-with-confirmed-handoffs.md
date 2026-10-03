# Switch Modes Explicitly with Confirmed Handoffs and Trial Grants

Status: open
Label: `ready-for-human`
Severity: `severity:medium`
Type: HITL
Owner: unassigned
Phase: 3 of 5 (part 1 of 2)
Blocked by: [02-add-model-policy-tracing-and-per-mode-evaluation.md](02-add-model-policy-tracing-and-per-mode-evaluation.md)

## Problem Statement

After the foundation and model policy land, a Turn can name a Mode, but nothing remembers it.
Each message returns to Daily unless it names a Mode again. A participant can't enter a Mode,
stay in it for a Session, see which Mode they're in, or leave it. A specialized Mode has no safe way
to send a Task request to Daily. Decision 14 requires every Task and Reminder from Coach or Reflect
to go through a confirmed handoff to Daily, and nothing implements that.

Decision 14 also says each specialized Mode is trialled behind an opt-in flag with at most five
participants for 14 days. The only entitlement policy today grants every live Mode to every
activated participant, so a Mode can't be opened to five people without opening it to everyone.

## Solution

- **Active Mode.** A Session records its active Mode. The routing policy resolves, in order: an
  explicit selection on this Turn, then the Session's active Mode, then Daily. A new Session starts
  in Daily, which matches the glossary: a Mode is temporary and participant-entered within a
  Session.
- **Entry and exit.** The participant enters a Mode with an explicit Telegram command or button,
  and leaves it at any time with one command. Entering a Mode states its purpose and its limits.
- **Handoffs.** A Mode may propose a handoff to a Mode it declares as a handoff target. The
  participant confirms with a button before anything changes. On confirmation, the target Mode
  handles the carried request as a participant-confirmed Turn. Declining changes nothing.
- **Trial grants.** A new entitlement policy lets a Mode require an explicit per-participant grant.
  Grants are created, expired, and revoked by an operator script, with a per-Mode cap of five
  active grants.

This issue ships no specialized Mode. Coach stays `planned` until
[04](04-build-coach-mode-with-coaching-program.md). The mechanics are proven with a test-only Mode.

## User Stories

1. As a participant, I want to enter a Mode with one explicit command or button, so that I choose when Amigo changes how it works.
2. As a participant, I want Amigo to tell me which Mode I entered and what it can and can't do, so that I know its limits.
3. As a participant, I want to stay in the Mode I chose for the rest of the Session, so that I don't have to reselect it for every message.
4. As a participant, I want to leave a Mode at any time with one command, so that I'm never stuck.
5. As a participant, I want a new Session to start in Daily, so that I don't return to a forgotten Mode days later.
6. As a participant, I want to be asked before a Mode passes something to Daily, so that nothing becomes a Task or Reminder without my say.
7. As a participant, I want to see exactly what will be passed to Daily before I confirm, so that I know what I'm agreeing to.
8. As a participant, I want declining a handoff to change nothing, so that saying no is always safe.
9. As a participant, I want an old handoff button to do nothing once it has expired or been used, so that tapping a stale button can't create duplicates.
10. As a participant, I want to be told plainly when a Mode I was in has been withdrawn, so that I understand why I'm back in Daily.
11. As a participant, I want a Mode I haven't been invited to trial to be refused with a clear reason, so that I'm not misled.
12. As the founder, I want to grant a Mode to a specific participant for a fixed period, so that I can run a trial with up to five people.
13. As the founder, I want granting a sixth active participant to the same Mode refused, so that trial caps are enforced rather than remembered.
14. As the founder, I want to revoke a grant immediately, so that I can end a participant's trial.
15. As the founder, I want every grant change recorded with who made it and why, so that trial access is auditable.
16. As the founder, I want a Mode's handoff targets to be declared, so that no Mode can hand off to a Mode it wasn't designed to reach.
17. As a security reviewer, I want a handoff to be impossible without a participant button tap, so that a prompt injection can't move content into Daily.
18. As a security reviewer, I want the carried request treated as untrusted data in the target Mode, with the confirmation as the only authorization, so that the handoff can't smuggle instructions.
19. As a security reviewer, I want one participant never able to confirm another participant's handoff, so that handoff callbacks stay tenant-isolated.
20. As an operator, I want the migration to be additive and reversible, so that it deploys without risk to existing Sessions.
21. As the Gate A evaluator, I want Daily's instructions, Tool schema, and model unchanged, so that no evaluation evidence is invalidated.

## Implementation Decisions

- **Migration (protected; needs explicit human approval).** One additive migration, numbered after
  the parked pairing migration 015:
  - adds a nullable `active_mode_id` to `sessions` (null means the default Mode);
  - adds a `mode_grants` table: grant id, user id, Mode id, granted at, expires at, revoked at,
    granted by, and reason. It has row-level security matching the tenant-isolation policies, and
    a uniqueness rule that allows one active grant per participant and Mode;
  - adds a `mode_handoffs` table: handoff id, user id, session id, source Mode, target Mode,
    carried request, created at, expires at, and resolved at with the resolution. It also has
    row-level security.
  It also bumps the application schema version. The implementing agent drafts the migration and
  its SQL assertions, then stops for approval as migration 015 did. No code path depends on the
  migration until it is approved.
- **Store sync.** The new store methods are:
  - `get_active_mode` and `set_active_mode`;
  - `grant_mode`, `revoke_mode_grant`, and `get_active_mode_grant`;
  - `create_handoff` and `resolve_handoff`.
  Each lives in `MemoryStore` and is mirrored in `InMemoryStore` and `FakeStore`.
  `resolve_handoff` is atomic and single-use.
- **Routing policy.** `ExplicitThenSessionThenDefault` replaces the initial policy. If the Session's
  active Mode is no longer live or entitled, the runtime clears it and replies with a withdrawal
  notice. It does not process the message in Daily, because that message was meant for another
  Mode. It writes only the notice.
- **Entry and exit.**
  - `/mode` lists the Modes the participant may enter. `/mode <id>` enters one, and `/daily` exits
    to Daily.
  - Commands are handled in the Turn processor before the model runs, like `/feedback`. Buttons
    reuse the existing keyboard and callback pattern, and Telegram stays inside
    `src/channels/telegram.py`.
  - Entry replies with the Mode's declared name, purpose, and limits. `ModeDefinition` gains a
    declared, participant-facing `limits` text.
  - Entering and leaving are not model Turns and make no model call.
- **Handoff proposal Tool.** A Mode with declared handoff targets gets a `propose_handoff` Tool in a
  new Handoffs Toolset in the Tools module. It records a pending handoff and returns. The runtime
  then sends the participant the carried request with Confirm and Decline buttons. The Tool rejects
  a target the Mode didn't declare. Handoffs expire after a short, declared window.
- **Confirmation.**
  - Confirm resolves the handoff atomically, sets the Session's active Mode to the target, and
    runs one target-Mode Turn. That Turn's input is the carried request, framed as a
    participant-confirmed handoff and treated as untrusted content.
  - Decline or expiry resolves the handoff with no other effect.
  - A second tap, or another participant's tap, does nothing.
- **Grant entitlement.** A Mode may declare `entitlement="grant"`. `GrantedParticipants` allows
  such a Mode only while the participant holds an unexpired, unrevoked grant. Every other Mode
  keeps the existing activated-participant rule.
- **Grant operations.** An operator script grants, revokes, and lists grants. It refuses a sixth
  active grant for one Mode, requires an expiry (default 14 days) and a reason, and records the
  operator. It uses the store and never touches production data for tests.
- **Turn Record.** It gains an `entered_by` value (`explicit`, `session`, `default`, or `handoff`)
  and records handoff proposals, confirmations, and declines. It stays content-free.
- **Daily unchanged.** Daily declares no handoff targets and gets no Handoffs Toolset in this
  issue, so its Tool schema and instructions stay byte-identical.

## Testing Decisions

- **Test Mode.** A test-only live Mode with `entitlement="grant"` and `handoffs=("daily",)` is
  registered in a test registry. Production registration is unchanged apart from the routing
  policy.
- **Through the bot handlers, with a scripted model:**
  - entering, staying across Turns, leaving, and a new Session restarting in Daily;
  - entering a planned, unknown, or ungranted Mode is refused and writes nothing;
  - an expired or revoked grant sends the participant back with the withdrawal notice;
  - a proposal followed by confirm creates exactly one Task through Daily;
  - decline, expiry, a double tap, and a cross-participant tap each create nothing;
  - a proposal to an undeclared target is rejected;
  - a carried request that contains injected instructions can't widen Daily's Tools.
- **Store contract tests** run against all three store implementations for grants, the active Mode,
  and handoff single-use resolution.
- **SQL assertions** for the migration cover RLS isolation, the one-active-grant rule, and additive
  compatibility.
- **The grant script** enforces the cap, expiry, and revoke rules.
- **Unchanged Daily:** the Tool-schema hash and golden instructions pass unchanged.
- **Prior art:** `tests/test_modes.py`, the Reminder button callback tests, the tenant-isolation SQL
  assertions, and migration 015's parked assertion pattern.

## Out of Scope

- Coach or any specialized Mode's behaviour (issue 04).
- Automatic or suggested routing (issue 05).
- Dashboard Mode selection, the Mode chips, or showing the active Mode on the dashboard.
- Billing, subscriptions, or payment-backed entitlements.
- Mode-to-Mode delegation without a Mode switch (issue 07).

## Further Notes

- **Human touchpoints:** approving the migration, and choosing the handoff expiry window and the
  `/mode` wording.
- Choosing a per-Session active Mode, rather than a per-participant one, follows the glossary: a
  persistent program is not an active Mode. A Coaching Program persists separately (issue 04).

## Comments

### 2026-10-03 — Schema proposals prepared; adoption not authorized

- Issue 02 is closed after independent review; the backend suite remains green (558 tests).
- Migration 016 and rollback SQL assertions are parked in `../proposals/`. Review identified
  stale expiry checks after lock waits, a Mode-entry/revocation race, and grant checks that did
  not respect activated-participant entitlements. These were corrected in the proposals.
- Migration 015's original temporary SQL files were missing. New proposal bytes were
  reconstructed from migration 003 and the documented review corrections; historical hashes
  and verification do not certify the reconstructed files.
- The isolated 001–014 → reconstructed 015 → 016 chain and both assertion files pass.
  Independent concurrency verification remains pending; see the proposal review records for
  current evidence and hashes.
- No protected migration has been adopted, no Store/runtime path depends on the proposals,
  and Daily remains the only live Mode. Human approval is required before schema adoption.
