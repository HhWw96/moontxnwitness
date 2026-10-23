"""Run instrumentation tests in a new owned PG18 cluster; retain all files."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bin', required=True, help='Existing complete PostgreSQL 18 installation bin directory')
    parser.add_argument('--output', required=True, help='New project-only work directory; never removed')
    args = parser.parse_args()
    work = Path(args.output).resolve(); work.mkdir(parents=True, exist_ok=False)
    binaries = Path(args.bin).resolve(); suffix = '.exe' if os.name == 'nt' else ''
    if not all((binaries/(name+suffix)).is_file() for name in ('initdb', 'pg_ctl', 'postgres')):
        raise ValueError('An existing complete PostgreSQL installation is required; nothing is downloaded')
    if os.name == 'nt' and not str(work).isascii(): raise ValueError('Use a short ASCII work directory on Windows')
    data = work/'data'; private = work/'connection.json'; password = secrets.token_hex(20)
    (work/'password.txt').write_text(password+'\n', encoding='ascii')
    env = dict(os.environ, TEMP=str(work), TMP=str(work), PYTHONIOENCODING='utf-8')
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    receipt = {'schema':1, 'actualDatabaseExecution':False, 'formalPerformanceMeasurement':False,
               'status':'started', 'privateConfigurationPublished':False,
               'wrapperSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'binarySha256':{name:hashlib.sha256((binaries/(name+suffix)).read_bytes()).hexdigest()
                               for name in ('initdb', 'pg_ctl', 'postgres')}}
    started = False; code = 1
    with (work/'control.log').open('xb') as control:
        def run(parts):
            return subprocess.run([str(x) for x in parts], stdin=subprocess.DEVNULL, stdout=control,
                                  stderr=subprocess.STDOUT, env=env, check=True, timeout=120, creationflags=flags)
        try:
            run([binaries/('initdb'+suffix), '-D',data,'-U','mtw','--locale=C','--encoding=UTF8',
                 '--auth-host=scram-sha-256','--auth-local=trust','--pwfile='+str(work/'password.txt')])
            with socket.socket() as candidate:
                candidate.bind(('127.0.0.1',0)); port = candidate.getsockname()[1]
            run([binaries/('pg_ctl'+suffix),'-D',data,'-l',work/'server.log','-o',
                 '-h 127.0.0.1 -p '+str(port)+' -c shared_buffers=32MB -c max_connections=20 -c work_mem=2MB',
                 '-w','start'])
            started = True; receipt['actualDatabaseExecution'] = True
            private.write_text(json.dumps({'host':'127.0.0.1','port':port,'dbname':'postgres',
                                           'user':'mtw','password':password}),encoding='utf8')
            with (work/'integration.log').open('xb') as integration:
                result = subprocess.run([sys.executable,'-B',str(ROOT/'scripts/instrumentation-postgres-test.py'),
                                         '--connection-file',str(private),'--output',str(work/'suite'),'--commit-loss'],
                                        cwd=ROOT,env=env,stdout=integration,stderr=subprocess.STDOUT,
                                        timeout=180,creationflags=flags)
            code = result.returncode; receipt.update(status='passed' if code==0 else 'failed',exitCode=code)
        except BaseException as error:
            receipt.update(status='failed',errorClass=type(error).__name__)
        finally:
            if started:
                pidfile = data/'postmaster.pid'
                if pidfile.exists():
                    actual = Path(pidfile.read_text(encoding='utf8').splitlines()[1]).resolve()
                    if actual != data: raise ValueError('Refuse to stop an unrelated cluster')
                    try:
                        run([binaries/('pg_ctl'+suffix),'-D',data,'-m','fast','-w','stop'])
                        receipt['ownClusterStopped'] = True
                    except BaseException as error:
                        receipt.update(status='failed',stopErrorClass=type(error).__name__); code=1
            (work/'wrapper-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'status':receipt['status'],'exitCode':code,'actualDatabaseExecution':receipt['actualDatabaseExecution']}))
    return code


if __name__ == '__main__': raise SystemExit(main())
