import os,pathlib,subprocess,tempfile,hashlib,json,concurrent.futures,threading,sys
root=pathlib.Path('/Users/mano/Workspace/amigo');bin=pathlib.Path('/opt/homebrew/opt/postgresql@15/bin');base=pathlib.Path(tempfile.mkdtemp(prefix='amigo-review020-',dir='/private/tmp'))
env={k:v for k,v in os.environ.items() if k in {'PATH','HOME','USER','LANG'}}
def run(name,*args):
 r=subprocess.run([str(bin/name),*map(str,args)],env=env,text=True,capture_output=True)
 if r.returncode: raise RuntimeError(r.stderr[-4000:])
 return r.stdout
run('initdb','-D',base/'data','-A','trust','--no-locale');run('pg_ctl','-D',base/'data','-l',base/'postgres.log','-o',f'-k {base} -p 55520 -h ""','start')
try:
 args=['-h',base,'-p','55520','-U','mano','-d','postgres','-X','-v','ON_ERROR_STOP=1']
 files=[root/'tests/sql/bootstrap_supabase_roles.sql']+[f for f in sorted((root/'migrations').glob('[0-9][0-9][0-9]_*.sql')) if int(f.name[:3])<=20]
 for f in files:
  data=f.read_bytes();frozen=base/f.name;frozen.write_bytes(data);run('psql',*args,'-q','-f',frozen)
  if f.name.startswith('020_'):print('020 source SHA256:',hashlib.sha256(data).hexdigest())
 print('PASS fresh bootstrap001–020:',len(files),'files;',base)
 run('psql',*args,'-q','-f',root/'tests/sql/assert_020_durable_memory.sql');print('PASS author020 owner/default-OFF/token/scope/version/forget/role assertions')
 run('psql',*args,'-q','-f','/tmp/amigo-review020-extra.sql');print('PASS independent null-CHECK/version, foreign source rollback, settings-token freshness, correction, purge and stale-receipt probes')
 sys.path.insert(0,str(root));from src.memory.durable import memory_payload_digest
 p={'category':'preference','text':'Fictional café ☕ preference','source_mode_id':'daily','source_channel':'dashboard','source_message_id':None,'source_date':'2026-10-22','creation_path':'dashboard_explicit','scopes':['daily'],'valid_until':None}
 sql_digest=run('psql',*args,'-Atc',"SELECT public.memory_payload_digest('"+json.dumps(p,ensure_ascii=False).replace("'","''")+"'::jsonb)").strip();assert sql_digest==memory_payload_digest(p);print('PASS Python/PostgreSQL exact Unicode ordered-array digest parity')
 run('psql',*args,'-qc','UPDATE public.memory_admission_controls SET ready=TRUE')
 candidates=[]
 for i in range(6):
  user=run('psql',*args,'-Atc',f"INSERT INTO public.user_profiles(telegram_chat_id,timezone) VALUES({910209900+i},'UTC') RETURNING user_id").splitlines()[0]
  token=json.loads(run('psql',*args,'-Atc',f"SELECT public.memory_command('{user}','prepare_memory_confirmation','{json.dumps({'operation':'save','preview_digest':sql_digest,'expected_settings_version':0})}'::jsonb)"))['token'];candidates.append((user,token))
 barrier=threading.Barrier(6)
 def confirm(item):
  user,token=item;barrier.wait(timeout=10);body=json.dumps({'token':token,'payload':p,'enable_memory':True,'policy_version':'memory-explicit-v1','idempotency_key':'parallel-first','payload_hash':'parallel-first'},ensure_ascii=False).replace("'","''")
  try:run('psql',*args,'-Atc',f"SELECT public.memory_command('{user}','confirm_memory_save','{body}'::jsonb)");return 'saved'
  except RuntimeError as e:
   assert 'Memory trial admission cap reached' in str(e);return 'cap'
 with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(confirm,candidates))
 assert results.count('saved')==5 and results.count('cap')==1,results;print('PASS six independent first-opt-in SQL transactions: five admitted, one refused; atomic global cap')
 print(run('psql',*args,'-Atc','SELECT public.get_app_schema_version(),(SELECT count(*) FROM public.memory_settings WHERE enabled),(SELECT count(*) FROM public.memory_versions)'))
finally:run('pg_ctl','-D',base/'data','-m','fast','stop')
