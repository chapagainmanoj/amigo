# Recommender Mode Expansion Plan

Status: planning only
Canonical Mode: **Recommender Mode** (`recommender`)
Proposed participant-facing action: **Recommend** (copy not yet approved)
Current catalogue state: `planned`, no Toolsets, confirmed handoff target `daily`
Decision owners: founder for the domain/data contract; independent participants for demand evidence

## Purpose and present boundary

Recommender Mode serves one job only:

> Help me choose among options in one approved recommendation domain using my stated preferences
> and explainable trade-offs.

This plan does not select that domain, approve a source, or authorize implementation. The current
catalogue is correct: Recommender stays `planned`, receives no Tools, and cannot be entered. The
proposed participant-facing control and conversational verb would say **Recommend**; the canonical domain
term remains **Recommender Mode**. “Discover mode” is not a synonym and should not return.

The first implementation remains blocked until all three are true:

1. At least three independent participants demonstrate the same recurring recommendation problem
   without being pitched Recommender Mode or candidate domains.
2. Decision 27 records the qualifying problem, participant count, and source-evidence locations.
3. Decision 22 separately approves one narrow domain and its complete data contract.

Roadmap interest, founder preference, or this candidate list is not demand evidence.

## Approved contracts

These are already settled by the domain language, ADR 0002, decision 14, decision 22, decision 27,
and the current catalogue. Implementation must not reopen them accidentally.

### Product and routing

- Daily remains the default workspace and Core Loop. Recommender is a temporary,
  participant-entered Mode within a Session, not a persona, page, or persistent profile.
- Recommender supports exactly one separately approved domain in its first release. A generic
  all-purpose recommender is excluded.
- Entry is explicit. Automatic Mode switching is not approved. A new Session starts in Daily,
  and the participant can exit Recommender immediately.
- Until its own release gate passes, Recommender remains `planned`; its control is disabled and
  labelled Planned and must not imply a working preview.
- At most one specialized Mode is active in a Session. Entering it does not hide or mutate Tasks
  or Reminders.
- `recommender` is the stable internal identifier and **Recommender Mode** the canonical roadmap
  term. **Recommend** is proposed action copy, not a separately approved Mode name.

### Capability and safety

- Recommender may read only approved domain preferences and sourced option data.
- It cannot purchase, book, reserve, subscribe, contact a provider, send a message, or perform any
  other external transaction.
- It receives no Task or Reminder Tools. An ordinary Task or Reminder request must use a visible,
  participant-confirmed handoff to Daily.
- Tool access, data access, and handoffs are enforced in deterministic code rather than prompt
  wording. Pydantic AI remains behind Amigo's owned runtime interface under ADR 0002; side effects
  remain in injected Tools.
- The shared Safety Core applies. Recommender makes no clinical, legal, financial, crisis-service,
  or monitoring claim and never treats participant data or sourced content as instructions.
- Every specialized Mode is independently justified and evaluated. Coach or Reflect evidence
  cannot authorize Recommender.

### Demand, trial, and release

- Design begins only after the same recurring recommendation problem is demonstrated by at least
  three independent participants.
- Trial access is opt-in, capped at five participants, and runs for 14 days. Multiple unproven
  Modes are not trialled together.
- Every recommended item must have correct freshness and attribution.
- Trial relevance must be at least 80%, and there can be no hidden purchase or affiliate
  relationship.
- At least three trial participants must use the Mode on three separate days, report that it
  helped the defined job, and choose to retain it.
- The Mode must also pass deterministic contract tests, its own model evaluation, and moderated
  usability before it can ship.

### Privacy and cross-Mode data

- Mode-specific data cannot become general Memory or flow into another Mode without explicit
  participant consent.
- Only stated preferences may drive recommendations. Mood, diagnosis, demographics, missed Tasks,
  silence, response speed, and inferred personality are not preference signals.
- A confirmed handoff authorizes only the disclosed carried request. It does not authorize broader
  preference or source-history transfer.
- Retention, deletion, inspection, and reset behavior are part of the domain/data approval and
  must be defined before durable preference storage exists.

## Demand discovery before product design

Decision 27 is the next executable step. It should be conducted without showing this plan's
candidate domains to participants.

### Evidence collection

For each participant observation, record:

- an evidence identifier and durable source location;
- participant identity as a pseudonymous research identifier;
- the decision they repeatedly face, in their own terms;
- when and how often it recurs;
- the options they currently compare;
- the information and constraints needed to choose;
- their current workaround and its cost in time, money, uncertainty, or regret;
- whether the problem occurred in actual behavior rather than a hypothetical interview answer.

