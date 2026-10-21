"""Read-only source/receipt review, no Clojure process or checker execution."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
SRC=ROOT/'artifacts/elle-result-summary-r2'
def bind(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def read(name):return (SRC/name).read_bytes()
prereg=json.loads(read('preregistered-before-tests.json'));first=json.loads(read('first-receipt.json'));reader=json.loads(read('reader-first-receipt.json'))
expected=prereg['files'];actual={name:bind(read(name)) for name in expected}
assert expected==actual==first['sourceBindingsBefore']==first['sourceBindingsAfter']
assert first['passed'] is True and first['exitCode']==0 and first['actualPureUnitExecuted'] is True
assert first['actualElleCheckerExecuted'] is False and first['actualBatchWrapperCompiled'] is False
assert b'Ran 5 tests containing 16 assertions.' in read('first.log') and b'0 failures, 0 errors.' in read('first.log')
assert b':java "25.0.1"' in read('first.log') and b':clojure "1.12.6"' in read('first.log') and b':actual-elle-checker false' in read('first.log')
assert reader['passed'] is True and reader['exitCode']==0 and reader['sourceBefore']==reader['sourceAfter']==actual['elle_batch.clj']
assert reader['wrapperFormsEvaluated'] is False and reader['actualFullWrapperCompiled'] is False
assert b'{:forms 7, :evaluated false, :actual-elle-checker false}' in read('reader-first.log')
runtime={}
for name,item in first['runtime'].items():
    value=bind((SRC/'runtime'/Path(name).name).read_bytes())
    assert item['expected']==item['actual']==value
    runtime[name]=value
helper=read('result_summary.clj').decode();wrapper=read('elle_batch.clj').decode()
assert '(boolean? original) original' in helper and '(= :unknown original) "unknown"' in helper
assert '"originalValidity" original-typed' in helper and '"cycleSearchTimeout" timeout?' in helper
assert 'cond timeout?' not in helper
issue={'severity':'blocks-complete-wrapper-execution-acceptance','file':'elle_batch.clj',
       'summary':'Raw actual checker result is saved after summary construction; a transport error before spit loses the raw returned result and catch says no checker result returned.',
       'evidence':{'summaryBeforeRawPersistence':wrapper.index('summary (summarize-elle-result result)')<wrapper.index('(spit raw-file'),
                   'catchClaimsNoResult':'"actualElleResultReturned" false' in wrapper},
       'remedy':'Persist raw actual result before conversion and distinguish checker throw from result/transport persistence failure. Freeze a separate revision; leave these tested sources unchanged.'}
assert all(issue['evidence'].values())
receipt={'schema':1,'kind':'independent-AI-short-source-and-pure-test-review','typedSummaryLogicAccepted':True,'sourceBindings':actual,
         'actualPureTestsObserved':5,'actualPureAssertionsObserved':16,'actualPureFailuresObserved':0,'actualJavaVersionObserved':'25.0.1',
         'actualClojureVersionObserved':'1.12.6','actualPureTestRerunByReviewer':False,'actualJvmRerunByReviewer':False,
         'actualElleCheckerExecuted':False,'actual2000InputEvaluationExecuted':False,'fullWrapperFormsReadWithoutEvaluation':7,
         'fixedJava21ElleIntegrationAccepted':False,'fullWrapperReadyForExecutionAccepted':False,'formalPerformanceMeasured':False,
         'runtimeJarBindingsRehashed':runtime,'sourceLogicReview':['Boolean validity preserved independently of partial timeout.',
          ':unknown remains keyword-typed original validity and independent timeout flag.',
          'Unsupported/missing validity maps to execution-error and cannot become a positive result.',
          'Raw upstream result persistence/catch semantics still need the separately listed wrapper fix.'],
         'issues':[issue],'evidenceBindings':{name:bind(read(name)) for name in ['preregistered-before-tests.json','first-receipt.json','first.log','reader-first-receipt.json','reader-first.log','run_first.py','read_wrapper_once.py']},
         'reviewerImportedOrExecutedCandidate':False,'reviewerSourceBinding':bind(Path(__file__).read_bytes())}
with (HERE/'receipt.json').open('x',encoding='utf8') as stream:json.dump(receipt,stream,indent=2);stream.write('\n')
files={p.name:bind(p.read_bytes()) for p in HERE.iterdir() if p.is_file()}
with (HERE/'index.json').open('x',encoding='utf8') as stream:json.dump({'schema':1,'files':files,'typedSummaryAccepted':True,'fullWrapperAccepted':False},stream,indent=2);stream.write('\n')
print(json.dumps({'typedSummaryAccepted':True,'fullWrapperAccepted':False,'issueCount':1,'receipt':bind((HERE/'receipt.json').read_bytes()),'index':bind((HERE/'index.json').read_bytes())}))
