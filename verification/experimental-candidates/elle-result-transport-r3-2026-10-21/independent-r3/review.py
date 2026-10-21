"""Independent read-only review of staged result retention; never run JVM."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
SRC=ROOT/'artifacts/elle-result-summary-r3'
OLD=ROOT/'artifacts/elle-result-summary-r2'
def bind(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def read(name):return (SRC/name).read_bytes()
checks=[]
def check(name,value):
    checks.append({'name':name,'passed':bool(value)})
    if not value:raise AssertionError(name)
prereg=json.loads(read('preregistered-before-tests.json'));first=json.loads(read('first-receipt.json'));reader=json.loads(read('reader-first-receipt.json'))
expected=prereg['files'];actual={name:bind(read(name)) for name in expected}
check('exact6-frozen-source-bindings',len(expected)==6 and expected==actual==first['sourceBindingsBefore']==first['sourceBindingsAfter'])
check('pure6-tests27-assertions',first['passed'] is True and first['exitCode']==0 and first['tests']==6 and first['assertions']==27
      and first['actualSyntheticCallbackExecution'] is True and first['actualFilesystemExecution'] is True)
log=read('first.log')
check('actual-pure-unit-log',b'Ran 6 tests containing 27 assertions.' in log and b'0 failures, 0 errors.' in log
      and b':java "25.0.1"' in log and b':clojure "1.12.6"' in log and b':actual-elle-checker false' in log)
check('runtime-scope-not-promoted',first['actualElleCheckerExecuted'] is False and first['actualFullWrapperCompiled'] is False and first['formalPerformanceMeasured'] is False)
check('actual-reader-only-receipt',reader['passed'] is True and reader['exitCode']==0 and reader['sourceBefore']==reader['sourceAfter']==actual['elle_batch.clj']
      and reader['wrapperFormsEvaluated'] is False and reader['actualFullWrapperCompiled'] is False and reader['actualElleCheckerExecuted'] is False)
check('actual8-form-reader-log',b'{:forms 8, :evaluated false, :actual-elle-checker false}' in read('reader-first.log'))
runtime={}
for name,item in first['runtime'].items():
    value=bind((OLD/'runtime'/Path(name).name).read_bytes());check('runtime-'+name,value==item);runtime[name]=value
check('same-accepted-typed-helper',bind(read('result_summary.clj'))==bind((OLD/'result_summary.clj').read_bytes())
      and bind(read('result_summary.clj'))['sha256']=='28cc491ea897d7191ea6305219abdd1009d53b822a79cfccbac3d79dfdf1709c')
transport=read('transport.clj').decode();wrapper=read('elle_batch.clj').decode();tests=read('test_transport.clj').decode()
positions=[transport.index('(let [invoke (prepare-checker)]'),transport.index('(swap! state assoc :attempted true)'),transport.index('(let [result (invoke)]'),
           transport.index('(swap! state assoc :returned true)'),transport.index('(spit raw-file (str (pr-str result)'),
           transport.index('(swap! state assoc :retained true)'),transport.index('(summarize-elle-result result)')]
check('ordered-prepare-attempt-return-retain-summary',positions==sorted(positions) and len(set(positions))==7)
check('source-original-result-retained-before-summary','(pr-str result)' in transport and '(:returned observed)' in transport and '(:retained observed)' in transport)
check('all4-error-stages-distinct',all(stage in transport for stage in ['"preparation"','"checker"','"result-retention"','"result-transport"']))
check('secondary-diagnostic-failure-does-not-mask-primary','(catch Throwable storage-error false)' in transport
      and '"errorClass" (.getName (class error)) "errorMessage" (.getMessage error)' in transport)
check('wrapper-checker-deferred-until-attempt','(execute-retained-result' in wrapper and '(fn [] (checker options h))' in wrapper
      and '(io/file raw-root (str id ".edn"))' in wrapper and '(io/file raw-root (str id ".exception.edn"))' in wrapper)
check('wrapper-still-pins-future-runtime','(= "21" (System/getProperty "java.specification.version"))' in wrapper and '(= "1.12.6" (clojure-version))' in wrapper)
check('synthetic-test-assertions-cover-evidence-and-stages','summary-error-keeps-original-returned-evidence' in tests
      and '(is (= original (edn/read-string (slurp raw))))' in tests and '(is (true? (get output "actualElleResultReturned")))' in tests
      and '(is (= "original checker error" (get output "errorMessage")))' in tests)
raws={p.name:bind(p.read_bytes()) for p in sorted((SRC/'synthetic-raw').iterdir()) if p.is_file()}
check('exact6-synthetic-retained-files',set(raws)=={'checker-error.exception.edn','false-timeout.edn','prepare-error.exception.edn',
      'raw-storage-error.exception.edn','summary-error.edn','summary-error.exception.edn'})
check('raw-false-with-timeout-retained',read('synthetic-raw/false-timeout.edn')==b'{:valid? false, :anomaly-types [:PL-SI-cycle-exists :cycle-search-timeout]}\n')
check('raw-result-after-summary-failure-retained',read('synthetic-raw/summary-error.edn')==b'{:valid? false, :anomaly-types [:G2-item]}\n'
      and read('synthetic-raw/summary-error.exception.edn')==b'{:class "clojure.lang.ExceptionInfo", :message "summary refused"}\n')
check('preparation-checker-errors-not-reclassified',read('synthetic-raw/prepare-error.exception.edn')==b'{:class "clojure.lang.ExceptionInfo", :message "bad history"}\n'
      and read('synthetic-raw/checker-error.exception.edn')==b'{:class "clojure.lang.ExceptionInfo", :message "checker stopped"}\n')
check('no-false-retained-file-on-storage-failure',not (SRC/'synthetic-raw/absent-parent').exists() and '"rawResultFile" (when (:retained observed)' in transport)
check('original-pre-freeze-static-failure-preserved',json.loads(read('history/static-first-failure.json'))['testsExecuted'] is False
      and prereg['staticFailure'].startswith('One extra closing delimiter'))
receipt={'schema':1,'kind':'independent-AI-short-staged-result-transport-review','passed':True,'checkCount':len(checks),'failedChecks':0,'checks':checks,
         'sourceBindings':actual,'runtimeJarBindingsRehashed':runtime,'syntheticRawBindings':raws,
         'sourceLogicReview':'Returned upstream result is retained before summary conversion; errors preserve attempted/returned/retained state and primary error class/message.',
         'actualPureTestsObserved':6,'actualPureAssertionsObserved':27,'actualJavaVersionObserved':'25.0.1','actualClojureVersionObserved':'1.12.6',
         'actualPureTestsReexecutedByReviewer':False,'actualJvmExecutedByReviewer':False,'candidateImportedOrExecutedByReviewer':False,
         'actualElleCheckerExecuted':False,'actual2000InputEvaluationExecuted':False,'fixedJava21ElleIntegrationAccepted':False,
         'fullWrapperReaderFormsOnly':8,'actualFullWrapperCompiled':False,'formalPerformanceMeasured':False,
         'remainingExecutionGates':['Separate reviewed outer collector with original input and runtime/dependency bindings.',
          'Process/output budgets, cleanup and accounting for timeout vs execution failure vs never invoked.',
          'Actual fixed-Java21 upstream integration, SDK comparison and independent result evidence verification.',
          'No per-record fsync or crash-durable raw-output claim is established by spit/close.'],
         'publicationPrivacy':[{'file':'synthetic-raw/raw-storage-error.exception.edn','originalBinding':raws['raw-storage-error.exception.edn'],
                               'action':'Contains local private path. Publish an explicitly bound redacted derivative and keep original private bytes unchanged.'}],
         'priorFindingResolved':{'reviewReceipt':'artifacts/elle-summary-independent-r2/receipt.json','issue':'Summary threw before raw result was saved and catch falsely claimed no result returned.'},
         'evidenceBindings':{name:bind(read(name)) for name in ['preregistered-before-tests.json','first-receipt.json','first.log','reader-first-receipt.json','reader-first.log','run_first.py','read_wrapper_once.py']},
         'reviewerSourceBinding':bind(Path(__file__).read_bytes())}
with (HERE/'receipt.json').open('x',encoding='utf8') as stream:json.dump(receipt,stream,indent=2);stream.write('\n')
files={p.name:bind(p.read_bytes()) for p in HERE.iterdir() if p.is_file()}
with (HERE/'index.json').open('x',encoding='utf8') as stream:json.dump({'schema':1,'files':files,'stagedPureTransportAccepted':True,'fullUpstreamIntegrationAccepted':False},stream,indent=2);stream.write('\n')
print(json.dumps({'passed':True,'checks':len(checks),'receipt':bind((HERE/'receipt.json').read_bytes()),'index':bind((HERE/'index.json').read_bytes()),'actualElleCheckerExecuted':False}))