Do not count multiple statements by one participant as independent demand. Group problems only when
the decision, needed option set, and success criterion are substantively equivalent. Record
near-matches separately rather than merging them to reach three.

### Gate result

Decision 27 should end in one of three explicit outcomes:

- **passed:** one problem has three or more independent participants and can enter decision 22;
- **insufficient:** evidence remains below threshold and collection continues;
- **do not build:** the problem is too infrequent, better solved elsewhere, unsafe, or incompatible
  with the non-transaction boundary.

Only `passed` opens domain/source selection. It does not itself approve a domain or source.

## Low-risk candidate domains to assess, not select

These candidates are planning prompts for evaluating a problem *after* blind demand collection.
They are not recommendations to participants and do not satisfy the demand gate.

| Candidate | Why it may be comparatively low risk | Risks and data questions that remain |
|---|---|---|
| Books for leisure reading | Reversible choice; low consequence; strong metadata and creator/publisher provenance are possible | Availability varies by region; edition metadata and content descriptors can be stale or incomplete; no retailer or library source is approved |
| Films or series for leisure viewing | Reversible choice; preferences and trade-offs are explainable; no action is needed beyond presenting options | Streaming availability changes quickly by region; age/content classifications vary; no catalogue source or freshness window is approved |
| Free learning resources for a participant-stated topic | Can be limited to non-credentialed, non-clinical learning and official/open catalogues | Quality, level, accessibility, and link rot need validation; professional certification, medical, legal, and financial education must be excluded from v1 |
| Low-cost, non-sensitive leisure activities | Can focus on reversible ideas rather than booking and can abstain when local facts are unavailable | Location is personal data; opening hours, weather, accessibility, and safety change rapidly; a trustworthy local source is not approved |

The first domain should avoid medical or wellbeing advice, finance or investment, legal decisions,
employment or admissions, housing, insurance, intimate relationships, products with material safety
risk, and any choice where a wrong answer can cause substantial harm or irreversible loss. These
exclusions reduce risk; they do not determine which candidate has demand.

## Proposed implementation contract

Everything in this section is a proposal for decision 22 or subsequent implementation review. It
is not approved merely because it is written here.

### 1. Approved-source adapter

Create one read-only domain adapter behind an owned interface. The model receives structured option
records, never raw webpages or arbitrary connector output. No generic web-search fallback is
allowed: an unavailable or insufficient approved source causes abstention.

Proposed option record:

- stable source and option identifiers;
- participant-facing title and short factual description;
- domain-specific comparable attributes;
- region or availability scope where relevant;
- canonical attribution label and source URL;
- source-published or source-updated time when available;
- Amigo retrieval time and freshness deadline;
- price only when required by the approved domain, with currency and observed time;
- content or safety markers required by the domain contract;
- an allowlisted source license/usage-policy identifier.

Raw source text is untrusted data. It cannot expand Tools, change system instructions, or authorize
a handoff or transaction. The adapter validates its schema and rejects malformed, sourceless, or
out-of-contract records before the model sees them.

### 2. Provenance and attribution

Every presented option should be traceable to at least one approved source record. Each response
should distinguish:

- **source facts:** availability, creator, date, price, category, or other verified attributes;
- **participant facts:** preferences or constraints explicitly supplied by the participant;
- **Amigo's comparison:** the explained trade-off derived from those two inputs.

The response should show compact source attribution beside each item and a retrieval/freshness
label when the information can change. Unsupported factual claims are omitted, not filled in from
model memory. Conflicting approved sources trigger an explicit conflict note or abstention under
the domain contract.

### 3. Freshness

Decision 22 must approve freshness rules per attribute, not one vague Mode-wide duration. Proposed
rules:

- immutable or slow metadata can use a longer cache window;
- availability, price, schedule, opening time, or regional access uses a short domain-specific
  window;
- freshness is calculated from the trusted retrieval time, with source update time retained as
  additional evidence rather than trusted alone;
- expired dynamic fields are not presented as current;
- if refreshing fails, the response either omits the expired claim or abstains from that option;
- every evaluation fixture carries a fixed clock and tests both sides of each freshness boundary.

The exact windows remain open until the domain and source behavior are known.

### 4. Preference controls

Use preferences stated in the current Turn or explicitly confirmed by the participant. Proposed v1
controls are:

- include, exclude, or require a domain attribute;
- indicate a soft preference versus a hard constraint;
- inspect the preferences used for the current recommendation;
- correct or remove one preference;
- reset all Recommender preferences;
- request a different trade-off without silently changing the saved profile.

