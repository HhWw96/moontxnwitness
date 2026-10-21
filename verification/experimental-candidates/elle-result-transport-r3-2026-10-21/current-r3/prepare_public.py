from pathlib import Path
import hashlib,json,re
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
OLD=ROOT/'artifacts/elle-result-summary-r2'
PUBLIC=ROOT/'verification/experimental-candidates/elle-result-transport-r3-2026-10-21'
def bind(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def main():
    files={}
    def copy(path,name):
        original=path.read_bytes();raw=original
        for prefix in (str(ROOT).replace('\\','\\\\'),str(ROOT),str(ROOT).replace('\\','/')):
            raw=raw.replace(prefix.encode(),b'<owned-experiment>')
        assert str(Path.home()).encode() not in raw
        assert str(Path.home()).replace('\\','\\\\').encode() not in raw
        assert not re.search(rb'gh[pousr]_[A-Za-z0-9]{20,}',raw)
        target=PUBLIC/name;target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as stream:stream.write(raw)
        files[name]={'original':bind(original),'public':bind(raw),'derived':raw!=original}
    for root,prefix in ((OLD,'previous-r2'),(HERE,'current-r3')):
        for path in sorted(root.rglob('*')):
            if not path.is_file() or path.suffix not in ('.clj','.py','.json','.log','.edn'):continue
            if 'runtime' in path.relative_to(root).parts:continue
            copy(path,prefix+'/'+path.relative_to(root).as_posix())
    for directory,prefix in (('elle-summary-independent-r2','independent-r2'),('elle-summary-independent-r3','independent-r3')):
        source=ROOT/'artifacts'/directory
        assert source.is_dir()
        for path in sorted(source.iterdir()):
            if path.is_file():copy(path,prefix+'/'+path.name)
    value={'schema':1,'kind':'typed-and-retained-Elle-result-transport-development','files':files,
           'pureSummaryTests':5,'pureSummaryAssertions':16,'syntheticTransportTests':6,'syntheticTransportAssertions':27,
           'java':'25.0.1','clojure':'1.12.6','actualElleCheckerExecuted':False,'actualFullWrapperCompiled':False,
           'actualExpansion2000Executed':False,'formalPerformanceMeasured':False,
           'runtimeJarsRedistributed':False,'privateOriginalsRetainedLocally':True}
    with (PUBLIC/'publication-index.json').open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2);stream.write('\n')
    print(json.dumps({'publicFiles':len(files),'explicitDerivatives':sum(v['derived'] for v in files.values()),'actualElleCheckerExecuted':False}))
if __name__=='__main__':main()
