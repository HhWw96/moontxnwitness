"""Preregister thirty paired real HTTP cases. No silent retry or success filtering."""
from pathlib import Path
import argparse,json,os,subprocess,sys,time,urllib.parse
sys.path.insert(0,str(Path(__file__).resolve().parent))
from protocol import COMMITS,SEEDS,encoded,digest,file_digest,new_directory,save_new,workload,validate_plan,relative_file
from verify_evidence import verify
from bounded_process import run_bounded
HERE=Path(__file__).resolve().parent

def preregister(output):
    root=new_directory(output);cases=[]
    for seed in SEEDS:
        case=workload(seed);name=f'case-{seed}.json';binding=save_new(root/name,case)
        cases.append({'seed':seed,'file':name,'sha256':binding['sha256']})
    result={'format':'moontxnwitness-mlflow-http-campaign/v1','commits':COMMITS,'cases':cases,'seeds':list(SEEDS),'pairs':30,'clientRetries':0,'sameMetricRequestsAndTimingPolicyBeforeAfter':True,'actualHttpExecution':False,'actualDatabaseExecution':False}
    save_new(root/'plan.json',result);return root/'plan.json'

def redact(raw,connection_file):
    # Retain complete stream order/length metadata; only configured password byte variants are removed.
    config=json.loads(Path(connection_file).read_text());secret=config.get('password')
    if secret:
        for text in sorted({str(secret),urllib.parse.quote(str(secret),safe=''),urllib.parse.quote_plus(str(secret))},key=len,reverse=True):raw=raw.replace(text.encode(),b'<redacted-connection-password>')
    return raw

def execute_one(case,label,output,*,python,connection_file,upstream_parent,project_root,manifest_path):
    root=new_directory(output);save_new(root/'case.json',case)
    command=[str(python),'-I','-B',str(HERE/'server_worker.py'),'--execute-real-http','--label',label,'--upstream-root',str(Path(upstream_parent)/label),'--manifest',str(manifest_path),'--project-root',str(project_root),'--connection-file',str(connection_file),'--case-file',str(root/'case.json'),'--output',str(root/'server')]
    env={k:v for k,v in os.environ.items() if k.upper() not in ('PYTHONPATH','PYTHONHOME','PYTHONSTARTUP') and not k.upper().startswith(('MLFLOW_','_MLFLOW_','DATABRICKS_','OPENAI_','ANTHROPIC_','AWS_','AZURE_','GOOGLE_','OTEL_'))}
    temp=root/'temp';temp.mkdir();env.update(TEMP=str(temp),TMP=str(temp),TMPDIR=str(temp),PYTHONDONTWRITEBYTECODE='1')
    started=time.monotonic();process=run_bounded(command,env=env,cwd=root,timeout=150)
    code=process['returncode'];stdout=process['stdout'];stderr=process['stderr'];error=process['error'];complete=process['streamsRetainedWithoutTruncation']
    save_new(root/'stdout.sanitized.log',redact(stdout,connection_file),raw=True);save_new(root/'stderr.sanitized.log',redact(stderr,connection_file),raw=True)
    manifest=json.loads(Path(manifest_path).read_bytes());evidence=verify(root/'server',manifest) if (root/'server/receipt.json').exists() else {'valid':False,'reason':'No completed original server evidence'}
    identity_matches=(evidence.get('label')==label and evidence.get('commit')==COMMITS[label]
        and evidence.get('workloadSha256')==digest(encoded(case)))
    if evidence.get('valid') and not identity_matches and error is None:error='child-evidence-identity-does-not-match-request'
    expected_exit=0 if evidence.get('passed') is True else 1
    if evidence.get('valid') and code!=expected_exit and error is None:error='child-exit-inconsistent-with-verified-trial'
    admitted=evidence.get('valid') is True and identity_matches and complete and error is None and process['childStopped'] is True
    result=evidence['result'] if admitted else {'executionComplete':False,'faultPredicate':False,'predicateDisposition':'unknown'}
    predicate_pass=(result.get('faultPredicate') is True if label=='before' else evidence.get('fixedBehaviorChecked') is True)
    record={'format':'moontxnwitness-mlflow-http-trial/v1','label':label,'seed':case['seed'],'caseSha256':digest(encoded(case)),'exitCode':code,'error':error,'elapsedSeconds':time.monotonic()-started,'stdoutOriginalBytes':process['stdoutOriginalBytes'],'stderrOriginalBytes':process['stderrOriginalBytes'],'stdoutRetainedBytes':len(stdout),'stderrRetainedBytes':len(stderr),'childStopped':process['childStopped'],'passed':bool(admitted and evidence['passed'] is True and predicate_pass),'evidenceIdentityMatchesRequest':identity_matches,'streamsRetainedWithoutTruncation':complete,'passwordBytesSanitized':True,'evidenceVerification':evidence,'result':result,'automaticRetry':False,'realChildCommandExecuted':True,'isolationViolationClaim':False,'G2Claim':False}
    save_new(root/'PROCESS.json',record);return record

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True);s=sub.add_parser('prepare-plan');s.add_argument('--output',type=Path,required=True)
    r=sub.add_parser('run');r.add_argument('--execute-real-http',action='store_true');r.add_argument('--plan',type=Path,required=True);r.add_argument('--connection-file',type=Path,required=True);r.add_argument('--upstream-parent',type=Path,required=True);r.add_argument('--project-root',type=Path,required=True);r.add_argument('--output',type=Path,required=True);r.add_argument('--python-before',type=Path,default=Path(sys.executable));r.add_argument('--python-fixed',type=Path,default=Path(sys.executable));r.add_argument('--manifest',type=Path,default=HERE/'upstream-manifest.json')
    a=p.parse_args()
    if a.command=='prepare-plan':print(json.dumps({'plan':str(preregister(a.output)),'actualHttpExecution':False}));return 0
    if not a.execute_real_http:raise ValueError('Explicit real-service execution flag required')
    plan=json.loads(a.plan.read_bytes())
    validate_plan(plan)
    root=new_directory(a.output);save_new(root/'original-plan.json',a.plan.read_bytes(),raw=True);results=[]
    for row in plan['cases']:
        raw=relative_file(a.plan.parent,row['file']).read_bytes()
        if digest(raw)!=row['sha256']:raise ValueError('Frozen case changed')
        case=json.loads(raw)
        if case!=workload(row['seed']):raise ValueError('Campaign requests differ from preregistration')
        for label in COMMITS:
            trial=execute_one(case,label,root/(str(row['seed'])+'-'+label),python=getattr(a,'python_'+label),connection_file=a.connection_file,upstream_parent=a.upstream_parent,project_root=a.project_root,manifest_path=a.manifest)
            results.append({'label':label,'seed':row['seed'],'passed':trial['passed'],'result':trial['result'],'processSha256':file_digest(root/(str(row['seed'])+'-'+label)/'PROCESS.json')})
    passed=len(results)==2*len(SEEDS) and all(row['passed'] is True and row['result'].get('executionComplete') is True and (row['result'].get('faultPredicate') is True if row['label']=='before' else bool(row['result'].get('httpStatusByWorker')) and all(value==200 for value in row['result']['httpStatusByWorker'].values())) for row in results)
    save_new(root/'RESULT.json',{'passed':passed,'preregisteredSeeds':30,'actualTrialsAttempted':len(results),'results':results,'scope':'Native frozen MLflow HTTP service paired experiment; not a database isolation certification','formalPerformanceMeasured':False,'automaticRetry':False})
    return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())