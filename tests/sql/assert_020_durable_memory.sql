\set ON_ERROR_STOP on
BEGIN;
DO $$ DECLARE u UUID; other UUID; p JSONB; token TEXT; r JSONB; m UUID; v INT;
BEGIN
 IF public.get_app_schema_version()<>20 THEN RAISE EXCEPTION '020 missing'; END IF;
 INSERT INTO public.user_profiles(telegram_chat_id,timezone) VALUES(91020001,'UTC') RETURNING user_id INTO u;
 INSERT INTO public.user_profiles(telegram_chat_id) VALUES(91020002) RETURNING user_id INTO other;
 p:=jsonb_build_object('category','preference','text','Fictional morning coffee',
 'source_mode_id','daily','source_channel','dashboard','source_message_id',NULL,
 'source_date',to_char(current_date,'YYYY-MM-DD'),'creation_path','dashboard_explicit',
 'scopes',jsonb_build_array('daily'),'valid_until',NULL);
 IF public.memory_command(u,'get_memory_settings')->>'enabled'<>'false' THEN RAISE EXCEPTION 'default on'; END IF;
 BEGIN
 PERFORM public.memory_command(u,'prepare_memory_confirmation',jsonb_build_object('operation','save',
 'preview_digest',public.memory_payload_digest(p),'expected_settings_version',0));
 RAISE EXCEPTION 'default admission admitted'; EXCEPTION WHEN raise_exception THEN
 IF SQLERRM NOT LIKE 'invalid transition:%' THEN RAISE; END IF; END;
 BEGIN
 PERFORM public.memory_command(u,'prepare_memory_confirmation',jsonb_build_object('operation','forget_all',
 'preview_digest',public.memory_inventory_digest(u),'expected_settings_version',NULL));
 RAISE EXCEPTION 'null expected version accepted'; EXCEPTION WHEN raise_exception THEN
 IF SQLERRM<>'stale version' THEN RAISE; END IF; END;
 UPDATE public.memory_admission_controls SET ready=TRUE;
 token:=public.memory_command(u,'prepare_memory_confirmation',jsonb_build_object('operation','save',
 'preview_digest',public.memory_payload_digest(p),'expected_settings_version',0))->>'token';
 IF EXISTS(SELECT 1 FROM public.memory_confirmation_claims WHERE token_hash=token) THEN RAISE EXCEPTION 'plaintext token'; END IF;
 BEGIN
 PERFORM public.memory_command(other,'confirm_memory_save',jsonb_build_object('token',token,'payload',p,
 'idempotency_key','save','payload_hash','save','enable_memory',TRUE,'policy_version','memory-explicit-v1'));
 RAISE EXCEPTION 'foreign token used'; EXCEPTION WHEN raise_exception THEN
 IF SQLERRM NOT LIKE 'invalid transition:%' THEN RAISE; END IF; END;
 BEGIN
 PERFORM public.memory_command(u,'confirm_memory_save',jsonb_build_object('token',token,'payload',p||'{"text":"changed"}',
 'idempotency_key','save','payload_hash','save','enable_memory',TRUE,'policy_version','memory-explicit-v1'));
 RAISE EXCEPTION 'changed preview used'; EXCEPTION WHEN raise_exception THEN
 IF SQLERRM NOT LIKE 'invalid transition:%' THEN RAISE; END IF; END;
 IF EXISTS(SELECT 1 FROM public.memory_settings WHERE user_id=u AND enabled) THEN RAISE EXCEPTION 'optin not atomic'; END IF;
 r:=public.memory_command(u,'confirm_memory_save',jsonb_build_object('token',token,'payload',p,
 'idempotency_key','save','payload_hash','save','enable_memory',TRUE,'policy_version','memory-explicit-v1'));
 m:=(r->'memory'->>'memory_id')::UUID;
 IF public.memory_command(u,'read_memory_context',jsonb_build_object('mode_id','daily','turn_id','t',
 'purpose','personalize','query','coffee'))->0->>'text'<>'Fictional morning coffee' THEN RAISE EXCEPTION 'retrieval'; END IF;
 IF jsonb_array_length(public.memory_command(other,'read_memory_context',jsonb_build_object('mode_id','daily','turn_id','t','purpose','personalize','query','coffee')))<>0
 OR jsonb_array_length(public.memory_command(u,'read_memory_context',jsonb_build_object('mode_id','coach','turn_id','t','purpose','personalize','query','coffee')))<>0
 OR jsonb_array_length(public.memory_command(u,'read_memory_context',jsonb_build_object('mode_id','reflect','turn_id','t','purpose','personalize','query','coffee')))<>0 THEN RAISE EXCEPTION 'scope leak'; END IF;
 r:=public.memory_command(u,'transition_memory',jsonb_build_object('memory_id',m,'expected_version',1,
 'action','inactive','idempotency_key','inactive','payload_hash','inactive'));
 IF (r->'memory'->>'version')::INT<>2 THEN RAISE EXCEPTION 'mutation did not version'; END IF;
 BEGIN
 PERFORM public.memory_command(u,'transition_memory',jsonb_build_object('memory_id',m,'expected_version',1,
 'action','use_again','idempotency_key','stale','payload_hash','stale'));
 RAISE EXCEPTION 'stale mutated'; EXCEPTION WHEN raise_exception THEN
 IF SQLERRM<>'stale version' THEN RAISE; END IF; END;
 r:=public.memory_command(u,'forget_memory',jsonb_build_object('memory_id',m,'expected_version',2,
 'idempotency_key','forget','payload_hash','forget'));
 IF EXISTS(SELECT 1 FROM public.memory_versions WHERE memory_id=m AND
 (text IS NOT NULL OR source_mode_id IS NOT NULL OR cardinality(scopes)<>0 OR state<>'forgotten'))
 OR EXISTS(SELECT 1 FROM public.memory_uses WHERE memory_id=m) THEN RAISE EXCEPTION 'purge incomplete'; END IF;
 r:=public.memory_command(u,'confirm_memory_save',jsonb_build_object('token',token,'payload',p,
 'idempotency_key','save','payload_hash','save','enable_memory',TRUE,'policy_version','memory-explicit-v1'));
 IF r->'memory'->>'text' IS NOT NULL THEN RAISE EXCEPTION 'idempotency resurrected plaintext'; END IF;
 IF EXISTS(SELECT 1 FROM public.memory_command_receipts WHERE result_metadata::TEXT LIKE '%Fictional%') THEN RAISE EXCEPTION 'receipt content'; END IF;
 IF has_table_privilege('service_role','public.memory_admission_controls','UPDATE')
 OR has_table_privilege('service_role','public.memory_versions','SELECT')
 OR has_function_privilege('authenticated','public.memory_command(uuid,text,jsonb)','EXECUTE')
 OR NOT has_function_privilege('service_role','public.memory_command(uuid,text,jsonb)','EXECUTE') THEN RAISE EXCEPTION 'privilege'; END IF;
END $$;
ROLLBACK;
