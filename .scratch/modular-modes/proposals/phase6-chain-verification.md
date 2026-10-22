# Phase 6 combined local schema proof

22 October 2026; no deployed database involved.

Fresh database `amigo019_full_22bc146ce3` in the disposable local PostgreSQL15 cluster. Driver
`/tmp/amigo-019-chain.py` reads the actual CI `-f` sequence, not an abbreviated migration list.
All45 files passed: bootstrap, legacy fixtures, migrations001–021, every matching assertion,
RLS/command/outbox/Activation/routing/budget/Memory/suggestion assertions and app schema ledger.

`check_schema_chain.py`: code/database agree at21; missing003/004/007/008/009/010/012/013 refused
by014; missing predecessor ledger refused by015,016,017,018,019,020,021.
`check_activation_lock_order.py` under service_role: forced interleave held;30trials155calls found
no deadlock. Only forced interleave proves lock order; no general deadlock-freedom claim.

Exact reviewed migration hashes:
273f33cc8a383c1b7362798721cedf2d07a67d07b44b59fd77e9bd346922481b  migrations/020_durable_memory.sql
7c515d31f4ef93417fc1c382c50d350affcc168d40ed4540394cf7fa02b652ec  migrations/021_confirmed_mode_suggestions.sql
bfdba78d3566695e33a9c19bcbae9f3dab92265ab90684a70f8842de0f79abd7  tests/sql/assert_020_durable_memory.sql
210dce4eadd3fc68693cc24bc05ae6e18ccbba480fd6dff4f6ea42b20c0a381d  tests/sql/assert_021_confirmed_mode_suggestions.sql
