# Prototype Findings

Status: founder discussion in progress; rain/dryer and postpone-first rules confirmed

## Decisions already made

- First internal scenario: weather-aware laundry decisions.
- Data for this prototype: simulated weather, not a live provider.
- Advice only; no persistence, inferred preferences, Tasks, or Reminders.

## Questions to answer by trying it

- Does the advice explain the trade-off you care about, or optimize the wrong objective?
- When should urgency change a recommendation rather than just add a deadline caveat?
- Does a preferred outdoor method justify examining weather when a dryer is available?
- Is abstention useful when weather is missing or stale, and are clarification questions necessary?
- What additional participant-supplied fact is truly necessary before the answer becomes useful?

No actual-user helpfulness, demand, weather accuracy, or drying-time evidence has been collected.

## 2026-10-03 — Rain with available dryer

The founder confirmed: recommend the dryer when rain is expected and a suitable dryer is available,
even if outdoor drying is preferred. Explain the trade-off; do not ask about postponement first.
The current prototype already does this. The remaining scenarios and rules are still exploratory.

## 2026-10-03 — Postponement before indoor drying

The founder challenged the need to explore indoor drying if postponement is possible, then agreed
to continue with this order: suitable dryer → recommend it; no dryer and flexible deadline →
postpone; no dryer and urgent deadline → explore indoor drying. The prototype now reflects that
priority, including known-unavailable versus unknown indoor drying to avoid repeated questions.
Forecast quality, exact timing, and other branches remain exploratory.

The revised eleven-case demo ran successfully and Ruff passed. Cases include flexible rain with
indoor drying available (postpone), urgent rain with indoor availability unknown (ask), available
(suggest it), and explicitly ruled out (state insufficient evidence rather than repeat the question).

## 2026-10-03 — Runnable artifact check

Eight demo cases ran; the interactive dryer-toggle, clear-to-rain change, urgency change, and quit
controls were exercised successfully. Ruff and whitespace checks passed. No automated tests were
added for this throwaway prototype. At the time of this check, no founder policy verdict or
live-data evidence was claimed; the later rain/dryer decision above confirms only that one rule.
