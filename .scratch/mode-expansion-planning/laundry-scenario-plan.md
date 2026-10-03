# Weather-Aware Laundry — First Internal Recommender Scenario

Status: scenario selected; throwaway simulated prototype available; production not enabled
Prepared: 2026-10-03
Decision: [Choose the First Internal Scenario](decisions/06-first-recommender-scenario.md)

## Job

Help the participant decide whether to do laundry now, choose another available drying option,
or postpone, using their stated objective and actual constraints. Do not guarantee drying times
or claim one option is universally best.

## Proposed minimum inputs

- Drying options actually available: dryer, outdoor line, or indoor drying; never invent equipment.
- Urgency: when the participant needs the clothes ready, and whether postponing is acceptable.
- Available washing/drying window and any participant-stated constraints or preferences.
- Weather only when an option depends on it; location comes from the participant, not inference.
  Do not collect location or call a weather source when it is unnecessary to compare the options.
- Weather records carry source, retrieval time, forecast location, forecast interval, and relevant
  conditions. Provider, licensing, freshness thresholds, and uncertainty rules are still open.

Facts, preferences, temporary circumstances, and external evidence remain separate. Use current
request facts without automatically saving them. Persistent equipment/preference information
would require an explicit save/inspection/correction contract before it is implemented.

## Proposed first output

A concise recommendation, the participant-specific reasons, important uncertainty, and one
feasible alternative where supported. Ask one necessary clarification instead of guessing.
If evidence cannot support a weather-dependent decision, say so; do not interpret missing weather
as good weather or turn forecast information into a promise that laundry will be dry.

Advice alone changes nothing. No Task/Reminder Tools, proactive notifications, purchases,
unconfirmed handoffs, or background preference learning. A later participant-requested Task uses
Daily's separately implemented confirmed workflow; it is not part of the first proposed tracer.

Confirmed internal rule: when rain is expected, outdoor drying is a preference rather than a hard
restriction, and a suitable dryer is available, recommend the dryer directly and explain why.
[Owner decision](decisions/08-rain-dryer-recommendation.md). Other branches remain proposed.

## Proposed verification cases

- Outdoor drying with usable weather evidence and a flexible deadline.
- Rain expected during the available outdoor window, with versus without another drying option.
- A dryer is available but the participant prefers outdoor drying: explain the trade-off rather
  than treating either equipment availability or preference as the whole objective.
- Urgent deadline with insufficient evidence of a feasible drying option: be honest, not reassuring.
- Indoor-only drying, with no weather/location dependency.
- Missing drying method, missing urgency, unknown location when weather is necessary, or stale,
  unavailable, wrong-location, or wrong-interval weather.
- Participant correction: equipment or preferences change and the recommendation must follow it.
- Requests to save a preference, inspect other Modes, or create a Task: no implied side effect.
- Prompt injection in participant text or source data cannot widen Tools or read other Mode history.

## 2026-10-03 — Simulated weather selected

The owner accepted simulated weather first. A throwaway, rule-based terminal prototype is at
[Laundry Prototype](laundry-prototype/README.md). It does not implement or register a production
Mode. Its branch rules are discussion inputs, not approved recommendation policy or model evidence.

## Next decision after founder walkthrough

Recommended: first validate the decision flow with explicitly labelled synthetic weather fixtures.
This can test grounding, trade-offs, uncertainty, and refusal without choosing a live source or
collecting personal location. Synthetic results are not live-weather or participant-demand evidence.

Alternative: begin with a live weather adapter, which first requires provider/source approval,
location minimization, terms and cost review, freshness rules, and outage behavior. No source is
selected. The existing simulated prototype provides no live-source evidence.

Commercial Recommender remains blocked by the existing demand and domain/source decisions.
