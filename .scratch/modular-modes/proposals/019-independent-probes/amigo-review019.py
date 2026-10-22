import os,pathlib,subprocess,tempfile,hashlib
root=pathlib.Path('/Users/mano/Workspace/amigo')
bin=pathlib.Path('/opt/homebrew/opt/postgresql@15/bin')
base=pathlib.Path(tempfile.mkdtemp(prefix='amigo-review019-',dir='/private/tmp'))
env={k:v for k,v in os.environ.items() if k in {'PATH','HOME','USER','LANG'}}
def run(name,*args):
 r=subprocess.run([str(bin/name),*map(str,args)],env=env,text=True,capture_output=True)
 if r.returncode: raise RuntimeError(r.stderr[-3000:])
 return r.stdout
run('initdb','-D',base/'data','-A','trust','--no-locale')
run('pg_ctl','-D',base/'data','-l',base/'postgres.log','-o',f'-k {base} -p 55519 -h ""','start')
try:
 args=['-h',base,'-p','55519','-U','mano','-d','postgres','-X','-v','ON_ERROR_STOP=1']
 files=[root/'tests/sql/bootstrap_supabase_roles.sql']+sorted((root/'migrations').glob('0[01][0-9]_*.sql'))
 # Include all migrations 001–019.
 for f in files:
  if f.name.startswith('019_'):
   run('psql',*args,'-q','-f','/tmp/amigo-review019-legacy-seed.sql')
   data=f.read_bytes(); frozen=base/f.name; frozen.write_bytes(data)
   print('019 source SHA256:',hashlib.sha256(data).hexdigest())
   run('psql',*args,'-q','-f',frozen)
  else: run('psql',*args,'-q','-f',f)
 run('psql',*args,'-q','-f','/tmp/amigo-review019-legacy-assert.sql')
 print('PASS legacy six commitments incl pending-attempted/accepted retained; four overflow debt; pristine cancelled excluded')
 print(f'PASS fresh bootstrap + migrations001-019: {len(files)} SQL files; {base}')
 run('psql',*args,'-q','-f',root/'tests/sql/assert_019_proactive_delivery_budget.sql')
 run('psql',*args,'-q','-f','/tmp/amigo-review019-extra.sql')
 print('PASS 019 roles, withdrawal-before-dispatch, claim fencing + reclaimed stale worker probes')
 run('psql',*args,'-q','-f','/tmp/amigo-review019-reminders.sql')
 print('PASS Reminder replacement/Later refusal atomic rollback; unsent cancel releases; attempted cancel retains debt')
 run('psql',*args,'-q','-f','/tmp/amigo-review018-extra.sql')
 print('PASS independent expired/stale approval, optimistic version, exactly-once completion, raw receipt denial probes')

 import concurrent.futures,json,threading
 user=run('psql',*args,'-Atc',"INSERT INTO public.user_profiles(telegram_chat_id,timezone,daily_message_budget) VALUES(910199992,'UTC',4) RETURNING user_id").splitlines()[0]
 barrier=threading.Barrier(8)
 def reserve(i):
  barrier.wait(timeout=10)
  return json.loads(run('psql',*args,'-Atc',f"SELECT public.reserve_proactive_delivery('{user}','review:{i}','reminder',date_trunc('minute',clock_timestamp()))"))['status']
 with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool: results=list(pool.map(reserve,range(8)))
 assert results.count('reserved')==4 and results.count('budget_exhausted')==4,results
 print('PASS concurrent eight independent PostgreSQL reservations: exactly four admitted/four refused')


 run('psql',*args,'-q','-f','/tmp/amigo-review019-mixed-seed.sql')
 mixed=json.loads(run('psql',*args,'-Atc',"SELECT json_build_object('user',u.user_id,'program',p.program_id) FROM public.user_profiles u JOIN public.coaching_programs p ON p.user_id=u.user_id WHERE telegram_chat_id=910199995"))
 barrier=threading.Barrier(5)
 def mixed_reserve(i):
  barrier.wait(timeout=10)
  sql=(f"SELECT public.enqueue_coaching_delivery('{mixed['user']}','{mixed['program']}',1,'mixed:coach',(clock_timestamp() AT TIME ZONE 'UTC')::date,'check_in',date_trunc('minute',clock_timestamp()))" if i==4 else f"SELECT public.reserve_proactive_delivery('{mixed['user']}','mixed:reminder:{i}','reminder',date_trunc('minute',clock_timestamp()))")
  return json.loads(run('psql',*args,'-Atc',sql))['status']
 with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool: mixed_results=list(pool.map(mixed_reserve,range(5)))
 assert sum(x in {'queued','reserved'} for x in mixed_results)==4 and mixed_results.count('budget_exhausted')==1,mixed_results
 print('PASS mixed actual Coach enqueue vs four Reminder reservations: four admitted/one refused')

 print(run('psql',*args,'-Atc',"SELECT public.get_app_schema_version(),(SELECT count(*) FROM public.coaching_programs),(SELECT count(*) FROM public.coaching_entries)"))
finally: run('pg_ctl','-D',base/'data','-m','fast','stop')
