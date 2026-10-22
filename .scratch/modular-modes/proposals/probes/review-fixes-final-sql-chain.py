"""Reproduce review-fix SQL evidence in a new disposable local PostgreSQL cluster."""

import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[4]
PG = Path('/opt/homebrew/opt/postgresql@15/bin')
PROOF = ROOT / '.scratch/modular-modes/proposals/review-fixes-final-sql-chain.json'


def run(args, *, env, cwd=ROOT, input=None):
    result = subprocess.run(args, cwd=cwd, env=env, input=input, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f'{args[0]} failed: {result.stdout[-4000:]} {result.stderr[-4000:]}')
    return result.stdout.strip()


cluster = Path(tempfile.mkdtemp(prefix='amigo-review-final-', dir='/private/tmp'))
user = pwd.getpwuid(os.getuid()).pw_name
# No application credentials/provider settings reach the local SQL processes.
env = {key: os.environ[key] for key in ('PATH', 'HOME', 'USER', 'LANG', 'TMPDIR')
       if key in os.environ}
env.update(PGHOST=str(cluster), PGPORT='55495', PGUSER=user, PGDATABASE='postgres')
env['PATH'] = str(PG) + ':' + env.get('PATH', '/usr/bin:/bin')
started = False
proof = {'cluster': str(cluster), 'network': 'unix-socket-only', 'files': [], 'checks': {}}
try:
    run([str(PG / 'initdb'), '-D', str(cluster / 'data'), '-A', 'trust', '-U', user], env=env)
    run([str(PG / 'pg_ctl'), '-D', str(cluster / 'data'), '-l', str(cluster / 'postgres.log'),
         '-o', f"-F -h '' -p 55495 -k {cluster}", '-w', 'start'], env=env)
    started = True
    run([str(PG / 'createdb'), 'amigo_review_final'], env=env)
    env['PGDATABASE'] = 'amigo_review_final'
    paths = re.findall(r'-f ([^\s\\]+)', (ROOT / '.github/workflows/ci.yml').read_text())
    if len(paths) != 45:
        raise RuntimeError(f'Expected reviewed45-file CI chain, found{len(paths)}')
    for path in paths:
        run([str(PG / 'psql'), '-v', 'ON_ERROR_STOP=1', '-q', '-f', path], env=env)
        proof['files'].append({'path': path, 'sha256': hashlib.sha256(
            (ROOT / path).read_bytes()).hexdigest(), 'result': 'PASS'})
        print('PASS', path, flush=True)
    for script in ('check_schema_chain.py', 'check_activation_lock_order.py'):
        probe_env = dict(env)
        if 'activation' in script:
            probe_env['PGOPTIONS'] = '-c role=service_role'
        output = run([str(ROOT / '.venv/bin/python'), 'scripts/' + script], env=probe_env)
        proof['checks'][script] = {'result': 'PASS', 'output': output}
        print(script, output, flush=True)
    version = run([str(PG / 'psql'), '-At', '-v', 'ON_ERROR_STOP=1', '-c',
                   'SELECT public.get_app_schema_version()'], env=env)
    if version != '21':
        raise RuntimeError(f'Unexpected schema{version}')
    proof['schema_version'] = int(version)
    proof['revision'] = run(['git', 'rev-parse', 'HEAD'], env=env)
    proof['result'] = 'PASS'
finally:
    if started:
        run([str(PG / 'pg_ctl'), '-D', str(cluster / 'data'), '-m', 'fast', '-w', 'stop'], env=env)
    proof['cluster_stopped'] = started
    PROOF.write_text(json.dumps(proof, indent=2) + '\n')
print('PASS fresh45-file SQL chain, schema21; cluster stopped; proof', PROOF, flush=True)
