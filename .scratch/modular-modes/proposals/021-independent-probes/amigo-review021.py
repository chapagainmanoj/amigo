import concurrent.futures, hashlib, json, os, pathlib, subprocess, tempfile, threading
root=pathlib.Path('/Users/mano/Workspace/amigo')
bin=pathlib.Path('/opt/homebrew/opt/postgresql@15/bin')
base=pathlib.Path(tempfile.mkdtemp(prefix='amigo-review021-',dir='/private/tmp'))
env={k:v for k,v in os.environ.items() if k in {'PATH','HOME','USER','LANG'}}
def run(name,*args):
 r=subprocess.run([str(bin/name),*map(str,args)],env=env,text=True,capture_output=True)
 if r.returncode: raise RuntimeError(r.stderr[-4000:])
 return r.stdout
run('initdb','-D',base/'data','-A','trust','--no-locale')
run('pg_ctl','-D',base/'data','-l',base/'postgres.log','-o',f'-k {base} -p 55531 -h ""','start')
try:
 args=['-h',base,'-p','55531','-U','mano','-d','postgres','-X','-v','ON_ERROR_STOP=1']
 files=[root/'tests/sql/bootstrap_supabase_roles.sql']+sorted((root/'migrations').glob('0[012][0-9]_*.sql'))
 for f in files:
  if f.name[:3].isdigit() and int(f.name[:3])>21: continue
  frozen=base/f.name; frozen.write_bytes(f.read_bytes())
  run('psql',*args,'-q','-f',frozen)
 run('psql',*args,'-q','-f',root/'tests/sql/assert_021_confirmed_mode_suggestions.sql')
 print('PASS fresh bootstrap+001–021 chain and021 assertions',flush=True)
 def sql(statement): return run('psql',*args,'-Atc',statement).strip().splitlines()[0]
 u=sql("INSERT INTO public.user_profiles(telegram_chat_id) VALUES(910219990) RETURNING user_id")
 older=sql(f"INSERT INTO public.sessions(user_id,mode_id) VALUES('{u}','daily') RETURNING session_id")
 newer=sql(f"INSERT INTO public.sessions(user_id,mode_id) VALUES('{u}','daily') RETURNING session_id")
 sql(f"SELECT public.grant_mode('{u}','coach','review','fictional SQL test')")
 barrier=threading.Barrier(8)
 def create(_):
  barrier.wait(timeout=10)
  value=sql(f"SELECT coalesce(public.create_mode_suggestion('{u}','{older}','coach'),'null'::jsonb)")
  return json.loads(value)
 with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool: created=list(pool.map(create,range(8)))
 assert sum(row is not None for row in created)==1,created
 offer=next(row for row in created if row)['offer_id']
 assert sql(f"SELECT public.resolve_mode_suggestion('{u}','{offer}',NULL) IS NULL")=='t'
 barrier=threading.Barrier(8)
 def confirm(_):
  barrier.wait(timeout=10)
  return json.loads(sql(f"SELECT coalesce(public.resolve_mode_suggestion('{u}','{offer}',TRUE),'null'::jsonb)"))
 with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool: confirmed=list(pool.map(confirm,range(8)))
 assert sum(row is not None for row in confirmed)==1,confirmed
 assert sql(f"SELECT count(*) FROM public.sessions WHERE user_id='{u}' AND mode_id='coach'")=='0'
 print('PASS eight simultaneousSQLcreate calls→1offer; eightconfirmcalls→1confirmation; oldownedopenSessionvalid; noTargetSession',flush=True)
 program=sql(f"INSERT INTO public.coaching_programs(user_id,goal,success_measure,check_in_days,check_in_time,timezone,state) VALUES('{u}','Fictional goal','Fictional measure',ARRAY[4],'12:00','UTC','draft') RETURNING program_id")
 sql(f"SELECT public.issue_coaching_approval('{u}','{program}',1)")
 assert sql(f"SELECT public.create_mode_suggestion('{u}','{newer}','coach') IS NULL")=='t'
 sql(f"UPDATE public.coaching_approvals SET expires_at=clock_timestamp()-interval '1 second' WHERE user_id='{u}'; SELECT 1")
 newoffer=json.loads(sql(f"SELECT public.create_mode_suggestion('{u}','{newer}','coach')"))['offer_id']
 sql(f"UPDATE public.sessions SET ended_at=clock_timestamp() WHERE session_id='{newer}'; SELECT 1")
 assert sql(f"SELECT public.resolve_mode_suggestion('{u}','{newoffer}',TRUE) IS NULL")=='t'
 print('PASS pendingCoachapproval suppression; expiredapproval allows; closedsource refuses; NULLconfirmation preserves pending',flush=True)
 print('cluster',base,flush=True)
 for relative in ['migrations/020_durable_memory.sql','migrations/021_confirmed_mode_suggestions.sql','tests/sql/assert_021_confirmed_mode_suggestions.sql']:
  print(relative,hashlib.sha256((root/relative).read_bytes()).hexdigest(),flush=True)
finally: run('pg_ctl','-D',base/'data','-m','fast','stop')
