"""Configured producer/installation checks using fake drivers only."""
from __future__ import annotations
import argparse,ast,hashlib,importlib.metadata,json,os,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dependency-root')
    a=parser.parse_args()
    if a.dependency_root:sys.path.insert(0,str(Path(a.dependency_root).resolve()))
    import sqlglot
    if sqlglot.__version__!='30.26.0' or importlib.metadata.version('sqlglot')!='30.26.0':
        raise ValueError('Require the fixed optional SQLGlot 30.26.0')
    dependency=Path(sqlglot.__file__).resolve().parent.parent
    work=ROOT/'artifacts/configured-session-pure';work.mkdir(parents=True,exist_ok=True)
    temporary=work/'temp';temporary.mkdir(exist_ok=True)
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONUTF8':'1',
        'PYTHONPATH':os.pathsep.join([str(ROOT/'integrations/python'),str(dependency)]),
        'MTW_SOURCE_TEST_ROOT':str(work/'source'),'TEMP':str(temporary),'TMP':str(temporary)}
    rows={}
    def run(key,args,expected=None):
        result=subprocess.run([sys.executable,'-B',*args],cwd=ROOT,env=env,capture_output=True,timeout=180)
        raw=result.stdout+result.stderr;log=work/(key+'.log')
        if result.returncode and not (work/(key+'-first-failure.log')).exists():
            (work/(key+'-first-failure.log')).write_bytes(raw)
        log.write_bytes(raw)
        if result.returncode:raise RuntimeError('Pure test failed; inspect '+str(log))
        if expected is not None:
            if b'Ran '+str(expected).encode()+b' tests' not in raw:raise ValueError('Executed count differs for '+key)
        rows[key]={'passed':True,'tests':expected,'outputSha256':hashlib.sha256(raw).hexdigest()}
    run('session',['scripts/configured-session-unit-test.py'],18)
    run('sql',['scripts/configured-sql-unit-test.py','--dependency-root',str(dependency)])
    adapter=json.loads((ROOT/'artifacts/configured-sql-adapter-validation.json').read_bytes())
    if not adapter['passed'] or adapter['testsRun']!=86:raise ValueError('SQL adapter actual checks differ')
    rows['sql']['tests']=adapter['testsRun']
    run('fetch',['scripts/configured-fetch-unit-test.py','--dependency-root',str(dependency)])
    fetch=json.loads((ROOT/'artifacts/configured-fetch-wrapper-validation.json').read_bytes())
    if fetch['status']!='passed' or fetch['tests']!=29:raise ValueError('Actual fake-driver checks differ')
    rows['fetch']['tests']=fetch['tests']
    run('source',['-m','unittest','moontxnwitness_capture.test_configured_source','-v'],39)
    files=['integrations/python/moontxnwitness_capture/configured_session.py',
        'scripts/configured-session-unit-test.py','scripts/configured-session-postgres.py',
        'scripts/configured-session-pure-test.py','examples/configured-session/startup.py',
        'integrations/python/moontxnwitness_capture/configured_source.py']
    for name in files:ast.parse((ROOT/name).read_text(encoding='utf8'),filename=name)
    result={'format':'configured-session-pure-checks/v1','passed':True,'results':rows,'ASTFiles':len(files),
        'parserVersion':sqlglot.__version__,'actualDatabaseExecution':False,'sourceFactsProduced':False,
        'writerWindowVerified':False,'isolationAnalysisReady':False}
    (work/'receipt.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print(json.dumps(result))
    return 0

if __name__=='__main__':raise SystemExit(main())
