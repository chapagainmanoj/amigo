# Plan Reflect, Recommender, and a Separate CBT Research Experiment

Label: `wayfinder:map`
Status: open
Owner: unassigned

## Destination

Prepare reviewable, implementation-ready contracts for Reflect and Recommender, and a separately
governed CBT-informed research experiment. Planning does not enable any Mode or authorize a trial.

## Notes

- Requested by the project owner on 2026-10-03; parallel planning is explicitly authorized.
- Follow `CONTEXT.md`, ADR 0002, and the existing Mode and non-clinical wellbeing decisions.
- Canonical product term: **Recommender Mode**, not a separate Recommend or Discover Mode.
- Use Wayfinder decision tickets; research findings and draft plans are inputs, not human approvals.
- The referenced generic research/domain-modeling skills are not installed under those names;
  use primary-source research and the existing domain vocabulary. Use `grill-me` for human choices.
- Shared Mode implementation continues separately under `../modular-modes/issues/`.
- Parallel planning does not override demand gates or authorize parallel external Mode trials.
- CBT research audience is founder-only, as selected by the owner. The protocol ticket remains
  open until personal-data processing and safety controls are resolved; no other people are invited.
- The owner selected in-memory personal use with no saved transcripts. A fixed-fictional CBT flow
  preview has a separate implementer/reviewer PASS, not approval of personal or live-model use.
- Do not modify runtime registration, protected files, production data, or approved product claims.

## Decisions so far

- [Prefer Postponement over Indoor Alternatives When the Deadline Is Flexible](decisions/09-postpone-before-indoor.md):
  Avoid an unnecessary indoor-drying question; explore it only when postponement is impractical.
- [Recommend the Available Dryer When Rain Conflicts with Outdoor Preference](decisions/08-rain-dryer-recommendation.md):
  Give direct, explained advice rather than an unnecessary postponement question.
- [Use Simulated Weather for the Internal Laundry Prototype](decisions/07-simulated-laundry-weather.md):
  The owner chose fictional forecasts before source integration; the throwaway terminal flow is
  ready for a walkthrough, not a live Mode.
- [Choose Weather-Aware Laundry as the First Internal Scenario](decisions/06-first-recommender-scenario.md):
  The owner selected one contextual recommendation tracer; commercial domain/source approval
  and participant-demand evidence remain separate.
- [Separate CBT Research from the Commercial Roadmap](decisions/03-separate-cbt-research.md):
  The owner requested a limited research/experiment branch, not a commercial product Mode.
- [Locate CBT Research Within Existing Boundaries](decisions/04-research-cbt-boundaries.md):
  Non-clinical thought-check experiments fit a separate sandbox; treatment research would require
  a new scope and qualified governance, not a research label alone.

## Not yet specified

- Exact implementation slices after the human contracts, evidence, and privacy controls are approved.
- Any future proposal to promote a reviewed research artifact into Reflect; no automatic promotion.
- Study design and applicable jurisdiction if real participants are later proposed.

## Out of scope

- Enabling Reflect, Recommender, or CBT in this planning session.
- Commercial CBT, Therapy Mode, diagnosis, clinical screening, treatment, or medical advice.
- Reusing sensitive experiment content as Memory, product analytics, or training data by default.
- Resolving migration approval or claiming Coach is live.
