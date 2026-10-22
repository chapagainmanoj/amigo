import concurrent.futures, hashlib, os, pathlib, re, subprocess, tempfile, time
root=pathlib.Path(__file__).resolve().parents[4]
bin=pathlib.Path('/opt/homebrew/opt/postgresql@15/bin')
base=pathlib.Path(tempfile.mkdtemp(prefix='amigo-item11-',dir='/private/tmp'))
env={k:v for k,v in os.environ.items() if k in {'PATH','HOME','USER','LANG'}}
def run(name,*args):
 r=subprocess.run([str(bin/name),*map(str,args)],env=env,text=True,capture_output=True)
 if r.returncode: raise RuntimeError(r.stderr[-4000:])
 return r.stdout
run('initdb','-D',base/'data','-A','trust','--no-locale')
run('pg_ctl','-D',base/'data','-l',base/'postgres.log','-o',f'-k {base} -p 55536 -h ""','start')
args=['-h',base,'-p','55536','-U','mano','-d','postgres','-X','-v','ON_ERROR_STOP=1','-At']
def sql(text): return run('psql',*args,'-c',text).strip()
def raw(text): return subprocess.run([str(bin/'psql'),*map(str,args),'-c',text],env=env,text=True,capture_output=True)
def wait_lock(key):
 for _ in range(100):
  if sql(f"SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND granted AND objid=(({key}) & 4294967295)::oid")!='0': return
  time.sleep(.02)
 raise RuntimeError('lock not observed')
try:
 files=re.findall(r'-f ((?:migrations|tests/sql)/\S+\.sql)',(root/'.github/workflows/ci.yml').read_text())
 for relative in files:
  if relative=='migrations/017_mode_conversations.sql':
   sql("INSERT INTO public.user_profiles(telegram_chat_id) VALUES(91911001); INSERT INTO public.sessions(user_id,active_mode_id,ended_at) SELECT user_id,'coach',clock_timestamp() FROM public.user_profiles WHERE telegram_chat_id=91911001; INSERT INTO public.sessions(user_id,active_mode_id) SELECT user_id,NULL FROM public.user_profiles WHERE telegram_chat_id=91911001;")
  source=root/relative; frozen=base/source.name; frozen.write_bytes(source.read_bytes()); run('psql',*args,'-q','-f',frozen)
 assert sql("SELECT string_agg(mode_id,',' ORDER BY (ended_at IS NULL)) FROM public.sessions WHERE user_id=(SELECT user_id FROM public.user_profiles WHERE telegram_chat_id=91911001)")=='coach,daily'
 print('PASS backfill closed coach + open NULL-active Daily; complete45-file SQLchain',flush=True)
 users=sql("INSERT INTO public.user_profiles(telegram_chat_id) VALUES(91911002),(91911003) RETURNING user_id").splitlines()[:2]
 a,b=users
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
  locked=pool.submit(sql,f"BEGIN; SELECT pg_advisory_xact_lock(hashtextextended('amigo-conversations:{a}',0)); SELECT pg_sleep(2); COMMIT")
  wait_lock(f"hashtextextended('amigo-conversations:{a}',0)")
  start=time.monotonic();sql(f"SET statement_timeout='800ms'; SELECT public.save_mode_conversation('{b}','daily','test','{{\"id\":2}}');")
  assert time.monotonic()-start<1, 'unrelated owner blocked'
  same=raw(f"SET statement_timeout='150ms'; SELECT public.save_mode_conversation('{a}','daily','test','{{\"id\":1}}');")
  assert same.returncode and 'statement timeout' in same.stderr
  locked.result()
 print('PASS held ownerA lock blocks A only; ownerB saves concurrently',flush=True)
 # Force both owners to observe an absent endpoint, then conflict at unique insert.
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
  owner=pool.submit(sql,f"BEGIN; SELECT public.save_mode_conversation('{a}','coach','test','{{\"id\":99}}'); SELECT pg_advisory_xact_lock(9181199); SELECT pg_sleep(2); COMMIT")
  wait_lock('9181199')
  other=raw(f"SELECT public.save_mode_conversation('{b}','coach','test','{{\"id\":99}}');")
  owner.result()
  assert other.returncode and 'conversation_endpoint_conflict' in other.stderr,other.stderr
 assert sql(f"SELECT user_id FROM public.mode_conversation_endpoints WHERE channel='test' AND endpoint='{{\"id\":99}}'")==a
 assert sql(f"SELECT count(*) FROM public.mode_conversations WHERE user_id='{b}' AND mode_id='coach'")=='0'
 print('PASS absent endpoint cross-owner race rejects loser without canonical corruption',flush=True)
 print('017SHA256',hashlib.sha256((root/'migrations/017_mode_conversations.sql').read_bytes()).hexdigest(),flush=True)
 print('cluster',base,flush=True)
finally:run('pg_ctl','-D',base/'data','-m','fast','stop')
