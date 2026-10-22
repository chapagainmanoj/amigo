# Migration 018 independent verification

Reviewer: dev_runtime (independent of migration author cbt_selector), 22 October 2026.

Fixed source point: HEAD `cab0751d2f19ce0220fcf691a94ab3efc7e5e11b`, plus uncommitted reviewed bytes:

- migration SHA-256: `ed445154f5492b5601953a764d70e365917e5c6162b8453cf00ca51dd2e33e4a`
- assertion SHA-256: `d59e843a161582a3288065cdb0123855acdf4aeea4dd98e3c8c68d6cd4f743cb`
- independent extra SQL SHA-256: `13d37fa239714baac03270a9e53148a9448e91226cf99e2c3fa413ae66e7a488`

Reviewed current uncommitted `migrations/018_coaching_programs.sql` against the approved Modes plan, Issue 04, AGENTS boundaries and current Store adapters. Standards/spec axes reviewed independently from author implementation. No migration edits by reviewer.

Security review: RLS enabled on all four tables; participant SELECT restricted to owned programs/entries; anonymous/direct mutations revoked; raw approvals/receipts denied even service-role SELECT; mutation RPCs service-role-only, SECURITY DEFINER, empty search_path. Owner-filtered program reads and composite owner FKs bind lifecycle entries, approvals and receipts. Program mutation/deletion/approval use shared per-owner advisory serialization. Approval tokens are opaque UUIDs, hash-only at rest, expire in ten minutes, bind exact current row/version and are consumed once. Version checks and receipts reject stale/conflicting commands. Revisions preserve initial term; explicit bounded extension alone changes it. Terminal transitions, completion and cascade deletion reviewed.

SQL proof: `/tmp/amigo-review018.py` created a new disposable PostgreSQL 15 cluster at `/private/tmp/amigo-review018-qzk5fiqo` on port 55519. Ran bootstrap Supabase role fixture then migrations 001–018 (19 SQL files), with `psql -X -v ON_ERROR_STOP=1`. No Supabase or existing database reset. Cluster stopped afterward.

Output:

```
PASS fresh bootstrap + migrations001-018: 19 SQL files
PASS 018 lifecycle/ownership/RLS/privileges/deletion rollback assertions
PASS independent expired/stale approval, optimistic version, exactly-once completion, raw receipt denial probes
18|0|0
```

Ran current `tests/sql/assert_018_coaching_programs.sql` plus `/tmp/amigo-review018-extra.sql` in rollback transactions. Extra probes explicitly expired an approval; revised a draft after issuing its token; attempted stale optimistic stop; forced an active program past its term then completed twice; checked service role cannot SELECT raw approval/receipt rows. Each prohibited operation raised its exact expected error, and completion appended exactly one entry. Final query: schema version 18, zero programs, zero entries, confirming rollback cleanup.

Python evidence: `pytest tests/test_coaching_state.py tests/test_coaching_delivery.py tests/test_reflect.py tests/test_recommender.py -q`: 87 passed. `pytest tests/test_coaching_store_contracts.py -q`: 8 passed. Earlier isolated Coach/Reflect/Recommender run: 68 passed. Local HH:MM parsing and UUID token fixes verified by source and focused tests.

Verdict: no unresolved blocking finding in reviewed migration 018. Does not certify Mode admission, production privacy promises, proactive delivery (019), or live provider evaluation. Coach callback/readiness integration findings sent separately to parent.

Exact independent additional probes:

```sql
BEGIN;
DO $$ DECLARE u UUID; p UUID; t TEXT; r JSONB; cfg JSONB; BEGIN
 INSERT INTO public.user_profiles(telegram_chat_id) VALUES(910189991) RETURNING user_id INTO u;
 cfg:='{"goal":"Synthetic","success_measure":"Chosen","check_in_days":[1],"check_in_time":"18:00","timezone":"UTC"}';
 r:=public.coaching_program_command(u,NULL,NULL,'draft','draft','draft',cfg); p:=(r->'program'->>'program_id')::UUID;
 t:=public.issue_coaching_approval(u,p,1);
 UPDATE public.coaching_approvals SET expires_at=clock_timestamp()-interval '1 second' WHERE user_id=u;
 BEGIN
  PERFORM public.confirm_coaching_approval(u,t,'expired','expired');
  RAISE EXCEPTION 'expired approval accepted';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'coaching_approval_required' THEN RAISE; END IF; END;
 t:=public.issue_coaching_approval(u,p,1);
 PERFORM public.coaching_program_command(u,p,1,'revise','revise','revise',cfg||'{"goal":"Changed"}'::jsonb);
 BEGIN
  PERFORM public.confirm_coaching_approval(u,t,'stale','stale');
  RAISE EXCEPTION 'stale summary token accepted';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'coaching_stale_version' THEN RAISE; END IF; END;
 t:=public.issue_coaching_approval(u,p,2);
 PERFORM public.confirm_coaching_approval(u,t,'approve','approve');
 BEGIN
  PERFORM public.coaching_program_command(u,p,2,'stop','stale-stop','stale-stop');
  RAISE EXCEPTION 'stale optimistic version accepted';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'coaching_stale_version' THEN RAISE; END IF; END;
 UPDATE public.coaching_programs SET starts_at=clock_timestamp()-interval '15 days',ends_at=clock_timestamp()-interval '1 day' WHERE program_id=p;
 PERFORM public.complete_due_coaching_programs(); PERFORM public.complete_due_coaching_programs();
 IF (SELECT state FROM public.coaching_programs WHERE program_id=p)<>'completed' OR
    (SELECT count(*) FROM public.coaching_entries WHERE program_id=p AND action='complete')<>1 THEN
  RAISE EXCEPTION 'completion not exactly once'; END IF;
 IF has_table_privilege('service_role','public.coaching_approvals','SELECT') OR
    has_table_privilege('service_role','public.coaching_command_receipts','SELECT') THEN
  RAISE EXCEPTION 'raw approval/receipt service read allowed'; END IF;
END $$;
ROLLBACK;
```
