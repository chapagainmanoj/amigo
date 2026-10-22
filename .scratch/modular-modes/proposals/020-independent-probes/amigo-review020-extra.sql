BEGIN;
DO $$ DECLARE u UUID; other UUID; p JSONB; token TEXT; r JSONB; m UUID; settings_v INT; f TEXT; row public.memory_versions; ses UUID; msg UUID; BEGIN
 INSERT INTO public.user_profiles(telegram_chat_id,timezone) VALUES(910209991,'UTC') RETURNING user_id INTO u;
 INSERT INTO public.user_profiles(telegram_chat_id,timezone) VALUES(910209992,'UTC') RETURNING user_id INTO other;
 p:='{"category":"preference","text":"Fictional café ☕ preference","source_mode_id":"daily","source_channel":"dashboard","source_message_id":null,"source_date":"2026-10-22","creation_path":"dashboard_explicit","scopes":["daily"],"valid_until":null}';
 UPDATE public.memory_admission_controls SET ready=TRUE;
 BEGIN
  PERFORM public.memory_command(u,'prepare_memory_confirmation',jsonb_build_object('operation','save','preview_digest',public.memory_payload_digest(p)));
  RAISE EXCEPTION 'missing expected settings version accepted';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'stale version' THEN RAISE; END IF; END;
 FOREACH f IN ARRAY ARRAY['text','source_mode_id','source_channel','creation_path'] LOOP
  row.memory_id:=gen_random_uuid();row.version:=1;row.user_id:=u;row.category:='preference';row.text:='Fictional constraint';row.source_mode_id:='daily';row.source_channel:='dashboard';row.source_date:=current_date;row.creation_path:='dashboard_explicit';row.scopes:=ARRAY['daily'];row.confirmed_at:=clock_timestamp();row.created_at:=clock_timestamp();row.state:='active';row.goal_state:='ongoing';
  IF f='text' THEN row.text:=NULL;ELSIF f='source_mode_id' THEN row.source_mode_id:=NULL;ELSIF f='source_channel' THEN row.source_channel:=NULL;ELSE row.creation_path:=NULL;END IF;
  BEGIN INSERT INTO public.memory_versions SELECT row.*; RAISE EXCEPTION 'nullable nonforgotten field accepted: %',f;
  EXCEPTION WHEN check_violation THEN NULL;END;
 END LOOP;
 INSERT INTO public.sessions(user_id,mode_id) VALUES(other,'daily') RETURNING session_id INTO ses;
 INSERT INTO public.messages(session_id,user_id,role,content) VALUES(ses,other,'user','Fictional other owner source') RETURNING message_id INTO msg;
 p:=p||jsonb_build_object('source_message_id',msg);
 token:=public.memory_command(u,'prepare_memory_confirmation',jsonb_build_object('operation','save','preview_digest',public.memory_payload_digest(p),'expected_settings_version',0))->>'token';
 BEGIN
  PERFORM public.memory_command(u,'confirm_memory_save',jsonb_build_object('token',token,'payload',p,'enable_memory',TRUE,'policy_version','memory-explicit-v1','idempotency_key','foreign-source','payload_hash','foreign-source'));
  RAISE EXCEPTION 'foreign provenance persisted';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'Memory source unavailable' THEN RAISE; END IF; END;
 IF EXISTS(SELECT 1 FROM public.memory_versions WHERE user_id=u) OR EXISTS(SELECT 1 FROM public.memory_settings WHERE user_id=u AND enabled) THEN RAISE EXCEPTION 'failed source partly enabled/saved';END IF;
 p:=p||'{"source_message_id":null}'::jsonb;
 token:=public.memory_command(u,'prepare_memory_confirmation',jsonb_build_object('operation','save','preview_digest',public.memory_payload_digest(p),'expected_settings_version',0))->>'token';
 PERFORM public.memory_command(u,'set_memory_pauses','{"expected_version":0,"use":true,"idempotency_key":"pause-use","payload_hash":"pause-use"}');
 BEGIN
  PERFORM public.memory_command(u,'confirm_memory_save',jsonb_build_object('token',token,'payload',p,'enable_memory',TRUE,'policy_version','memory-explicit-v1','idempotency_key','stale-settings','payload_hash','stale-settings'));
  RAISE EXCEPTION 'stale preview settings accepted';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'stale version' THEN RAISE; END IF; END;
 token:=public.memory_command(u,'prepare_memory_confirmation',jsonb_build_object('operation','save','preview_digest',public.memory_payload_digest(p),'expected_settings_version',1))->>'token';
 r:=public.memory_command(u,'confirm_memory_save',jsonb_build_object('token',token,'payload',p,'enable_memory',TRUE,'policy_version','memory-explicit-v1','idempotency_key','save','payload_hash','save'));
 m:=(r->'memory'->>'memory_id')::UUID;
 PERFORM public.memory_command(u,'set_memory_pauses','{"expected_version":2,"use":false,"idempotency_key":"resume-use","payload_hash":"resume-use"}');
 r:=public.memory_command(u,'read_memory_context','{"mode_id":"daily","turn_id":"first","purpose":"preference","query":"café preference"}');
 IF jsonb_array_length(r)<>1 OR r->0->>'untrusted'<>'true' THEN RAISE EXCEPTION 'bounded untrusted owned retrieval failed';END IF;
 token:=public.memory_command(u,'prepare_memory_confirmation',jsonb_build_object('operation','correct','preview_digest',public.memory_payload_digest(p||'{"text":"Fictional current preference"}'),'expected_settings_version',3,'memory_id',m,'expected_memory_version',1))->>'token';
 r:=public.memory_command(u,'confirm_memory_save',jsonb_build_object('token',token,'payload',p||'{"text":"Fictional current preference"}','idempotency_key','correct','payload_hash','correct'));
 IF (r->'memory'->>'version')::int<>2 OR (SELECT state FROM public.memory_versions WHERE memory_id=m AND version=1)<>'superseded' THEN RAISE EXCEPTION 'correction not versioned';END IF;
 r:=public.memory_command(u,'read_memory_context','{"mode_id":"daily","turn_id":"second","purpose":"preference","query":"preference"}');
 IF jsonb_array_length(r)<>1 OR (r->0->>'version')::int<>2 THEN RAISE EXCEPTION 'superseded version retrieved';END IF;
 PERFORM public.memory_command(u,'forget_memory',jsonb_build_object('memory_id',m,'expected_version',2,'idempotency_key','forget','payload_hash','forget'));
 r:=public.memory_command(u,'confirm_memory_save',jsonb_build_object('token',token,'payload',p||'{"text":"Fictional current preference"}','idempotency_key','correct','payload_hash','correct'));
 IF r->'memory'->>'text' IS NOT NULL OR EXISTS(SELECT 1 FROM public.memory_uses WHERE user_id=u) THEN RAISE EXCEPTION 'receipt replay resurrected content or retained use';END IF;
 IF (SELECT content FROM public.messages WHERE message_id=msg)<>'Fictional other owner source' THEN RAISE EXCEPTION 'Memory purge touched Message';END IF;
END $$;
ROLLBACK;