Session-scoped preferences should be the default. Any durable domain preference requires separate,
explicit “save this preference” consent, a visible Recommender-only store, and inspect/delete/reset
controls. Do not infer a durable preference from clicks, silence, purchase behavior, Tasks, mood,
demographics, or repeated model guesses.

### 5. Response and abstention

A successful response should present a small option set, explain how each item fits the stated
constraints, identify meaningful trade-offs, state important uncertainty, and show provenance. It
should not present a hidden ranking as objective truth.

Recommender should abstain, narrow the question, or ask one clarification when:

- no approved source covers the request;
- source data is missing, stale, conflicting, or outside its licensed use;
- the request crosses the approved domain, geography, price range, or safety boundary;
- hard preferences leave no supported option;
- the participant has not supplied a preference necessary to distinguish options;
- the request is high-stakes or asks for diagnosis, legal/financial judgment, or crisis help;
- the participant asks it to transact, contact, book, purchase, or subscribe;
- confidence cannot be grounded in the returned source records.

Abstention is a correct outcome and must not silently fall back to general model knowledge.

### 6. Privacy and retention

Proposed minimization rules:

- send the source only the minimum query needed for the approved domain;
- do not send participant name, Telegram/chat identifiers, Task titles, Session transcript, or
  general Memory unless the source contract requires a specific field and the participant has
  explicitly approved it;
- use coarse location or participant-entered region when sufficient; never infer or continuously
  track precise location;
- keep operational telemetry content-free under the existing Turn Record contract;
- separate source cache data from participant preferences;
- declare preference and recommendation-history retention periods before trial;
- support participant inspection, correction, deletion, and reset before durable storage ships.

Decision 22 must record the source processor/subprocessor status, hosting geography, retention,
training use, deletion behavior, licensing terms, rate/cost limits, and incident handling.

### 7. No external transactions or commercial steering

No Tool may complete or initiate a purchase, booking, reservation, subscription, provider contact,
or affiliate redirect. Source links may be shown for attribution or participant-led follow-up only
if decision 22 approves that behavior. The response must not claim an action was taken.

Any commercial relationship, sponsored placement, paid ranking, referral tracking, or affiliate
fee must be disclosed and separately approved before use. Hidden influence is a release blocker
and an immediate stop condition. Ranking must be reproducible from participant preferences and
declared option attributes, not commercial value to Amigo.

## Evaluation plan

Recommender gets its own suite; Daily's Gate A evidence cannot substitute for it.

### Deterministic contract suite

Cover at least:

- explicit entry/exit, planned/unentitled refusal, and new-Session return to Daily;
- exact Tool membership: approved read-only source/preference Tools plus confirmed handoff only;
- no Task, Reminder, transaction, outbound-contact, or undeclared-source Tool;
- tenant isolation and cross-Mode data isolation;
- current-Turn and explicitly saved preference handling, correction, deletion, and reset;
- source schema validation, provenance presence, licensing allowlist, cache and freshness boundaries;
- stale, missing, malformed, conflicting, injected, or unavailable source data causing omission or
  abstention rather than unsupported output;
- confirmed handoff to Daily and decline, expiry, duplicate tap, and cross-participant refusal;
- content-free telemetry and no participant content in logs or traces;
- no source call containing undeclared participant fields;
- every declared invalidating input forcing the Mode evaluation to rerun.

### Model evaluation

Build cases from the approved domain and real demand language. Score:

- source-grounded factual correctness and attribution;
- freshness correctness for every dynamic claim;
- hard-constraint compliance and soft-preference adherence;
- explanation of meaningful trade-offs without invented certainty;
- relevance, including the approved minimum of 80% during trial;
- calibrated clarification and abstention;
- resistance to participant and source-data prompt injection;
- refusal of high-stakes, out-of-domain, and transaction requests;
- correct confirmed handoff behavior for an ordinary Task or Reminder request;
- response usefulness and participant ability to understand why options were shown.

The release candidate must pin the Mode instructions, Tool schema/order, model policy, source
adapter/version, data snapshot or reproducible fixture, freshness policy, evaluation cases, and
dependency versions. A change to any of these invalidates its evidence.

### Moderated usability

With five participants:

- all five identify that Recommend is a specialized Mode and state its domain and limits;
- at least four enter, exit, decline/confirm a Daily handoff, and control preferences without help;
- participants can find provenance, recognize uncertainty, and distinguish source facts from
  Amigo's comparison;
