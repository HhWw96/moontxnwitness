"""Reproduce the actual base-user producer using a new retained PG18 cluster."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[3]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bin',required=True,help='Existing complete PostgreSQL18 bin directory')
    parser.add_argument('--upstream-root',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args();work=Path(args.output).resolve();work.mkdir(parents=True,exist_ok=False)
    binaries=Path(args.bin).resolve();suffix='.exe' if os.name=='nt' else ''
    if os.name=='nt' and not str(work).isascii():raise ValueError('Use an ASCII owned work path on Windows')
    modules=ROOT/'integrations/python/moontxnwitness_capture'
    files=[Path(__file__).resolve(),Path(__file__).with_name('profile_demo.py'),
        *sorted((modules/'profiles').glob('*.py')),
        *(modules/name for name in ['capture.py','capture_v3.py','instrumentation.py','orm.py','_orm_policy.py',
            '_orm_async.py','_orm_raw_async.py','source_sink.py','_orm_source_sink.py','_durable_policy.py','journal_v3.py'])]
    binding=lambda:{file.relative_to(ROOT).as_posix():hashlib.sha256(file.read_bytes()).hexdigest() for file in files}
    before=binding();receipt={'schema':1,'kind':'owned-upstream-base-user-producer',
        'status':'not-executed','actualDatabaseExecution':False,'formalPerformanceMeasurement':False,
        'sourceBefore':before,'fullMappingCoverageAccepted':False,'privateCredentialsPublished':False}
    try:
        receipt['versions']={name:importlib.metadata.version(name) for name in ['psycopg','psycopg-binary','sqlalchemy','fastapi-users','greenlet']}
    except importlib.metadata.PackageNotFoundError:
        receipt['reason']='Optional pinned dependencies missing'
        (work/'wrapper-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8');return 3
    if receipt['versions']['psycopg']!='3.3.6' or receipt['versions']['sqlalchemy']!='2.0.55':
        raise ValueError('Pinned psycopg and SQLAlchemy required')
    password=secrets.token_hex(20);(work/'password.txt').write_text(password+'\n',encoding='ascii')
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    env=dict(os.environ,TEMP=str(work),TMP=str(work),PYTHONIOENCODING='utf-8')
    started=False;code=1;data=work/'data'
    with (work/'control.log').open('xb') as log:
        def run(parts):
            return subprocess.run([str(item) for item in parts],env=env,stdin=subprocess.DEVNULL,
                stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120,creationflags=flags)
        try:
            receipt['binarySha256']={name:hashlib.sha256((binaries/(name+suffix)).read_bytes()).hexdigest()
                                    for name in ('initdb','pg_ctl','postgres')}
            run([binaries/('initdb'+suffix),'-D',data,'-U','mtw','--locale=C','--encoding=UTF8',
                '--auth-host=scram-sha-256','--auth-local=trust','--pwfile='+str(work/'password.txt')])
            with socket.socket() as candidate:candidate.bind(('127.0.0.1',0));port=candidate.getsockname()[1]
            run([binaries/('pg_ctl'+suffix),'-D',data,'-l',work/'server.log','-o',
                '-h 127.0.0.1 -p '+str(port)+' -c shared_buffers=32MB -c max_connections=20 -c work_mem=2MB','-w','start'])
            started=True;receipt['actualDatabaseExecution']=True
            private=work/'connection.json'
            private.write_text(json.dumps({'host':'127.0.0.1','port':port,'dbname':'postgres','user':'mtw','password':password}),encoding='utf8')
            with (work/'business.log').open('xb') as business:
                result=subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('profile_demo.py')),
                    '--upstream-root',str(Path(args.upstream_root).resolve()),'--connection-file',str(private),
                    '--output',str(work/'suite')],env=env,cwd=ROOT,stdout=business,stderr=subprocess.STDOUT,
                    timeout=180,creationflags=flags)
            code=result.returncode;receipt.update(status='producer-passed' if code==0 else 'failed',businessExitCode=code)
        except BaseException as error:receipt.update(status='failed',errorClass=type(error).__name__)
        finally:
            if started and (data/'postmaster.pid').exists():
                actual=Path((data/'postmaster.pid').read_text(encoding='utf8').splitlines()[1]).resolve()
                if actual!=data:raise ValueError('Refuse to stop an unrelated PostgreSQL instance')
                try:
                    run([binaries/('pg_ctl'+suffix),'-D',data,'-m','fast','-w','stop']);receipt['ownClusterStopped']=True
                except BaseException as error:receipt.update(status='failed',stopErrorClass=type(error).__name__);code=1
            after=binding();receipt.update(sourceAfter=after,sourceUnchanged=before==after)
            if before!=after:receipt['status']='failed';code=1
            (work/'wrapper-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'status':receipt['status'],'businessExitCode':code,'ownClusterStopped':receipt.get('ownClusterStopped')}))
    return code


if __name__=='__main__':raise SystemExit(main())
