# Independent adopted schema16 verification — PASS

Date: 2026-10-03. Reviewer: independent review agent, separate from adopter.

The exact reviewed 015/016 bytes were adopted under the project owner's explicit approval.
This verification used a newly created database, `amigo_adopted016_review_e5232f81`, exclusively
in the verified local temporary PostgreSQL15 cluster `/tmp/amigo-mode016.pFi5g5`, port55476,
owner `mano`. No existing fixture was reset; no production connection or deployment occurred.

The reviewer ran all35 SQL files in the adopted CI workflow's exact order: bootstrap, migrations
001–016, legacy/backfill/tenant/command assertions, assertions015/016 at their proper chain
positions, and the updated application schema-version assertions. All succeeded.

The fresh database then ran:

```bash
PGHOST=/tmp/amigo-mode016.pFi5g5 PGPORT=55476 PGUSER=mano \
PGDATABASE=amigo_adopted016_review_e5232f81 \
  .venv/bin/python scripts/check_schema_chain.py --scratch-db amigo_chain016_review_<unique-id>
PGHOST=/tmp/amigo-mode016.pFi5g5 PGPORT=55476 PGUSER=mano \
PGDATABASE=amigo_adopted016_review_e5232f81 \
  .venv/bin/python scripts/check_activation_lock_order.py
```

Both returned exit0. Database/code agree on revision16. Migration014 refused every tested
constructible chain missing003/004/007/008/009/010/012/013; migration015 refused missing ledger14;
migration016 refused missing ledger15. The Activation forced interleave held, and30 trials
(155 calls) found no deadlock. Only its forced interleave proves that specific ordering shape;
pairing-against-pairing evidence is the separate before/after probe recorded in016-review.md.

Verified migration/assertion bytes:

- 015 SQL: `55cac11a14e03a8be4cba13c107994a2fe17f6fb31e67bffb53028d5d676fdae`
- 015 assertions: `c5a3f8dd850bda1966df80ec17f11a8aca295fc218637b72aee0dc898f7ae80e`
- 016 SQL: `d08b4e28366982d06e2e1c5de1aa8088d90b09bf505e515accf3a0615d70c3df`
- 016 assertions: `b1f81a37d440a81c22b14bcde246a57324cb7a6b89526bf8dbae0b1585c2a72e`

Verified integration hashes:

- CI workflow: `a1cc563df012bcf545ed9f963b2e66059cc059f779ee7c9053f0c8dc82e2b3d8`
- Application schema contract: `132c04800002d193e9aa19c10534291048fb0a8c87df6bc22f49d4e9178655b1`
- Schema-chain checker: `645508a2e6038659d51d2da10eada9bad8de4f9d4ad86360652fab3e5c0d874f`
- Activation probe: `3b3afd6e6669c7132081ede5c7bc1623ec6b5186de49eae88e9f0a2e779bccc5`
- Schema SQL assertions: `d0f16e65e28f261a49b36468d176b658dc5d82fbb854cbb0d99adf572f344dc9`

No unresolved SQL/adoption verification finding remains. Issue03 application routing, grants,
handoff orchestration, and three-Store contract implementation remain separate work. The CBT
offline-selector mock review likewise does not establish clinical or live-provider validation.
