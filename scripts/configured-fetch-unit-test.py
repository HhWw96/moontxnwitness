"""Run bounded wrapper tests and produce a fresh actual fake-driver frame fixture."""
import argparse,hashlib,json,os,re,subprocess,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--dependency-root',required=True);args=parser.parse_args()
    dependency=Path(args.dependency_root).resolve();run=ROOT/'artifacts/configured-fetch-unit-runs'/uuid.uuid4().hex;run.mkdir(parents=True)
    env={**os.environ,'PYTHONPATH':str(dependency),'PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1','MTW_CONFIGURED_FETCH_TEST_ROOT':str(run),'TEMP':str(run),'TMP':str(run)}
    test=ROOT/'integrations/python/moontxnwitness_capture/test_configured_fetch.py'
    result=subprocess.run([sys.executable,'-B',str(test)],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    (run/'tests.txt').write_bytes(result.stdout)
    if result.returncode:print(result.stdout.decode('utf8',errors='replace'));return result.returncode
    os.environ.update({k:env[k] for k in ('MTW_CONFIGURED_FETCH_TEST_ROOT','PYTHONDONTWRITEBYTECODE')})
    sys.path[:0]=[str(ROOT/'integrations/python'),str(dependency)]
    from moontxnwitness_capture.test_configured_fetch import Raw,CONFIG,SQL
    from moontxnwitness_capture.configured_fetch import ConfiguredInstrumentation
    observer=ConfiguredInstrumentation(run/'fixture-observer',CONFIG);cursor=observer.wrap(Raw()).cursor()
    cursor.execute(SQL,(1,));cursor.fetchone();cursor.fetchmany(1);cursor.fetchall();cursor.close();observer.close()
    frames=[(item['kind'],json.loads(item['frameText'])) for item in map(json.loads,(observer.output/'lifecycle.jsonl').read_text(encoding='utf8').splitlines()) if 'frameText'in item]
    execution=next(f for kind,f in frames if kind=='configured-execution');native=next(f for kind,f in frames if kind=='configured-native-result')
    deliveries=[f for kind,f in frames if kind=='configured-delivery']
    fixture=ROOT/'artifacts/configured-fetch-fixture.json';fixture.write_text(json.dumps({'config':CONFIG.to_dict(),'execution':execution,'native':native,'deliveries':deliveries},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    receipt={'format':'configured-fetch-wrapper-tests/v1','status':'passed','actualDatabaseExecution':False,'testOutputSha256':sha(run/'tests.txt'),'fixtureSha256':sha(fixture),'testModuleSha256':sha(test),'implementationSha256':sha(ROOT/'integrations/python/moontxnwitness_capture/configured_fetch.py'),'tests':int(re.search(rb'Ran (\d+) tests',result.stdout).group(1)),'publicReleasePerformed':False}
    (ROOT/'artifacts/configured-fetch-wrapper-validation.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
    print(json.dumps(receipt));return 0
if __name__=='__main__':raise SystemExit(main())
