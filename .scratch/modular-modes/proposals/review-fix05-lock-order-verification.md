# Review fix05 — independent 019 lock-order proof

22 October2026. Author/dev_runtime isolated budget-review-fixes checkout; independent reviewer
cbt_selector. Author commit4f3bf65, integrated separately onto develop.

`update_reminder_budget` now takes user_profiles FOR KEY SHARE before the shared per-user budget
advisory lock, matching reserve_proactive_delivery and the concurrent profile-delete lock order.
No budget semantics changed in this slice. Static lock-order tests now parse each inline SQL body,
recognize all row-lock modes and cover017–019 plus the five proactive entry points.

Independent fresh PostgreSQL complete001–021 CI chain: all45SQLfiles PASS.157lock-order tests
PASS0.27s; Ruff clean. Exact019SHA256:
4638f74e59aa1515f0c60682f9ea4fba66061234151a9eed18418d3a759f531c.
Driver/tmp/amigo-item5-review.py; disposable cluster/private/tmp/amigo-item5-review-mlxereiz stopped.
No Supabase/production data/credentials or deployed schema changed. Static lock tests establish
statement ordering; full-chain assertions do not establish universal deadlock-freedom.
