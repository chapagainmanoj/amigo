DO $$
DECLARE
  first_claim JSONB;
  duplicate_claim JSONB;
  finished JSONB;
BEGIN
  first_claim := public.claim_telegram_update(1001, 7001, 'message');
  IF first_claim->>'claimed' <> 'true' OR first_claim->>'status' <> 'processing' THEN
    RAISE EXCEPTION 'first claim did not reserve the update';
  END IF;

  duplicate_claim := public.claim_telegram_update(1001, 7001, 'message');
  IF duplicate_claim->>'claimed' <> 'false'
    OR duplicate_claim->>'status' <> 'processing'
  THEN
    RAISE EXCEPTION 'duplicate claim did not return the original state';
  END IF;

  finished := public.finish_telegram_update(1001, 'completed', NULL);
  IF finished->>'status' <> 'completed' OR finished->>'finished_at' IS NULL THEN
    RAISE EXCEPTION 'completion was not retained';
  END IF;

  finished := public.finish_telegram_update(1001, 'completed', NULL);
  IF finished->>'status' <> 'completed' THEN
    RAISE EXCEPTION 'completion replay was not idempotent';
  END IF;

  first_claim := public.claim_telegram_update(1002, -7002, 'callback_query');
  finished := public.finish_telegram_update(1002, 'failed', 'RuntimeError');
  IF finished->>'status' <> 'failed'
    OR finished->>'failure_code' <> 'RuntimeError'
  THEN
    RAISE EXCEPTION 'failure state was not retained';
  END IF;

  BEGIN
    PERFORM public.claim_telegram_update(1001, 9999, 'message');
    RAISE EXCEPTION 'identity conflict unexpectedly succeeded';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM <> 'telegram_update_identity_conflict' THEN
      RAISE;
    END IF;
  END;

  BEGIN
    PERFORM public.finish_telegram_update(1001, 'failed', 'RetryError');
    RAISE EXCEPTION 'conflicting finish unexpectedly succeeded';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM <> 'telegram_update_already_finished' THEN
      RAISE;
    END IF;
  END;
END;
$$;

SET ROLE authenticated;

DO $$
BEGIN
  IF has_table_privilege(current_user, 'public.telegram_update_claims', 'SELECT') THEN
    RAISE EXCEPTION 'authenticated role can read Telegram update claims';
  END IF;
  BEGIN
    PERFORM public.claim_telegram_update(2001, 8001, 'message');
    RAISE EXCEPTION 'authenticated role unexpectedly claimed an update';
  EXCEPTION WHEN insufficient_privilege THEN
    NULL;
  END;
END;
$$;

RESET ROLE;
