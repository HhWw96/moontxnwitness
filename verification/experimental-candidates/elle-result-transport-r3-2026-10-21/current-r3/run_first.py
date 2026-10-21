from pathlib import Path
import hashlib,json,os,subprocess
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
OLD=ROOT/'artifacts/elle-result-summary-r2'
def bind(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def main():
    prereg=json.loads((HERE/'preregistered-before-tests.json').read_text());before=prereg['files']
    assert all(bind((HERE/name).read_bytes())==value for name,value in before.items())
    original=json.loads((OLD/'first-receipt.json').read_text());assert original['passed'] is True
    jars=[];runtime={}
    for name,item in original['runtime'].items():
        path=OLD/'runtime'/Path(name).name
        actual=bind(path.read_bytes());assert actual==item['expected']
        runtime[name]=actual;jars.append(str(path))
    java='D:/Java/jdk-25/bin/java.exe'
    command=[java,'-Xms16m','-Xmx128m','-cp',os.pathsep.join(jars),'clojure.main',str(HERE/'test_transport.clj'),
             str(HERE/'result_summary.clj'),str(HERE/'transport.clj'),str(HERE/'synthetic-raw')]
    env={key:value for key,value in os.environ.items() if key in ('PATH','SystemRoot','SYSTEMROOT','WINDIR','COMSPEC','PATHEXT')}
    with (HERE/'first.log').open('xb') as stream:
        result=subprocess.run(command,cwd=HERE,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=60)
    log=(HERE/'first.log').read_text();after={name:bind((HERE/name).read_bytes()) for name in before}
    passed=result.returncode==0 and before==after and 'Ran 6 tests containing 27 assertions.' in log and '0 failures, 0 errors.' in log
    value={'schema':1,'passed':passed,'exitCode':result.returncode,'tests':6,'assertions':27,'java':'25.0.1','clojure':'1.12.6',
           'actualSyntheticCallbackExecution':True,'actualFilesystemExecution':True,'actualElleCheckerExecuted':False,
           'actualFullWrapperCompiled':False,'formalPerformanceMeasured':False,'runtime':runtime,
           'sourceBindingsBefore':before,'sourceBindingsAfter':after,'sourceBindingsUnchanged':before==after}
    with (HERE/'first-receipt.json').open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2);stream.write('\n')
    print(json.dumps({'passed':passed,'tests':6,'assertions':27,'actualElleCheckerExecuted':False}))
    return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