- no participant believes Amigo purchased, booked, contacted, monitored, or independently verified
  an option beyond the cited source.

### Trial and release evidence

Run one 14-day opt-in trial with at most five participants only after deterministic, model, privacy,
security, and moderated-usability gates pass. Release requires all approved decision-14 evidence,
including:

- every presented item has correct freshness and attribution;
- at least 80% of rated recommendations are relevant;
- no hidden purchase or affiliate relationship;
- at least three participants use Recommend on three separate days, say it helped the approved
  job, and choose to retain it;
- no unauthorized Tool, data-flow, transaction, or cross-account/cross-Mode event.

## Stop conditions

Stop the design, implementation, or trial immediately when any of these occurs:

- the three-independent-participant demand gate is not met or the grouped problems are not truly
  equivalent;
- no source can meet the approved provenance, freshness, licensing, privacy, reliability, and cost
  contract;
- an unauthorized Tool, external transaction, or unconfirmed Daily handoff executes;
- participant data, Mode-specific preferences, or source queries leak across accounts or Modes;
- a recommendation uses stale or unsupported facts, hides attribution, or bypasses abstention;
- a hidden affiliate, sponsored, purchase, or ranking relationship is discovered;
- a clinical, legal, financial, crisis-service, monitoring, or other high-stakes claim appears;
- privacy inspection, deletion, reset, or retention controls fail;
- participants cannot identify the active Mode or reasonably understand why options were shown;
- the relevance, repeated-use, helpfulness, or retention thresholds are missed;
- a source changes terms, schema, coverage, or reliability such that existing evidence is no longer
  valid.

A documented Do Not Build decision is an acceptable successful outcome.

## Vertical slices and dependencies

Each slice should be independently reviewable and should end in observable evidence rather than a
horizontal layer that cannot be exercised.

| Slice | Participant-visible tracer bullet | Dependencies | Exit evidence |
|---|---|---|---|
| 0. Demand gate | Research records one real recurring decision problem without exposing a Mode | Decision 14 closed | Decision 27 records three independent participants for one equivalent problem, or an explicit insufficient/do-not-build outcome |
| 1. Domain and source contract | A reviewer can inspect the exact domain boundary, source, freshness, attribution, privacy, preference, cost, and disclosure rules | Slice 0 passed | Founder-approved decision 22; source terms and processor review; no domain selected by roadmap alone |
| 2. Read-only source tracer | Given one approved query fixture, the adapter returns validated, attributable, fresh option records or an explicit unavailable result | Slice 1 | Contract tests for schema, provenance, freshness, injection, outage, license, and cost boundaries; no model or participant data write |
| 3. One grounded Recommend Turn | An explicitly entered test participant asks one qualifying question and gets sourced options, trade-offs, or a correct abstention | Slices 1–2; Mode foundation and model-policy/evaluation work accepted | Recommender-specific instructions, read-only Toolset, Turn Context, no-transaction boundary, scripted end-to-end test, prompt/Tool snapshots |
| 4. Preference control | The participant states, inspects, corrects, removes, and resets the preferences used by a recommendation | Slice 3; approved retention choice; protected migration approval if durable data is chosen | Session-only flow or separately approved durable store; tenant/privacy tests; no inferred preference |
| 5. Confirmed Daily handoff | A Task request inside Recommend shows the carried request and creates exactly one Task only after confirmation | Explicit switching/trial-grant issue 03 and its migration approved | Confirm/decline/expiry/replay/cross-tenant tests; Recommender never receives Task or Reminder Tools |
| 6. Recommender evaluation gate | The exact release candidate passes deterministic and model scenarios with current source/freshness evidence | Slices 2–5; approved model and evaluation contract | Independent security/privacy review, full Mode evaluation artifact, no unresolved critical failure |
| 7. Moderated trial readiness | Five participants can enter/exit Recommend, control preferences, see provenance, and understand limits | Slice 6 | Decision-14 moderated thresholds met; trial copy/support/runbook approved |
| 8. Fourteen-day opt-in trial | Up to five granted participants use one narrow Recommend domain in real decisions without Amigo transacting | Slice 7; trial grants and telemetry operational | Relevance, repeated-use, helpfulness, retention, freshness, attribution, privacy, and no-commercial-steering evidence reviewed independently |
| 9. Ship, revise, or stop | Participants see Recommend enabled only if every gate remains current | Slice 8 | Explicit founder release decision; otherwise keep planned, revise, disable, or record Do Not Build |

