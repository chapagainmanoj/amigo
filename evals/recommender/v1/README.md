# Recommender v1 — fictional laundry only

Sixteen cases, three repetitions each. All weather and participant scenarios are
fictional. The local Tool uses labelled synthetic fixtures; no live source,
location collection, durable preferences, Task/Reminder mutation, transactions or
cross-Mode transcript access is included.

The full scripted subset exercises the owned runtime/orchestrator in
`tests/test_recommender.py`. Scripted results are regression checks, never provider
evidence, real forecast validation, participant demand or release evidence.
No provider run has been made for this suite.

The Tool's trusted fixture output contains source, fixture ID, synthetic marker,
fictional location/window, retrieval time and freshness deadline. Timestamps are
relative to the injected Clock for repeatable demonstrations; they describe
fictional fixture evidence, never real weather. Unavailable, stale and wrong-window
fixtures abstain. A fixture must be explicitly selected before outdoor comparison.
Indoor-only and dryer-only comparisons do not use weather.

Decisions 06–09 require: available suitable dryer over a soft outdoor preference
when simulated rain conflicts; postponement before indoor alternatives when the
deadline is flexible; urgent alternatives must be actually available and carry no
claim of guaranteed completion. Hard restrictions override soft preferences.

Catalogue integration is owner-controlled and must preserve grant entitlement,
only the Laundry and Handoffs Toolsets, no Daily context providers, and the
`daily` handoff target. Keep broader commercial Recommender and live-weather
claims gated by their separate demand/source decisions.
