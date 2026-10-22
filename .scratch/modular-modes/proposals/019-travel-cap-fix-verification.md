# 019 travel quiet hours and per-participant Coach cap

22 October 2026. Repository-only fix, after foundation commit 402bed5. No Supabase or provider calls.
This author verification is separate from the requested independent final review.

Changed: planner and local/SQL dispatch use current profile timezone for wake/sleep; Program timezone
still determines slot, selected weekday and occurrence date. Local/SQL admission allows at most one
noncancelled Coach reservation per participant/profile day across Programs. Stored local day OR
scheduled instant converted into the current profile zone conservatively counts capacity. Accepted
and uncertain reservations retain the cap with NULL Program after deletion. Dispatch rechecks other
Coach capacity and a reduced current shared budget; unused cancelled capacity can be retried.

Before fix: four focused Python regressions failed. Program Thursday 08:00 UTC / profile Los Angeles
01:00 wrongly allowed; Thursday 01:00 UTC / profile Wednesday 18:00 wrongly denied. After fix:
`python -m pytest tests/test_coaching_delivery.py tests/test_reminder_budget.py -q` → 97 passed.
Full `python -m pytest tests/ -q` → 1151 passed in 10.65s. `ruff check src tests scripts` passed;
`git diff --check` passed. Daily schema and golden remain covered by full suite.

Fresh PostgreSQL proof command: `.venv/bin/python /tmp/amigo-coach-travel.py`; retained source in
`019-independent-probes/amigo-coach-travel.py`. Disposable Unix-socket-only cluster
`/private/tmp/amigo-coach-travel-sh675tpn`, port 55529, owner mano. Stopped after verification.
Script creates two fresh databases and follows the exact CI SQL order including legacy seeds.
Original 402bed5 migration with new assertions: RED `profile travel quiet hours ignored`.
Current migration: GREEN all 41 SQL files, including quiet and inverse awake assertions, cap across
Programs, retained accepted/uncertain NULL-Program capacity, cancelled retry, dispatch collision and
reduced budget. Fixture TIME casts were corrected before the successful run.

Final SHA256:

- migrations/019_proactive_delivery_budget.sql:
  `4c6c0f0ca24e6fd1a65f987d0686c7819e3222bce91c1bde48d189e34b94c781`
- tests/sql/assert_019_proactive_delivery_budget.sql:
  `b8d181f65df9cfcc2d62bba28d999d3b16cda524214b1b096a6971a0f99b5993`

No commit. Parent owns final independent review and review-queue entry.
