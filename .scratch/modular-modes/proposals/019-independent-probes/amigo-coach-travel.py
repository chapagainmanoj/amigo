import hashlib, os, pathlib, re, subprocess, tempfile
root=pathlib.Path('/Users/mano/Workspace/amigo')
bin=pathlib.Path('/opt/homebrew/opt/postgresql@15/bin')
base=pathlib.Path(tempfile.mkdtemp(prefix='amigo-coach-travel-',dir='/private/tmp'))
env={k:v for k,v in os.environ.items() if k in {'PATH','HOME','USER','LANG'}}
def run(name,*args,check=True):
 r=subprocess.run([str(bin/name),*map(str,args)],env=env,text=True,capture_output=True)
 if check and r.returncode: raise RuntimeError(r.stderr[-3500:])
 return r
run('initdb','-D',base/'data','-A','trust','--no-locale')
run('pg_ctl','-D',base/'data','-l',base/'postgres.log','-o',f'-k {base} -p 55529 -h ""','start')
try:
 args=['-h',base,'-p','55529','-U','mano','-X','-v','ON_ERROR_STOP=1']
 files=re.findall(r'-f ((?:migrations|tests/sql)/\S+\.sql)',(root/'.github/workflows/ci.yml').read_text())
 for db,old in [('travel_before',True),('travel_after',False)]:
  run('createdb','-h',base,'-p','55529','-U','mano',db)
  for relative in files:
   path=root/relative
   if old and relative.startswith('migrations/019_'):
    frozen=base/'old019.sql';frozen.write_bytes(subprocess.check_output(['git','show','402bed5:'+relative],cwd=root));path=frozen
   result=run('psql',*args,'-d',db,'-q','-f',path,check=False)
   if result.returncode:
    if old and relative=='tests/sql/assert_019_proactive_delivery_budget.sql' and 'profile travel quiet hours ignored' in result.stderr:
     print('RED original019: profile travel quiet hours ignored',flush=True);break
    raise RuntimeError(relative+' '+result.stderr[-3000:])
  else:
   assert not old
   print(f'GREEN fresh complete CI chain {len(files)} SQL files; profile quiet and inverse awake assertions PASS',flush=True)
 print('cluster',base,flush=True)
 for rel in ['migrations/019_proactive_delivery_budget.sql','tests/sql/assert_019_proactive_delivery_budget.sql']:
  print(rel,hashlib.sha256((root/rel).read_bytes()).hexdigest(),flush=True)
finally: run('pg_ctl','-D',base/'data','-m','fast','stop')
