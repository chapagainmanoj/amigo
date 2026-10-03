# Use Simulated Weather for the Internal Laundry Prototype

Parent: [Mode Expansion Planning](../MAP.md)
Status: closed
Label: `wayfinder:grilling`, `done`
Type: HITL / grilling
Severity: `severity:low`
Owner: unassigned
Blocked by: [Choose the First Internal Scenario](06-first-recommender-scenario.md)

## Question

Should the first internal laundry prototype use simulated weather or connect a live source?

## Comments

### 2026-10-03 — Owner accepted simulated weather first

Use fictional weather fixtures to examine the decision flow before selecting a live provider.
The throwaway [terminal prototype](../laundry-prototype/README.md) is rule-based and in-memory,
with no production imports, model calls, weather requests, or Task/Reminder effects.
Its eight demo scenarios and interactive option/weather/urgency changes ran successfully; Ruff
and whitespace checks passed. Founder walkthrough and policy feedback remain pending. These
checks are not release evidence or validation of real forecasts, drying times, or personalization.
