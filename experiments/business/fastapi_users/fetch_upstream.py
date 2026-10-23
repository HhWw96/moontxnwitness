"""Fetch only the declared public upstream commit into a new retained checkout."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
URL='https://github.com/fastapi-users/fastapi-users-db-sqlalchemy.git'
COMMIT='6397ace506d829a2ee12786da5d724c3f4c6b634'


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True)
    args=parser.parse_args();output=Path(args.output).resolve();output.mkdir(parents=True,exist_ok=False)
    receipt={'schema':1,'repository':URL,'commit':COMMIT,'status':'started','files':{},'firstFailureRetained':True}
    env=dict(os.environ,TEMP=str(output),TMP=str(output));flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    code=1
    try:
        for i,arguments in enumerate([['init',str(output/'source')],
            ['-C',str(output/'source'),'config','core.autocrlf','false'],
            ['-C',str(output/'source'),'remote','add','origin',URL],
            ['-C',str(output/'source'),'fetch','--depth','1','origin',COMMIT],
            ['-C',str(output/'source'),'checkout','--detach','FETCH_HEAD']]):
            with (output/('git-'+str(i)+'.log')).open('xb') as log:
                subprocess.run(['git',*arguments],env=env,stdout=log,stderr=subprocess.STDOUT,
                               check=True,timeout=120,creationflags=flags)
        source=output/'source'
        actual=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD']).decode().strip()
        if actual!=COMMIT:raise ValueError('Fetched commit mismatch')
        names=subprocess.check_output(['git','-C',str(source),'ls-tree','-r','--name-only','HEAD']).decode().splitlines()
        selected=[name for name in names if name.startswith('fastapi_users_db_sqlalchemy/') and name.endswith('.py')]
        licenses=[name for name in names if name in ('LICENSE','LICENSE.md','LICENSE.txt')]
        if not selected or not licenses:raise ValueError('Runtime source and original license must both exist')
        for name in [*selected,*licenses]:
            raw=(source/name).read_bytes();receipt['files'][name]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
        receipt.update(status='passed',licenseFiles=licenses);code=0
    except BaseException as error:receipt.update(status='failed',errorClass=type(error).__name__)
    finally:(output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'status':receipt['status'],'commit':COMMIT}));return code


if __name__=='__main__':raise SystemExit(main())
