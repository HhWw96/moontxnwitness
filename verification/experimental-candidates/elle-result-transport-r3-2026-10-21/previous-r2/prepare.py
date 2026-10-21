from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
def binding(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
original=(ROOT/'artifacts/elle-batch-evaluator-r1/elle_batch.clj').read_bytes()
assert binding(original)['sha256']=='8046e0f944c84da6b68d7b93eb4c6452f0c0e2375cc312a50f32d2a90ecd271f'
source=original.decode()
position=source.index('(def options')
source=source[:position]+'(load-file (str (io/file (.getParentFile (io/file *file*)) "result_summary.clj")))\n\n'+source[position:]
start=source.index('            original-valid (:valid? result)')
end=source.index('            raw-file',start)
source=source[:start]+'            summary (summarize-elle-result result)\n'+source[end:]
old='''        {"id" id "inputSha256" (get request "inputSha256") "valid" valid
         "anomalyTypes" anomalies "cycleSearchTimeout" timeout?
         "rawResultFile" (.getName raw-file) "actualElleResultReturned" true})'''
new='''        (merge summary
               {"id" id "inputSha256" (get request "inputSha256")
                "rawResultFile" (.getName raw-file) "actualElleInvocationAttempted" true
                "actualElleResultReturned" true}))'''
assert old in source;source=source.replace(old,new)
source=source.replace('''  ;; as execution timeouts and retain every partial file, without retrying.''',
'''  ;; as actual timeout, execution failure or never invoked, according to retained
  ;; execution evidence. Keep every partial file and never retry an input.''')
with (HERE/'elle_batch.clj').open('xb') as stream:stream.write(source.encode())
frozen={path.name:binding(path.read_bytes()) for path in HERE.glob('*.clj')}
value={'schema':1,'candidate':'typed-Elle-result-transport-r2','baselineWrapper':binding(original),'files':frozen,
       'plannedPureUnitJavaMajor':25,'plannedClojure':'1.12.6','plannedUnitTests':5,'plannedAssertions':16,
       'pureUnitScope':'No Elle classes/checkers or2000 input evaluator loaded; Java21 actual upstream run remains separate',
       'actualCheckerExecuted':False,'actualBatchWrapperCompiled':False,'actualUnitTestsExecuted':False,'formalPerformanceMeasured':False}
with (HERE/'preregistered-before-tests.json').open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2);stream.write('\n')
print(json.dumps({'frozenFiles':len(frozen),'actualUnitTestsExecuted':False}))
