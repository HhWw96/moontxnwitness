"""First isolated mock/filesystem run of the unchanged author R2 candidate."""
from pathlib import Path
import hashlib,json,os,subprocess
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
SOURCE=ROOT/'artifacts/plain-v3-epoch-r2-draft'
def binding(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def main():
    raw=(SOURCE/'candidate-index-static-v1.json').read_bytes()
    assert binding(raw)['sha256']=='f6610c932dac6f4576072d366fdbebf6b7ca4e7dfd5da07240ad279742b47e0a'
    index=json.loads(raw)
    expected={f'artifacts/plain-v3-epoch-r2-draft/{name}':value for name,value in index['files'].items()}
    expected.update(index['dependencies'])
    expected['artifacts/plain-v3-epoch-r2-draft/candidate-index-static-v1.json']=binding(raw)
    restored=HERE/'repository';restored.mkdir(exist_ok=False)
    scratch=HERE/'scratch';scratch.mkdir(exist_ok=False)
    for name,item in expected.items():
        content=(ROOT/name).read_bytes();assert binding(content)==item,name
        target=restored/name;target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as stream:stream.write(content)
    env={key:value for key,value in os.environ.items() if key in ('PATH','SystemRoot','SYSTEMROOT','WINDIR','COMSPEC','PATHEXT','USERPROFILE','HOME')}
    env.update(MTW_JOURNAL_SCRATCH=str(scratch.resolve()),TEMP=str(scratch.resolve()),TMP=str(scratch.resolve()),PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
    command=[str(ROOT/'artifacts/pg-driver/Scripts/python.exe'),'-B','artifacts/plain-v3-epoch-r2-draft/test_hardening.py']
    attempt={'schema':1,'candidateIndex':binding(raw),'allSourcesBefore':expected,'actualDatabaseExecution':False,'formalPerformanceMeasured':False}
    with (HERE/'before.json').open('x',encoding='utf8') as stream:json.dump(attempt,stream,indent=2)
    try:
        with (HERE/'first.log').open('xb') as stream:
            result=subprocess.run(command,cwd=restored,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=180)
        attempt['exitCode']=result.returncode
    except subprocess.TimeoutExpired:
        attempt['failure']='TimeoutExpired'
    after={name:binding((restored/name).read_bytes()) for name in expected}
    attempt['allSourcesAfter']=after;attempt['allSourcesUnchanged']=after==expected
    paths=list(scratch.glob('*/test-receipt.json'))
    attempt['unitReceipts']=[{'path':p.relative_to(HERE).as_posix(),**binding(p.read_bytes())} for p in paths]
    receipt=json.loads(paths[0].read_text()) if len(paths)==1 else {}
    attempt['passed']=(attempt.get('exitCode')==0 and attempt['allSourcesUnchanged'] and receipt.get('passed') is True
                       and receipt.get('tests')==73 and receipt.get('skipped')==[] and receipt.get('actualDatabaseExecution') is False)
    with (HERE/'first-attempt.json').open('x',encoding='utf8') as stream:json.dump(attempt,stream,indent=2);stream.write('\n')
    print(json.dumps({'passed':attempt['passed'],'tests':receipt.get('tests'),'skipped':len(receipt.get('skipped',[])),'actualDatabaseExecution':False}))
    return 0 if attempt['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
