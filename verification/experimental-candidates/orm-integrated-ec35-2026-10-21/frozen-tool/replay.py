"""Tokenless, exact-source local-build replay of the frozen independent24 driver."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
PROFILE_SHA='7bc8b50b443339d0bbbf20f351ad0eda52fa2f8c70d9fd62ddd18379ac2e0079'
DRIVER_SHA='6f2bf2fe5fcd9e67990cf43fb4069651507a1b48ee057e4da44ec4974cb2d5e3'
CONTRACT_SHA='2e30dcccb17920312a50f88048ffcd4049a99fb9e2818d6d6d9c92feb4017051'
BASELINE_SHA='1835044d4c5ab478ad32af879d4828fecd9778d2347bf817adcf8dca75be2938'

def binding(path):
    h=hashlib.sha256();n=0
    with Path(path).open('rb') as stream:
        while block:=stream.read(65536):
            n+=len(block)
            if n>64*1024*1024:raise ValueError('Bound file exceeds64MiB')
            h.update(block)
    return {'bytes':n,'sha256':h.hexdigest()}

def load(path):
    if Path(path).stat().st_size>8*1024*1024:raise ValueError('Small metadata byte bound')
    return json.loads(Path(path).read_bytes())

def save(path,value):
    with Path(path).open('x',encoding='utf-8',newline='\n') as stream:json.dump(value,stream,indent=2);stream.write('\n')
    return binding(path)

def copy(source,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    with Path(source).open('rb') as src,target.open('xb') as dst:shutil.copyfileobj(src,dst,65536)
    if binding(source)!=binding(target):raise ValueError('Copied frozen bytes differ')

def source_fingerprint(root):
    names=['moon.mod']+[p.relative_to(root).as_posix() for p in (root/'src').rglob('*')
                       if p.is_file() and (p.suffix=='.mbt' or p.name=='moon.pkg')]
    h=hashlib.sha256()
    for name in sorted(names,key=lambda s:s.encode('utf-16-be')):
        h.update(name.encode());h.update(b'\0');h.update((root/name).read_bytes());h.update(b'\0')
    return h.hexdigest()

def child_environment():
    words=('TOKEN','SECRET','PASSWORD','AUTHORIZATION','PRIVATE_KEY','API_KEY')
    return {k:v for k,v in os.environ.items() if not any(word in k.upper() for word in words)}

def execute(command,work):
    paths={name:work/('runtime-process.'+name) for name in ('stdout','stderr')}
    start=time.monotonic();failure=None
    with paths['stdout'].open('xb') as stdout,paths['stderr'].open('xb') as stderr:
        process=subprocess.Popen(command,cwd=work,env=child_environment(),stdout=stdout,stderr=stderr,
                                 creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            while process.poll() is None:
                if time.monotonic()-start>240:raise TimeoutError('Independent replay process exceeded240s')
                if any(p.stat().st_size>8*1024*1024 for p in paths.values()):raise ValueError('Independent replay output bound')
                time.sleep(.1)
        except Exception as error:
            failure=type(error).__name__;process.kill();process.wait(timeout=10)
    if any(p.stat().st_size>8*1024*1024 for p in paths.values()):failure='OutputByteLimit'
    record={'exitCode':process.returncode,'elapsedSeconds':time.monotonic()-start,
            'stdout':binding(paths['stdout']),'stderr':binding(paths['stderr']),'failureClass':failure}
    save(work/'runtime-process.json',record)
    if failure:raise RuntimeError('Bounded independent child failed: '+failure)
    return record

def differences(expected,actual,path='$',out=None):
    out=[] if out is None else out
    if len(out)>=24:return out
    if type(expected) is not type(actual):out.append({'path':path,'expected':expected,'actual':actual});return out
    if isinstance(expected,dict):
        for key in sorted(set(expected)|set(actual)):
            if key not in expected or key not in actual:out.append({'path':path+'.'+key,'expected':expected.get(key),'actual':actual.get(key)})
            else:differences(expected[key],actual[key],path+'.'+key,out)
            if len(out)>=24:break
    elif isinstance(expected,list):
        if len(expected)!=len(actual):out.append({'path':path+'.length','expected':len(expected),'actual':len(actual)})
        for i,(left,right) in enumerate(zip(expected,actual)):
            differences(left,right,path+'['+str(i)+']',out)
            if len(out)>=24:break
    elif expected!=actual:out.append({'path':path,'expected':expected,'actual':actual})
    return out

def preflight(source,runtime):
    assert binding(HERE/'target-profile.json')['sha256']==PROFILE_SHA
    assert binding(HERE/'runtime.mjs')['sha256']==DRIVER_SHA
    assert binding(HERE/'contract-v1.json')['sha256']==CONTRACT_SHA
    assert binding(HERE/'baseline-bindings.json')['sha256']==BASELINE_SHA
    profile=load(HERE/'target-profile.json')
    assert source_fingerprint(source)==profile['sourceSha256']
    manifest=load(runtime/'build-manifest.json')
    assert manifest['sourceSha256']==profile['sourceSha256'] and manifest['version']==profile['version']
    for name,expected in profile['files'].items():assert binding(runtime/name)==expected,name
    assert manifest['coreSha256']==profile['files']['core.mjs']['sha256']
    assert manifest['captureCoreSha256']==profile['files']['capture-core.mjs']['sha256']
    for name,expected in profile['expectedInputs'].items():assert binding(HERE/'inputs'/name)==expected
    for case in load(HERE/'baseline-bindings.json')['cases']:
        assert binding(HERE/'baseline-reports'/case['file'])==case['reportBinding']
    return profile

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source-root',type=Path,default=ROOT)
    parser.add_argument('--runtime-dir',type=Path,required=True);parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--node',default='node');args=parser.parse_args()
    work=args.work.resolve();work.mkdir(parents=True,exist_ok=False)
    result={'schema':1,'kind':'independent-frozen24-current-local-build-replay','passed':False,'complete':False,
            'semantic24Passed':False,'strict24OutputBytesPassed':False,'valid4OutputBytesPassed':False,
            'sourceKind':'current local build, not an old public runtime artifact','publicDownloadAccepted':False,
            'oldPublicSignatureExtended':False,'fullApplicationAccepted':False,'stableReleaseAccepted':False,
            'databaseExecution':False,'formalPerformance':False,'checks':[],'startedAt':datetime.now(timezone.utc).isoformat()}
    try:
        assert not os.environ.get('GITHUB_TOKEN') and not os.environ.get('GH_TOKEN'),'Parent must not receive GitHub tokens'
        profile=preflight(args.source_root.resolve(),args.runtime_dir.resolve())
        result['target']=profile;result['driverSha256']=DRIVER_SHA;result['originalContractSha256']=CONTRACT_SHA
        save(work/'target-profile.json',profile)
        for name in profile['files']:copy(args.runtime_dir/name,work/'actual-build'/name)
        copy(args.runtime_dir/'capture-core.mjs',work/'artifact/experimental-capture-core.mjs')
        copy(HERE/'runtime.mjs',work/'runtime.mjs');copy(HERE/'contract-v1.json',work/'contract-v1.json')
        for name in profile['expectedInputs']:copy(HERE/'inputs'/name,work/'inputs'/name)
        # Only module identity/input binding fields consumed by the unchanged original driver.
        save(work/'profile.json',{'schema':1,'kind':'current-local-build-driver-binding',
             'sourceSha256':profile['sourceSha256'],'moduleSha256':profile['files']['capture-core.mjs']['sha256'],
             'inputs':profile['expectedInputs'],'originalPublicModuleRun':None,'publicDownloadAccepted':False})
        process=execute([args.node,str(work/'runtime.mjs'),str(work),str(work/'result')],work)
        runtime=load(work/'result/independent-result.json');result['runtime']=runtime
        result['complete']=runtime['complete'] and len(runtime['cases'])==24
        result['semantic24Passed']=process['exitCode']==0 and runtime['passed'] and result['complete'] and all(c['passed'] for c in runtime['cases'])
        original=load(HERE/'baseline-bindings.json')['cases'];comparisons=[]
        for case,baseline in zip(runtime['cases'],original):
            path=work/'result'/baseline['file'];current=binding(path)
            same_input=all(case[k]==baseline[k] for k in ('name','expected','inputBytes','inputSha256'))
            comparison={'name':case['name'],'inputAndExpectationUnchanged':same_input,
                        'expectedOutput':baseline['reportBinding'],'actualOutput':current,'fullOutputBytesEqual':current==baseline['reportBinding']}
            if not comparison['fullOutputBytesEqual']:
                comparison['unmodifiedDiagnosticDifferences']=differences(load(HERE/'baseline-reports'/baseline['file']),load(path))
            comparisons.append(comparison)
        result['checks']=comparisons
        result['all24InputsAndExpectationsUnchanged']=len(comparisons)==24 and all(c['inputAndExpectationUnchanged'] for c in comparisons)
        result['strict24OutputBytesPassed']=len(comparisons)==24 and all(c['fullOutputBytesEqual'] for c in comparisons)
        result['valid4OutputBytesPassed']=len(comparisons)==24 and all(c['fullOutputBytesEqual'] for c in comparisons[:4])
        result['invalid20OutputBytesPassed']=len(comparisons)==24 and all(c['fullOutputBytesEqual'] for c in comparisons[4:])
        result['sourceStillMatchesTarget']=source_fingerprint(args.source_root.resolve())==profile['sourceSha256']
        result['actualCopiedBuildStillMatchesTarget']=all(binding(work/'actual-build'/n)==v for n,v in profile['files'].items())
        result['passed']=all(result[k] for k in ('semantic24Passed','strict24OutputBytesPassed','all24InputsAndExpectationsUnchanged',
                                                'sourceStillMatchesTarget','actualCopiedBuildStillMatchesTarget'))
    except Exception as error:
        result['errorClass']=type(error).__name__;result['error']=str(error).replace(str(work),'<fresh>').replace(str(ROOT),'<repository>')
    result['finishedAt']=datetime.now(timezone.utc).isoformat()
    path=work/'independent-replay.json';receipt=save(path,result)
    print(json.dumps({'passed':result['passed'],'complete':result['complete'],'semantic24Passed':result['semantic24Passed'],
                      'strict24OutputBytesPassed':result['strict24OutputBytesPassed'],'valid4OutputBytesPassed':result['valid4OutputBytesPassed'],
                      'receiptSha256':receipt['sha256']}),flush=True)
    return 0 if result['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
