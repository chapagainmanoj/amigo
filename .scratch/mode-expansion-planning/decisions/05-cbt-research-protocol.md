# Approve CBT Research Audience and Protocol

Parent: [Mode Expansion Planning](../MAP.md)
Status: open
Label: `wayfinder:grilling`, `ready-for-human`
Type: HITL / grilling
Severity: `severity:critical`
Owner: unassigned
Blocked by: none

## Question

Is the initial experiment restricted to synthetic internal scenarios, founder personal use, or
real adult participants, and what qualified review, consent, data policy, and stop rules are needed?

## Comments

2026-10-03: Asked the owner to choose the initial audience. Recommended synthetic internal
scenarios first.

### 2026-10-03 — Audience selected; protocol remains open

The owner chose founder-only personal experimentation. No other participants or commercial use
are authorized. Synthetic cases precede personal use as verification fixtures. Exact template,
non-clinical research question, provider processing/retention, consent to personal-content handling,
access isolation, stop controls, and verification remain unresolved; keep this ticket open.

### 2026-10-03 — In-memory personal data selected; synthetic preview reviewed

The owner selected no saved personal transcripts, with in-memory use only. Treat inputs, replies,
and derived summaries as personal content; do not retain them or copy them to telemetry. This
choice does not approve provider retention/processing, exact templates, or personal input yet.

A separate implementation agent built a fixed-fictional control preview and another agent
independently reviewed it. PASS is restricted to that synthetic scope: no arbitrary personal input,
model/network, production imports/registration, persistence, Tools, or participant access.
Demo/manual state-control checks, lint, and whitespace passed. This is not clinical, safety,
privacy-release, or personal-use approval. [Preview and remaining gaps](../cbt-research-prototype/NOTES.md).

### 2026-10-03 — Guided-question style selected

The owner accepted guided questions for a founder-entered thought instead of supplying fixed
interpretation choices: one question at a time, every step optional, immediate stop available.
The founder retains ownership of interpretations and any takeaway. Do not grade personal answers
against the fictional preview's predetermined choices or impose a positive reframe.

This resolves interaction style only. Exact template wording, bounded scope/length, personal-input
isolation, provider handling, and safety verification remain open. The existing fictional preview
is unchanged and must not be presented as the approved personal flow.

### 2026-10-03 — Bounded format selected

The owner accepted one everyday situation per run, ending with an optional participant-owned
takeaway rather than indefinite conversation. Every step remains optional; stopping early is
a valid outcome. Do not silently continue into another situation or reopen a completed run.

This resolves format only. Exact prompts, numeric Step/model-call limits, personal-input and
provider handling, qualified template review, and safety verification remain open.

### 2026-10-03 — Research focus and practitioner involvement clarified

The owner confirmed **CBT-informed thought examination**, not broad supportive conversation.
The owner is not a CBT expert and plans to involve someone qualified to make the method
CBT-informed. No practitioner has yet been appointed and no protocol review is claimed.

A rigid question sequence was challenged because it may not fit every scenario. The intended
research direction is to compare bounded adaptive sequencing against a fixed baseline, using
practitioner-defined question patterns, applicability/exclusions, and a review rubric. Exact
adaptation rules remain proposed until practitioner review and owner approval. Do not claim that
AI follows expert practice or provides therapy because its language sounds plausible.

See [Practitioner Collaboration Brief](../cbt-expert-brief.md). Founder-only access, one everyday
situation, optional steps/takeaway, immediate stop, and no saved personal transcripts still apply.

### 2026-10-03 — MVP destination and next phase clarified

The owner is still looking for a qualified practitioner and identified recruitment/method review
as the next CBT phase. The desired destination is an MVP-sized research mode, not a commercial
therapy feature. The proposed MVP is a separate synthetic comparison harness for a fixed baseline
and bounded adaptive questioning; method/rubric review remains required. Personal use and provider
processing are not approved by this scope clarification. This protocol decision remains open.

### 2026-10-03 — Owner correction: MVP before practitioner collaboration

This supersedes the preceding sequence: build a small research MVP first, then involve a qualified
practitioner and pursue further research together. Do not block engineering on recruitment or
describe the initial patterns as practitioner-reviewed. The initial synthetic comparison uses
provisional patterns and an engineering rubric; expert validation and clinical efficacy are not
claimed. Founder-only/no-saved-transcript boundaries remain. Personal-input/provider processing
still needs explicit approval of the actual implementation and data contract.
