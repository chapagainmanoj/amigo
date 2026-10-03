# Recommend the Available Dryer When Rain Conflicts with Outdoor Preference

Parent: [Mode Expansion Planning](../MAP.md)
Status: closed
Label: `wayfinder:grilling`, `done`
Type: HITL / grilling
Severity: `severity:low`
Owner: unassigned
Blocked by: [Use Simulated Weather](07-simulated-laundry-weather.md)

## Question

If the participant prefers outdoor drying but rain is expected and a dryer is available,
should Amigo recommend the dryer or ask whether to postpone?

## Comments

### 2026-10-03 — Owner decision

Recommend the dryer directly, explaining that expected rain conflicts with outdoor drying.
Do not require an extra postponement question before giving useful advice. The dryer must be
declared available and suitable for these clothes; a preference for outdoor drying is not a
hard prohibition against the dryer. Explicit restrictions still override this recommendation.

The simulated prototype already follows this branch. This confirms one internal decision rule,
not the complete prototype, a guaranteed drying time, commercial release, or real-weather evidence.
