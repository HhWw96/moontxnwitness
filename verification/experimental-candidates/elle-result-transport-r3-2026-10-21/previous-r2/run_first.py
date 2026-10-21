"""One pure Clojure transport unit run; no upstream Elle dependency/execution."""
from pathlib import Path
import hashlib,json,os,subprocess,urllib.request,traceback
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
def binding(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def main():
    before=json.loads((HERE/'preregistered-before-tests.json').read_text())
    expected=before['files']
    assert all(binding((HERE/name).read_bytes())==value for name,value in expected.items())
    original=ROOT/'verification/experimental-candidates/elle-smoke-r2-2026-10-21/actual-ci-39599513353/actual/execution-receipt.json'
    runtime=json.loads(original.read_text())['actualRuntimeDependencyBindings']
    names=['org/clojure/clojure/1.12.6/clojure-1.12.6.jar','org/clojure/spec.alpha/0.5.238/spec.alpha-0.5.238.jar',
           'org/clojure/core.specs.alpha/0.4.74/core.specs.alpha-0.4.74.jar']
    libs=HERE/'runtime';libs.mkdir(exist_ok=False)
    receipt={'schema':1,'passed':False,'actualElleCheckerExecuted':False,'actualBatchWrapperCompiled':False,
             'actualPureUnitExecuted':False,'formalPerformanceMeasured':False,'sourceBindingsBefore':expected,'runtime':{},
             'dependencyMetadataSourceSha256':binding(original.read_bytes())['sha256']}
    code=1
    try:
        jars=[]
        for name in names:
            pin=runtime['runtime-home/.m2/repository/'+name];target=libs/Path(name).name
            url='https://repo.maven.apache.org/maven2/'+name
            with urllib.request.urlopen(url,timeout=45) as response:
                assert response.status==200
                raw=response.read(pin['bytes']+1)
            with target.open('xb') as stream:stream.write(raw)
            actual=binding(raw);receipt['runtime'][name]={'expected':pin,'actual':actual,'url':url}
            assert actual==pin,'Published fixed runtime bytes differ'
            jars.append(str(target))
        java=Path('D:/Java/jdk-25/bin/java.exe')
        version=subprocess.check_output([str(java),'-version'],stderr=subprocess.STDOUT,timeout=20)
        with (HERE/'java-version.log').open('xb') as stream:stream.write(version)
        receipt['javaVersionOutput']=version.decode('utf8',errors='replace')
        command=[str(java),'-Xms16m','-Xmx128m','-cp',os.pathsep.join(jars),'clojure.main',
                 str(HERE/'test_result_summary.clj'),str(HERE/'result_summary.clj')]
        env={key:value for key,value in os.environ.items() if key in ('PATH','SystemRoot','SYSTEMROOT','WINDIR','COMSPEC','PATHEXT')}
        with (HERE/'first.log').open('xb') as stream:
            receipt['actualPureUnitExecuted']=True
            result=subprocess.run(command,cwd=HERE,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=60)
        receipt['exitCode']=result.returncode;code=result.returncode
        receipt['passed']=code==0
    except Exception as error:
        receipt['failure']={'class':type(error).__name__,'message':str(error)}
    finally:
        after={name:binding((HERE/name).read_bytes()) for name in expected}
        receipt['sourceBindingsAfter']=after;receipt['sourceBindingsUnchanged']=expected==after
        receipt['passed']=receipt['passed'] and expected==after
        with (HERE/'first-receipt.json').open('x',encoding='utf8') as stream:json.dump(receipt,stream,indent=2);stream.write('\n')
    print(json.dumps({'passed':receipt['passed'],'actualPureUnitExecuted':receipt['actualPureUnitExecuted'],'actualElleCheckerExecuted':False}))
    return code if receipt['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
