"""Run the fixed model driver cases in one NEW retained owned PG18 cluster."""
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


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--bin',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();output=Path(args.output).resolve();output.mkdir(parents=True,exist_ok=False)
    binaries=Path(args.bin).resolve();suffix='.exe' if os.name=='nt' else '';data=output/'data'
    if os.name=='nt' and not str(output).isascii():raise ValueError('Owned Windows data path must be ASCII')
    password=secrets.token_hex(20);(output/'password.txt').write_text(password+'\n',encoding='ascii')
    environment=dict(os.environ,TEMP=str(output),TMP=str(output),PYTHONIOENCODING='utf-8')
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    receipt={'kind':'owned-model-driver-profile','status':'not-executed','actualDatabaseExecution':False,
        'formalPerformanceMeasurement':False,'sourceBefore':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    started=False;code=1
    with (output/'control.log').open('xb') as log:
        def run(parts):return subprocess.run([str(p) for p in parts],env=environment,stdin=subprocess.DEVNULL,
            stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120,creationflags=flags)
        try:
            receipt['binarySha256']={n:hashlib.sha256((binaries/(n+suffix)).read_bytes()).hexdigest() for n in ('initdb','pg_ctl','postgres')}
            run([binaries/('initdb'+suffix),'-D',data,'-U','mtw','--locale=C','--encoding=UTF8',
                '--auth-host=scram-sha-256','--auth-local=trust','--pwfile='+str(output/'password.txt')])
            with socket.socket() as candidate:candidate.bind(('127.0.0.1',0));port=candidate.getsockname()[1]
            run([binaries/('pg_ctl'+suffix),'-D',data,'-l',output/'server.log','-o',
                '-h 127.0.0.1 -p '+str(port)+' -c shared_buffers=32MB -c max_connections=20 -c work_mem=2MB','-w','start'])
            started=True;receipt['actualDatabaseExecution']=True
            private=output/'connection.json';private.write_text(json.dumps({'host':'127.0.0.1','port':port,'dbname':'postgres','user':'mtw','password':password}),encoding='utf8')
            with (output/'business.log').open('xb') as business:
                result=subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('driver_cases.py')),
                    '--connection-file',str(private),'--output',str(output/'suite')],env=environment,stdin=subprocess.DEVNULL,
                    stdout=business,stderr=subprocess.STDOUT,timeout=240,creationflags=flags)
            code=result.returncode;receipt.update(status='passed' if code==0 else 'failed',businessExitCode=code)
        except BaseException as error:receipt.update(status='failed',errorClass=type(error).__name__)
        finally:
            if started and (data/'postmaster.pid').exists():
                actual=Path((data/'postmaster.pid').read_text(encoding='utf8').splitlines()[1]).resolve()
                if actual!=data:raise ValueError('Refuse to stop another database')
                try:run([binaries/('pg_ctl'+suffix),'-D',data,'-m','fast','-w','stop']);receipt['ownClusterStopped']=True
                except BaseException as error:receipt.update(status='failed',stopErrorClass=type(error).__name__);code=1
            receipt['sourceAfter']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
            receipt['sourceUnchanged']=receipt['sourceBefore']==receipt['sourceAfter']
            if not receipt['sourceUnchanged']:receipt['status']='failed';code=1
            (output/'wrapper-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'status':receipt['status'],'businessExitCode':code,'ownClusterStopped':receipt.get('ownClusterStopped')}));return code


if __name__=='__main__':raise SystemExit(main())
