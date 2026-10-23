"""Run a preregistered cost prefix on a new retained owned PG18 cluster.

Nothing starts without an explicit exclusive-host assertion. Three full-timing
cells are the default partial first group; no complete protocol is inferred.
"""
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

ROOT=Path(__file__).resolve().parents[2]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bin',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--profile',choices=['column','sidecar'],default='column')
    parser.add_argument('--max-cells',type=int,default=3)
    parser.add_argument('--exclusive-host',action='store_true')
    args=parser.parse_args()
    if not args.exclusive_host:parser.error('Stop other host workloads and explicitly pass --exclusive-host')
    if not 1<=args.max_cells<=36:parser.error('--max-cells must be in 1..36')
    work=Path(args.output).resolve();work.mkdir(parents=True,exist_ok=False)
    if os.name=='nt' and not str(work).isascii():raise ValueError('Use an ASCII owned path on Windows')
    binaries=Path(args.bin).resolve();suffix='.exe' if os.name=='nt' else ''
    files=[Path(__file__).resolve(),Path(__file__).with_name('full_capture_cost.py'),Path(__file__).with_name('cell_archive.py'),
        *sorted(path for path in (ROOT/'integrations/python/moontxnwitness_capture').glob('*.py') if not path.name.startswith('test_'))]
    binding=lambda:{path.relative_to(ROOT).as_posix():hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    receipt={'schema':1,'kind':'owned-full-capture-cost','status':'not-executed','actualDatabaseExecution':False,
        'fullProtocolCompleted':False,'privateCredentialsPublished':False,'sourceBefore':binding(),
        'profile':args.profile,'maximumCells':args.max_cells,'quick':False,'archiveOutsideMeasurement':True}
    started=False;returncode=1;data=work/'data'
    try:
        receipt['driver']={name:importlib.metadata.version(name) for name in ['psycopg','psycopg-binary']}
        if any(version!='3.3.6' for version in receipt['driver'].values()):raise ValueError('Pinned psycopg3.3.6 required')
        receipt['binarySha256']={name:hashlib.sha256((binaries/(name+suffix)).read_bytes()).hexdigest() for name in ['initdb','pg_ctl','postgres']}
        version=subprocess.check_output([str(binaries/('postgres'+suffix)),'--version'],text=True)
        if ' 18.' not in version:raise ValueError('PostgreSQL18 required')
        receipt['postgresVersion']=version.strip()
        password=secrets.token_hex(20);password_file=work/'password.txt';password_file.write_text(password+'\n',encoding='ascii')
        with socket.socket() as channel:channel.bind(('127.0.0.1',0));port=channel.getsockname()[1]
        private={'host':'127.0.0.1','port':port,'dbname':'postgres','user':'mtw_cost','password':password}
        connection_file=work/'connection.json';connection_file.write_text(json.dumps(private),encoding='utf8')
        with (work/'control.log').open('xb') as log:
            subprocess.run([str(binaries/('initdb'+suffix)),'-D',str(data),'-U','mtw_cost','--pwfile',str(password_file),
                '--auth=scram-sha-256','--encoding=UTF8','--locale=C'],stdout=log,stderr=subprocess.STDOUT,check=True)
            options=f'-h 127.0.0.1 -p {port} -c shared_buffers=32MB -c max_connections=24 -c work_mem=2MB -c max_wal_size=512MB -c min_wal_size=80MB'
            receipt['serverOptions']=options
            subprocess.run([str(binaries/('pg_ctl'+suffix)),'-D',str(data),'-l',str(work/'server.log'),'-o',options,'-w','start'],stdout=log,stderr=subprocess.STDOUT,check=True)
        started=True
        env=dict(os.environ);env['MTW_PG_CONNECTION_FILE']=str(connection_file);env.pop('MTW_PG_DSN',None)
        command=[sys.executable,'-B',str(Path(__file__).with_name('full_capture_cost.py')),'--output',str(work/'study'),
            '--profile',args.profile,'--exclusive-host','--exclusive-cluster','--archive-cells','--max-cells',str(args.max_cells)]
        with (work/'study.log').open('xb') as log:child=subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT)
        returncode=child.returncode;receipt['studyExitCode']=returncode
        summary_path=work/'study/receipt.json'
        if summary_path.is_file():
            summary=json.loads(summary_path.read_text(encoding='utf8'))
            receipt.update(status=summary['status'],actualDatabaseExecution=summary.get('actualDatabaseExecution',False),
                fullProtocolCompleted=summary.get('formalProtocolCompleted',False),performanceTargetsPassed=summary.get('performanceTargetsPassed',False),
                studyReceiptSha256=hashlib.sha256(summary_path.read_bytes()).hexdigest())
    except BaseException as error:
        receipt.update(status='failed',errorClass=type(error).__name__);returncode=1
    finally:
        if started or (data/'postmaster.pid').is_file():
            if data.resolve()!=work/'data' or not (data/'PG_VERSION').is_file():raise ValueError('Owned cluster identity changed; refusing stop')
            with (work/'control.log').open('ab') as log:
                stopped=subprocess.run([str(binaries/('pg_ctl'+suffix)),'-D',str(data),'-m','fast','-w','stop'],stdout=log,stderr=subprocess.STDOUT)
            receipt['ownClusterStopped']=stopped.returncode==0
        receipt['sourceAfter']=binding();receipt['sourceUnchanged']=receipt['sourceBefore']==receipt['sourceAfter']
        if not receipt['sourceUnchanged']:receipt['status']='failed';returncode=1
        (work/'wrapper-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in receipt.items() if k not in ('sourceBefore','sourceAfter')},indent=2))
    return returncode

if __name__=='__main__':raise SystemExit(main())
