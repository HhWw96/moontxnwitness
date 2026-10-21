"""Complete only fresh-root placement preflight rejected in the first audit.
No product, expectation, database, build, workflow, or passed runtime is rerun.
"""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,shutil,subprocess
ROOT=Path(__file__).resolve().parents[2]
WORK=Path(r'D:/CodexScratch/MoonTxnWitness-v3-public-8f5d51a-20261021/final-audit-work')
SHA=lambda b:hashlib.sha256(b).hexdigest()
LOAD=lambda p:json.loads(p.read_bytes())
def save(p,x):
 raw=(json.dumps(x,indent=2)+'\n').encode();p.parent.mkdir(parents=True,exist_ok=True);p.open('xb').write(raw);return {'file':str(p),'bytes':len(raw),'sha256':SHA(raw)}
first_path=ROOT/'verification/v3/independent-public-checkpoint-8f5d51a-2026-10-21T08-16-42.759797Z.json'
assert SHA(first_path.read_bytes())=='9cda388fab69387229178f64f8917ef587e3bc22ec9f27bfc1e45f78e7b85ac9'
first=LOAD(first_path);assert not first['passed'] and first['static']
result={'schema':1,'scope':'Independent AI acceptance of public development checkpoint actual downloaded bytes; supplemental fresh-root placement correction',
'sourceCommit':first['sourceCommit'],'independentAIAcceptance':True,'humanAcceptance':False,'stableReleasePublished':False,'fullApplicationIntegration':False,
'localDatabaseExecution':False,'localBuild':False,'authorRuntimeOrCacheUsed':False,'complete':False,'passed':False,
'firstFailure':{'file':first_path.relative_to(ROOT).as_posix(),'sha256':SHA(first_path.read_bytes()),'preserved':True},
'correction':{'kind':'independent-audit-invocation-input-placement','description':'The downloaded MLflow auditor requires evidence paths under its fresh ROOT. Initial invocation passed the sibling artifact directory and was rejected before any of its 24 checks. Copying exactly the downloaded evidence into a new child directory satisfies this existing path contract. Product and frozen expectations are unchanged.','productionChanged':False,'passedChecksRerun':False},
'auditScriptSha256':SHA(Path(__file__).read_bytes()),'static':first['static'],'fresh':[]}
try:
 original=WORK/'artifact-postgres/verification/faults/mlflow/ci'
 for os_name in ('ubuntu-24.04','windows-2022'):
  fresh=WORK/('fresh-'+os_name);prior=LOAD(fresh/'mlflow-independent-process.json');assert prior['exitCode']==1
  prior_stdout=json.loads(prior['stdout'].strip().splitlines()[-1]);assert prior_stdout['checks']==0 and not prior_stdout['complete']
  runtime=LOAD(fresh/'audit-output/fresh-result.json');assert runtime['passed'] and runtime['checks']==332 and all(c['passed'] for c in runtime['cases'])
  destination=fresh/'verification/faults/mlflow/downloaded-public-ci';shutil.copytree(original,destination)
  bindings=[]
  for path in sorted(original.rglob('*')):
   if path.is_file():
    rel=path.relative_to(original);raw=path.read_bytes();assert (destination/rel).read_bytes()==raw;bindings.append({'file':str(rel).replace('\\','/'),'bytes':len(raw),'sha256':SHA(raw)})
  process=subprocess.run([os.environ.get('MTW_PYTHON') or os.environ.get('PYTHON') or 'python','-B','verification/v3/tools/mlflow_execution_audit.py','--database',str(destination)],cwd=fresh,capture_output=True,text=True,encoding='utf8',errors='replace',timeout=120)
  saved=save(fresh/'mlflow-independent-placement-corrected-process.json',{'exitCode':process.returncode,'stdout':process.stdout,'stderr':process.stderr,'copiedEvidenceBindings':bindings})
  assert process.returncode==0,process.stdout[-1000:]
  summary=json.loads(process.stdout.strip().splitlines()[-1]);assert summary['passed'] and summary['complete'] and summary['checks']==24
  assert SHA((fresh/summary['receipt']).read_bytes())==summary['sha256']
  result['fresh'].append({'artifactOrigin':os_name,'passed':True,'runtimeChecks':332,'runtimeResultSha256':SHA((fresh/'audit-output/fresh-result.json').read_bytes()),
   'journalProcessSha256':SHA((fresh/'journal-process.json').read_bytes()),'mlflowAdditionalIndependentChecks':24,'mlflowReceipt':summary['receipt'],'mlflowReceiptSha256':summary['sha256'],
   'correctedProcessSha256':saved['sha256'],'evidenceFilesCopied':len(bindings),'evidenceCopyBindingsSha256':SHA(json.dumps(bindings,sort_keys=True).encode()),
   'actualCoreSha256':SHA((fresh/'dist/core.mjs').read_bytes()),'actualCaptureCoreSha256':SHA((fresh/'dist/capture-core.mjs').read_bytes()),'localDatabaseExecution':False,'localBuild':False,'authorRuntimeOrCacheUsed':False})
  print(json.dumps({'progress':'fresh-supplement-complete','artifactOrigin':os_name,'priorRuntimeChecks':332,'additionalChecks':24,'passed':True}),flush=True)
 result['complete']=True;result['passed']=len(result['fresh'])==2
except Exception as e:result['errorClass']=type(e).__name__;result['error']=str(e).replace(str(ROOT),'<workspace>')
result['limitations']=first['limitations']+['Generated source/portable package ZIP files were not uploaded as CI artifacts; downloaded acceptance covers actual runtime bytes and public repository source, with packaging receipts independently checked.','Formal regression passed, while final RSS/search/reduction performance targets remain unfulfilled; this is not a stable release gate.']
result['transportAuditSha256']=first['transportAuditSha256'];result['workflowRuns']=first['workflowRuns'];result['downloadedFiles']=first['downloadedFiles'];result['retainedRawDirectory']=str(WORK);result['finishedAt']=datetime.now(timezone.utc).isoformat()
stamp=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H-%M-%S-%fZ');p=ROOT/'verification/v3'/('independent-public-checkpoint-8f5d51a-completed-'+stamp+'.json');binding=save(p,result)
print(json.dumps({'passed':result['passed'],'complete':result['complete'],'receipt':p.relative_to(ROOT).as_posix(),'sha256':binding['sha256'],'error':result.get('error')}),flush=True)
raise SystemExit(0 if result['passed'] else 1)