Dependency order is strict: slices 2–9 cannot run before decisions 27 and 22 close. Durable preference
work cannot start without its retention/privacy choice and any protected migration approval. Trial
entry and confirmed handoff depend on issue 03. Recommender must never be bundled with Reflect or a
clinical/wellbeing initiative; those have separate demand, safety, and release decisions.

## Proposed work packages after approval

Once decision 22 closes, convert the applicable slices into independently grabbable issues:

1. source contract and read-only adapter;
2. Recommender Mode definition, instructions, Toolset, and Turn Context;
3. preference controls and, only if approved, durable preference storage;
4. confirmed Daily handoff integration;
5. deterministic and model evaluation suite;
6. moderated-usability and trial runbook;
7. evidence review and ship/revise/stop decision.

Do not create implementation tickets for a domain-specific adapter, prompt, schema, or evaluation
set until the demand and domain/data decisions are both closed.

## Open questions for decision 22

1. Which real recurring problem passed the three-independent-participant demand gate?
2. What is the exact in-domain request, and which adjacent requests are explicitly out of scope?
3. Which source or source combination is approved, under what license, cost, quota, geography, and
   commercial relationship?
4. Which attributes are authoritative, and what freshness window applies to each dynamic field?
5. What does the Mode do when sources disagree, omit a field, cover the wrong region, or fail?
6. Which preferences are necessary, which are sensitive, and which remain Session-only?
7. Is durable preference storage justified? If so, what consent, retention, inspection, deletion,
   reset, and migration contract is approved?
8. How many options should one Turn present, and what diversity or exploration rule prevents a
   repetitive hidden ranking?
9. How is attribution shown in Telegram and the dashboard without implying independent
   verification?
10. Are outbound source links allowed for participant-led follow-up, and how are tracking and
    affiliate parameters prohibited or disclosed?
11. What response latency, source availability, and per-active-participant cost are acceptable?
12. Which exact events force abstention, disable the Mode, invalidate evaluation evidence, or end
    the trial?

Until these questions and decisions 27/22 are resolved, the correct production behavior is the
current one: Recommender stays planned, cannot run, and performs no read, write, or transaction.

## 2026-10-03 — Founder hypothesis: contextual everyday choices

The founder described a broader long-term job: help choose what fits the participant's preferences,
constraints, and present circumstances. Examples include clothing, meals, films, leisure activities,
and whether to do laundry when drying depends on owning a dryer versus sunlight and weather.
These are founder hypotheses, not independent demand evidence or an approved domain selection.

This broadens the approved one-domain release contract and raises an unresolved preference-learning
choice. Do not silently replace the current contract or declare the demand gate passed.

Proposed architectural direction, not approved implementation:

- Keep one Recommender Mode with separately declared domain adapters, rather than a Mode for each
  choice. A future multi-domain contract must explicitly authorize each adapter and its data.
- Separate participant-stated preferences, factual constraints, temporary scenario context, sourced
  option facts, and candidate preference inferences. A dryer is a factual constraint, not a taste;
  tonight's available time is temporary context, not a lasting preference.
- Explicit preferences may be used in the current request; saving them remains an explicit choice.
  Behavioral evidence can at most propose a correction-ready candidate pending approval of a
  learning contract. One selection does not establish a durable preference.
- Eligible participant-confirmed general Memory could be shared only under its authorized-use
  contract. Do not read other Modes' transcripts to infer tastes, emotions, health, or personality.
  Reflect and CBT research content remain outside recommendation learning.
- Present supported choices and trade-offs relative to the participant's stated objective; do not
  claim an objective universal best option. Missing scenario/source facts require clarification or
  abstention, not invented availability, weather, wardrobe, ingredients, or equipment.
- Laundry reasoning is read-only. Creating a Task or Reminder still requires a confirmed Daily
  handoff. Prioritizing an already-owned Task may instead belong to Daily; that ownership decision
  is open and must not create hidden Mode switching.

Candidate internal tracer: weather-aware laundry decisions, with explicit dryer/drying-method,
coarse participant-provided location, a verified forecast or supplied synthetic weather fixture,
and the participant's urgency/time constraints. This demonstrates contextual choice without
claiming a wardrobe, food, entertainment, and household recommender are all ready.

The owner selected weather-aware laundry decisions as the first internal scenario on 2026-10-03.
See [the scenario decision](decisions/06-first-recommender-scenario.md) and
[proposed scenario contract](laundry-scenario-plan.md). Selecting this scenario does not authorize
implementation, external testing, a live source, or a commercial multi-domain release. The next
choice is synthetic weather fixtures versus an approved live-weather adapter.
