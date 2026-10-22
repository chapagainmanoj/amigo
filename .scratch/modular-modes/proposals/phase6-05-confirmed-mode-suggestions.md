# Issue 05 — participant-confirmed Mode suggestions

Status: provisional — owner review
Date: 22 October 2026
Implementation: disabled application/Store candidate; no live admission.
Sources: Issue 05; decisions 14, 23 and 28; build-plan Phase 6.

## Decision

Build a disabled-by-default application policy for an explicit suggestion followed by confirmation.
Do not build silent routing or Interaction Style adaptation. Decisions 23 and 28 remain open;
passing software/model tests does not constitute the required two independently qualified Mode
releases or measured switching-friction evidence.

Use a narrow deterministic rule set over the participant's current explicit request, after the
current Turn. It may identify the job “pursue a goal or habit” or “examine a specific experience”;
it must not infer sentiment, mood, diagnosis, personality, silence, response speed or Task behavior.
No extra model call, new Daily Tool or Daily instruction change. No rules over stored Reflect,
Coach or future Memory content. A rule match is only permission to offer, never to route.

## Proposed behavior

- Admission requires the feature gate, real release/friction evidence, a live target Mode, current
  entitlement and that Mode's privacy readiness. Check again at confirmation.
- Offer at most once per Session. A decline suppresses further suggestions for that Session;
  a participant “stop suggesting” preference persists until explicitly reversed.
- Suppress offers during Crisis Referral, pending participant confirmation, or an incomplete
  Tool/handoff operation. The current reply must remain coherent without the offer.
- The initial action is **Open Mode**, with the target's purpose/limits shown. Confirmation opens
  its canonical conversation or invokes the same explicit command entry path on a non-threaded
  channel. It does not copy source history, execute a target Turn, or carry a request invisibly.
- If carrying the current request is later offered, show its exact bounded preview and use the
  existing confirmed handoff; this is a separate explicit choice from opening a Mode.

Use a durable metadata-only proposal with owner, source Session, target Mode, expiry, version and
single-use resolution. Reuse the confirmation dispatcher pattern, not the `mode_handoffs` execution
RPC for an Open Mode action. The latter would execute carried content and change the semantics.
Callbacks derive the actor from authentication, never payload identity. Expired, foreign, replayed,
withdrawn or unentitled confirmations do nothing. No proposed content enters routine telemetry.

## Acceptance and remaining evidence

Offline tests must cover both channel capability paths, zero pre-confirmation route/Session changes,
repeat suppression, owner isolation, callback replay, revoked grants, crisis suppression, forbidden
signals, and byte-identical Daily instructions/Tool schema. Evaluate eligible-job precision and
irrelevant offers on a versioned fictional set before any opt-in trial.

Owner review must approve the exact rule vocabulary and offer copy. Decisions 23/28 still require
real participant evidence; the default stays off until those gates are actually satisfied.


## Implemented Phase 6 slice

`ModeSuggestionController` runs after a successful Daily reply and uses only the current explicit
job request. Three conservative authored rules target habit-building, reflection, or fictional
laundry comparison. It adds no model call or Daily Tool/instruction. An immutable offer UUID binds
the exact target; there is no mutable proposal payload or carried content. Store metadata contains
owner, source Session, target, trusted grant requirement, expiry and single-use resolution.

Migration021 and both local Stores enforce one offer per owned open Daily Session, permanent
Session suppression after decline/expiry, persistent participant on/off preference and current
grant checks. Pending Handoff/Coach approvals suppress creation. Confirmation checks current
catalogue/readiness and grant again, then invokes explicit `/mode` preparation: opens the canonical
conversation/Session and displays purpose/limits without a target Turn or source-message copy.
Source history never moves. A crash after consuming confirmation may require manual `/mode`;
there is no deferred target execution to recover or accidentally repeat.

Real admission stays OFF. Feature/release/friction/policy readiness all default false. Additionally,
per-Turn affirmative safety/operation clearance defaults to denial: the existing Turn result does
not expose reviewed authoritative Crisis Referral/incomplete-operation metadata. Lexical crisis
suppression is defense in depth, not a complete detector. A reviewed clearance implementation is
required before activation; a successful regex match cannot waive it. Fictional tests inject
explicit clearance and readiness. `/suggestions on` only permits future approved offers; it cannot
enable feature/release/privacy gates.

The authored rule tests cover narrow positive jobs, irrelevant mood/Task-behavior inputs, ambiguous
jobs, commands and explicit crisis suppression. Software precision on those fixtures is not real
switching-friction evidence or a validated generalized intent classifier. Decisions23/28 remain
open. Independent migration review and full-chain proof are recorded separately.
