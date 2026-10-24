"""One future fixed40x50 Elle/public027 comparison. No import-time execution."""
from pathlib import Path
import argparse,contextlib,hashlib,json,os,re,signal,subprocess,sys,time,traceback,zipfile,stat
APP='experiments/elle/v028';BRANCH='experiment/elle-v028-campaign';PARENT='947719688dbcd96213283499747b38b3ccfe6fde';REPO='HhWw96/moontxnwitness'
BASE_SHA='d8bff60353abe61720f3d6345c84154ae9bad60b17076bf891fea278b5af42e2';SMOKE_MANIFEST='eed9fb7fad2397d0f7273a191b576c6e93164ed10882445826ba319313c5f7fb';CAMPAIGN_SHA='24ebfd4e0a483ec06b0fcd29273a39456be0da40058f953ae48a9e2ba2cfebcb';COLLECTOR_SHA='3febadd965e18fd3f653fead261e121ce8bc1a88b34ec659b18dbea0646cbd06'
DATASET='verification/experimental-candidates/elle-expansion-generation-v2-2026-10-21/actual-ci-39606834359/inputs.jsonl';DATASET_SHA='4b7ef85eb4a2f4a74020d6e6c65f5345f7c4c3b576afbe02b3f7a0cfc6033507'
OUT_LITERAL='/home/runner/work/_temp/mtw-elle-v028-campaign-first';RUNTIME_ZIP='/home/runner/work/_temp/mtw-elle-v028-campaign-runtime.original.zip';PUBLIC_ZIP='/home/runner/work/_temp/mtw-elle-v028-campaign-public027.original.zip'
NEW_FILES=frozenset(('.github/workflows/elle-v028-campaign.yml',*[APP+'/'+n for n in ('hosted_campaign.py','campaign-sdk-worker.mjs','campaign-stage.json','campaign-source-manifest.json','campaign-public-dist-manifest.json','campaign-evidence/original-eight-review.json','campaign-evidence/public027-publication.original.json','campaign-evidence/public027-independent-review.json')]))
BUDGETS={'wallSeconds':18000,'ownedOutputBytes':2147483648,'SDKBatchSeconds':300,'SDKBatchBytes':67108864,'SDKStreamBytes':8388608,'runtimeForensicBytes':16777216,'runtimeForensicFileBytes':1048576,'runtimeForensicFiles':64}
class CampaignCancelled(Exception):pass

def need(v,m):
 if not v:raise ValueError(m)
def sha(b):return hashlib.sha256(b).hexdigest()
def decode(b):
 def unique(pairs):
  d={}
  for k,v in pairs:need(k not in d,'duplicate JSON key');d[k]=v
  return d
 return json.loads(b,object_pairs_hook=unique)
def binding(p):
 h=hashlib.sha256();n=0
 with Path(p).open('rb') as f:
  while b:=f.read(65536):h.update(b);n+=len(b)
 return {'bytes':n,'sha256':h.hexdigest()}
def write_new(p,obj):
 raw=obj if isinstance(obj,bytes) else (json.dumps(obj,sort_keys=True,ensure_ascii=True,indent=2)+'\n').encode()
 with Path(p).open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
def load_base(project):
 p=project/APP/'hosted_smoke.py';raw=p.read_bytes();need(sha(raw)==BASE_SHA,'exact reviewed fix2 helper');ns={'__name__':'fixed_campaign_runtime_primitives','__file__':str(p),'__verified_source_sha256__':BASE_SHA};exec(compile(raw,str(p),'exec'),ns);return ns

def validate_stage(stage):
 need(stage['schema']==1 and stage['stage']=='fixed2000-common-serializable-comparison-preparation' and stage['branch']==BRANCH and stage['parent']==PARENT,'fixed campaign stage')
 need(stage['rootFutureCampaignExecutionAuthorized'] is True and stage['rootFuturePublicSDKComparisonAuthorized'] is True,'explicit root future comparison authorization')
 for k in ('sourceReviewPassed','readyForHostedCampaign','actual2000Executed','actualSDKExecuted','actualSmokeAcceptedFor2000','rulesOrInputsMayChange'):need(stage[k] is False,'prepared stage cannot manufacture '+k)
 need(stage['actualAgreementCount']==0 and stage['automaticRetry'] is False,'prepared no results or retries')
 need(stage['runtimeAdmissionSha256']=='4381947aa2266616061d161f38e9b143818763d2a69a04e7199651e5853e805d','original runtime admission')

def validate_dataset(raw,campaign,plans):
 need(sha(raw)==DATASET_SHA and len(raw)==5940749,'original2000 dataset bytes');lines=raw.splitlines();need(len(lines)==2000 and raw.endswith(b'\n'),'original2000 complete JSONL');rows=[decode(l) for l in lines];seen=set()
 for i,row in enumerate(rows):
  expected=('register-'+str(i)) if i<1000 else ('list-'+str(i));model='point-register-v1' if i<1000 else 'append-list-v1'
  need(row['id']==expected and row['id'] not in seen and row['input']['dataModel']==model and row['input']['traceSchema']==3,'fixed ordered actual two-model scope');seen.add(row['id'])
  canonical=json.dumps(row['input'],sort_keys=True,separators=(',',':'),ensure_ascii=True).encode();need(sha(canonical)==row['inputSha256'],'original input semantic hash')
 flat=[c for plan in plans for c in plan['cases']];need(flat==[{'id':r['id'],'inputSha256':r['inputSha256']} for r in rows],'40x50 plans cover exact original2000 order')
 need(len(campaign['batches'])==40 and all(len(p['cases'])==50 and p['expectedTruthSupplied'] is False and p['inferredVersionOrderSupplied'] is False and p['originalRulesChanged'] is False for p in plans),'unchanged source conversion and checker input facts')
 return rows

def source_check(project,pin,env,base):
 manifest_raw=(project/APP/'campaign-source-manifest.json').read_bytes();need(sha(manifest_raw)==pin,'external campaign manifest pin');doc=decode(manifest_raw)
 need(doc['parent']==PARENT and doc['branch']==BRANCH and doc['budgets']==BUDGETS and doc['originalCampaignSha256']==CAMPAIGN_SHA and doc['originalCollectorSha256']==COLLECTOR_SHA,'fixed campaign source scope')
 expected=NEW_FILES-{'.github/workflows/elle-v028-campaign.yml',APP+'/campaign-source-manifest.json'};need(set(doc['files'])==expected,'exact new code/stage/evidence closure')
 for name,lock in doc['files'].items():base['plain'](project/base['relative'](name));need(binding(project/name)==lock,'campaign source changed '+name)
 head=base['read_git'](project,'rev-parse','HEAD').decode().strip();parents=base['read_git'](project,'rev-list','--parents','-n','1','HEAD').decode().strip().split();changed=base['parse_changes'](base['read_git'](project,'diff-tree','--no-commit-id','--name-status','-r','-z',PARENT,'HEAD'));status=base['read_git'](project,'status','--porcelain=v1','--untracked-files=all')
 need(env.get('GITHUB_ACTIONS')=='true' and env.get('RUNNER_OS')=='Linux' and env.get('GITHUB_REPOSITORY')==REPO and env.get('GITHUB_EVENT_NAME')=='push' and env.get('GITHUB_REF')=='refs/heads/'+BRANCH,'dedicated actual hosted push')
 need(re.fullmatch('[0-9a-f]{40}',head) and env.get('GITHUB_SHA')==head and parents==[head,PARENT] and changed=={n:'A' for n in NEW_FILES} and status==b'','single exact parent/exact new sources/clean checkout')
 need(env.get('GITHUB_RUN_ATTEMPT')=='1' and re.fullmatch('[1-9][0-9]*',env.get('GITHUB_RUN_ID','')),'first actual run only');event_path=Path(env['GITHUB_EVENT_PATH']);base['plain'](event_path);event_raw=event_path.read_bytes();event=decode(event_raw)
 need(event['ref']==env['GITHUB_REF'] and event['after']==event['head_commit']['id']==head and event['repository']['full_name']==REPO,'raw push context')
 for n in NEW_FILES:need((project/n).read_bytes()==base['read_git'](project,'show','HEAD:'+n),'actual source blob differs')
 validate_stage(decode((project/APP/'campaign-stage.json').read_bytes()))
 public=decode((project/APP/'campaign-public-dist-manifest.json').read_bytes());need(public['version']=='0.2.7' and public['sourceCommit']=='c10b06c5bfcabd1f40b0ff0099717072a816ec74' and public['archiveBytes']==49656319 and public['archiveSha256']=='4de093877bd75d55e327c5015484aead587e5be59bd22818d035c0fed4298c3d' and public['url']=='https://github.com/HhWw96/moontxnwitness/releases/download/v0.2.7/MoonTxnWitness-v0.2.7-portable.zip' and public['distPrefix']=='MoonTxnWitness-v0.2.7/dist/' and public['entryPoint']=='sdk.mjs' and len(public['files'])==102,'fixed anonymous public027 top-level dist source')
 # Same original106 + original53 R4 + admission + original8 source closure; never call smoke main.
 base['validate_sources'](project,(project/APP/'smoke-execution-source-manifest.json').read_bytes(),SMOKE_MANIFEST)
 review_raw=(project/APP/'campaign-evidence/original-eight-review.json').read_bytes();need(sha(review_raw)=='76d881a31f418009219ea7d843c10e606f0aca2b472ba016009e7040fed66f30','original independent8 review');review=decode(review_raw)
 need(review['evidenceReviewPassed'] is True and review['overallHostedSmokeTransportPassed'] is True and review['sourceCommit']==PARENT and review['actualEightFacts']['returned']==8 and review['actualEightFacts']['comparisonEligible']==6 and review['actualEightFacts']['unknown']==2 and review['actual2000Executed'] is False and review['actualSDKExecuted'] is False,'actual8 evidence scope; not prior2000 or SDK agreement')
 r4=project/APP/'r4';campaign=decode(base['pinned'](r4/'campaign-plan-final2.json',CAMPAIGN_SHA));base['pinned'](r4/'collect_campaign.py',COLLECTOR_SHA);plans=[]
 for i,b in enumerate(campaign['batches']):
  need(b['name']=='batch-'+str(i).zfill(3) and b['outputDirectory']=='actual-outputs/'+b['name'],'fixed40 output enumeration');p=decode(base['pinned'](r4/b['planPath'],b['planSha256']));base['pinned'](project/base['relative'](p['batchPath']),p['batchSha256'],8388608);plans.append(p)
 rows=validate_dataset((project/DATASET).read_bytes(),campaign,plans)
 return {'head':head,'parent':PARENT,'branch':BRANCH,'runId':env['GITHUB_RUN_ID'],'attempt':1,'manifestSha256':pin,'rawEventSha256':sha(event_raw),'original106And53R4Unchanged':True,'actualNewSources':{n:binding(project/n) for n in sorted(NEW_FILES)}},doc,campaign,plans,rows

def extract_public(archive,dest,manifest,base):
 need(binding(archive)=={'bytes':manifest['archiveBytes'],'sha256':manifest['archiveSha256']},'anonymous public portable whole bytes');need(not dest.exists(),'fresh public dist only')
 with zipfile.ZipFile(archive) as z:
  infos=z.infolist();need(len(infos)==manifest['archiveMembers'] and sum(i.file_size for i in infos)==manifest['archiveLogicalBytes'],'public portable exact archive structure');seen=set()
  for i in infos:
   name=i.filename[:-1] if i.is_dir() else i.filename;base['relative'](name);need(i.orig_filename==i.filename and name.casefold() not in seen,'public archive alias');seen.add(name.casefold());mode=stat.S_IFMT(i.external_attr>>16);need(mode in (0,stat.S_IFREG,stat.S_IFDIR) and not i.external_attr&0x400 and not i.flag_bits&1,'public archive plain members');need(i.compress_type in (0,8),'public archive compression')
  prefix=manifest['distPrefix'];selected={i.filename[len(prefix):]:i for i in infos if not i.is_dir() and i.filename.startswith(prefix)};need(len(selected)==102 and set(selected)=={f['path'] for f in manifest['files']} and manifest['entryPoint']=='sdk.mjs','exact public top-level102 dist')
  dest.mkdir()
  for f in manifest['files']:
   name=base['relative'](f['path']);raw=z.read(selected[name]);need({'bytes':len(raw),'sha256':sha(raw)}=={k:f[k] for k in ('bytes','sha256')},'original public dist bytes');p=dest/name;p.parent.mkdir(parents=True,exist_ok=True);write_new(p,raw)
 audit_public(dest,manifest,base)

def audit_public(dest,manifest,base):
 actual=base['closure'](dest)['files'];need(actual=={f['path']:{k:f[k] for k in ('bytes','sha256')} for f in manifest['files']},'complete immutable public102 runtime closure')

@contextlib.contextmanager
def cancellation_scope():
 old={s:signal.getsignal(s) for s in (signal.SIGINT,signal.SIGTERM)}
 def cancelled(signum,frame):raise CampaignCancelled('campaign cancelled; original owned-group kill/wait cleanup')
 try:
  for s in old:signal.signal(s,cancelled)
  yield
 finally:
  for s,h in old.items():signal.signal(s,h)

def checkpoint(output,started,core):
 need(time.monotonic()-started+BUDGETS['SDKBatchSeconds']<=BUDGETS['wallSeconds'],'campaign wall budget reserves a full fixed batch timeout');used=sum(p.stat().st_size for p in output.rglob('*') if p.is_file());need(used<=BUDGETS['ownedOutputBytes'],'owned campaign output budget');gate=core['linux_resources'](output);need(gate['passed'],'original1.2GiB/2GiB resource gate');return {'elapsedSeconds':time.monotonic()-started,'ownedOutputBytes':used,'originalResourceGate':gate}

def bounded_forensics(root,dest,base,initial,observed=None):
 """Strict failure remains failure; retain bounded raw prefixes and honest file state."""
 dest.mkdir();entries=[];total=0;count=0;skipped=0;truncated=False
 try:base['plain'](root);need(root.is_dir(),'runtime root is not a plain existing directory')
 except Exception as e:
  write_new(dest/'INDEX.json',{'rootReadStatus':'refused-or-missing','error':str(e),'retainedBytes':0,'unexpectedRuntimeStillRejected':True});return
 for parent,dirs,files in os.walk(root,followlinks=False):
  dirs.sort();files.sort()
  for name in list(dirs):
   p=Path(parent)/name
   try:base['plain'](p)
   except Exception as e:entries.append({'path':p.relative_to(root).as_posix(),'readStatus':'refused-link-or-reparse','error':str(e)});dirs.remove(name)
  for name in files:
   p=Path(parent)/name;relative=p.relative_to(root).as_posix()
   try:
    base['plain'](p);current=(observed or {}).get(relative) if observed is not None else binding(p)
    if relative in initial['files'] and current==initial['files'][relative]:skipped+=1;continue
   except Exception:pass
   if len(entries)>=256:truncated=True;break
   entry={'path':relative,'retainedBytes':0,'complete':False};entries.append(entry)
   if count>=BUDGETS['runtimeForensicFiles'] or total>=BUDGETS['runtimeForensicBytes']:entry['readStatus']='budget-not-read';continue
   try:
    base['plain'](p);need(p.is_file(),'plain forensic file');size=p.stat().st_size;cap=min(size,BUDGETS['runtimeForensicFileBytes'],BUDGETS['runtimeForensicBytes']-total)
    with p.open('rb') as f:raw=f.read(cap)
    target=dest/(str(count).zfill(3)+'.original-prefix.bin');count+=1;write_new(target,raw);total+=len(raw);entry.update(observedFileBytes=size,retainedBytes=len(raw),complete=len(raw)==size,retained=target.name,retainedSha256=sha(raw),readStatus='written-original-bytes')
   except Exception as e:entry.update(readStatus='failed',error=str(e))
 write_new(dest/'INDEX.json',{'entries':entries,'unchangedOriginalFilesSkipped':skipped,'entryMetadataTruncated':truncated,'retainedBytes':total,'limits':{k:BUDGETS[k] for k in ('runtimeForensicBytes','runtimeForensicFileBytes','runtimeForensicFiles')},'unexpectedRuntimeStillRejected':True})

def runtime_audit(base,initial,root,evidence):
 evidence.mkdir();primary=None;after=None
 try:
  after=base['closure'](root);write_new(evidence/'RUNTIME-AFTER.json',after);delta=base['validate_runtime_delta'](initial,after);write_new(evidence/'RUNTIME-DELTA.json',delta);base['retain_generated_runtime_files'](root,evidence,delta);need(base['closure'](root)==after,'runtime changed while retaining raw class evidence');return after
 except BaseException as e:
  primary=e
  try:bounded_forensics(root,evidence/'unexpected-runtime-original-bytes',base,initial,None if after is None else after['files'])
  except Exception as diagnostic:e.add_note('bounded runtime forensic persistence failed: '+repr(diagnostic))
  raise

def report_class(input,report,verification):
 def mapping(v):return v if isinstance(v,dict) else {}
 report=mapping(report);verification=mapping(verification);execution=mapping(report.get('execution'));evidence=mapping(report.get('evidence'));reasons=[mapping(execution.get('metrics')).get('reason'),mapping(evidence.get('metrics')).get('reason'),evidence.get('reason')];reason=next((v for v in reasons if v is not None),None);status=report.get('status');model={'point-register-v1':'register-serializable-v1','append-list-v1':'append-list-serializable-v1'}.get(input['dataModel']);qualified=verification.get('valid') is True and report.get('schemaVersion')==3 and report.get('version')=='0.2.7' and report.get('tool')=='MoonTxnWitness' and mapping(report.get('modelDefinition')).get('id')==model and mapping(report.get('coverage')).get('complete') is True
 category='unknown';boolean=None
 if verification.get('valid') is not True:category='verification-failure'
 elif status=='invalid':category='invalid'
 elif status in ('consistent','violation'):category=status if qualified else 'unqualified-'+status;boolean=(status=='consistent') if qualified else None
 elif status=='inconclusive':category='budget' if isinstance(reason,str) and re.search('budget|capacity|limit',reason) else 'unknown'
 return {'status':status,'reason':reason,'category':category,'comparisonBoolean':boolean,'comparisonEligible':type(boolean) is bool,'modelDefinition':report.get('modelDefinition'),'coverageComplete':mapping(report.get('coverage')).get('complete') is True}

def collect_sdk(output,rows,batches,base):
 allrows=[];byid={r['id']:r for r in rows}
 for batch in batches:
  work=output/'sdk'/batch['name'];expected=rows[int(batch['name'][-3:])*50:(int(batch['name'][-3:])+1)*50];states={r['id']:[] for r in expected};process=None;issues=[]
  if (work/'process.json').exists():
   try:
    need((work/'process.json').stat().st_size<=1048576,'SDK process receipt budget');process=decode((work/'process.json').read_bytes());need(isinstance(process,dict),'SDK process receipt object')
   except Exception as e:process=None;issues.append({'class':type(e).__name__,'error':str(e)})
  ledger=work/'case-results/ledger.jsonl';previous='0'*64;sequence=0;lastOrdinal=0
  try:
   if ledger.exists():
    need(ledger.stat().st_size<=8388608,'SDK ledger budget')
    with ledger.open('rb') as stream:
     for raw in stream:
      need(raw.endswith(b'\n') and len(raw)<=1048576,'complete bounded SDK ledger frame');e=decode(raw);body=e['body'].encode();b=decode(body);sequence+=1;need(e['bodySha256']==sha(body) and e['previousSha256']==previous and b['sequence']==sequence,'SDK ledger chain');previous=sha(body);need(b['id'] in states and b['inputSha256']==byid[b['id']]['inputSha256'],'SDK ledger original identity');ordinal=next(i for i,r in enumerate(expected) if r['id']==b['id']);need(ordinal>=lastOrdinal and ordinal<=lastOrdinal+1,'SDK case order');need(ordinal==lastOrdinal or states[expected[lastOrdinal]['id']][-1]['phase']=='completed','SDK prior case incomplete');lastOrdinal=ordinal;states[b['id']].append(b)
   for original in expected:
    events=states[original['id']];phases=[e['phase'] for e in events];allowed=['analysis-intent','report-retained','verification-intent','verification-retained','completed'];prefix=phases[:-1] if phases[-1:]==['failure'] else phases;need(prefix==allowed[:len(prefix)] and len(prefix)<=5,'SDK durable phase order')
  except Exception as e:issues.append({'class':type(e).__name__,'error':str(e)})
  try:
   if process is not None:
    for name,lock in process.get('logBindings',{}).items():need(name in ('stdout.raw','stderr.raw') and binding(work/name)==lock and (work/name).stat().st_size<=BUDGETS['SDKStreamBytes'],'SDK original stream binding')
   if process is not None and process.get('exitCode')==0 and process.get('stopReason') is None:
    receipt=decode((work/'case-results/receipt.json').read_bytes());need(receipt['passed'] is True and receipt['requested']==receipt['completed']==50 and receipt['ledger']==binding(ledger) and receipt['lastBodySha256']==previous and all([e['phase'] for e in states[r['id']]]==['analysis-intent','report-retained','verification-intent','verification-retained','completed'] for r in expected),'SDK successful receipt and all fifty durable completions')
  except Exception as e:issues.append({'class':type(e).__name__,'error':str(e)})
  processOK=not issues and process is not None and process.get('exitCode')==0 and process.get('stopReason') is None and not process.get('rawStreamsMayBeTruncated') and not process.get('controllerErrors')
  for original in expected:
   case={'id':original['id'],'inputSha256':original['inputSha256'],'actualAnalysisResultReturned':False,'actualVerificationReturned':False,'comparisonEligible':False,'comparisonBoolean':None,'category':'not-invoked','phaseEvidence':states[original['id']],'processSucceeded':processOK,'processFailureCategory':None if processOK else ('timeout' if (process or {}).get('stopReason')=='process-timeout' else 'budget' if 'budget' in str((process or {}).get('stopReason')) else 'execution-failure' if work.exists() else 'not-invoked')}
   try:
    need(not issues,'SDK ledger integrity failure');events={e['phase']:e for e in states[original['id']]};root=work/'case-results'
    if 'analysis-intent' in events:
     case['category']='execution-failure';inputRaw=(root/(original['id']+'.input.json')).read_bytes();need(sha(inputRaw)==original['inputSha256'] and decode(inputRaw)==original['input'],'SDK retained exact original input')
    if 'report-retained' in events:
     p=root/(original['id']+'.report.json');need(binding(p)==events['report-retained']['report'] and p.stat().st_size<=33554432,'SDK full report digest');case.update(actualAnalysisResultReturned=True,report={'path':str(p),**binding(p)})
    if 'verification-retained' in events:
     p=root/(original['id']+'.verification.json');need(binding(p)==events['verification-retained']['verification'] and p.stat().st_size<=1048576,'SDK verification digest');case.update(actualVerificationReturned=True,verification={'path':str(p),**binding(p)})
    if 'verification-retained' in events and 'report-retained' in events:
     report=decode(Path(case['report']['path']).read_bytes());verify=decode(Path(case['verification']['path']).read_bytes());classification=report_class(original['input'],report,verify);
     if 'completed' in events:need(classification==events['completed']['classification'],'SDK classification from complete retained report')
     case.update(classification);case['comparisonEligible']=case['comparisonEligible'] and processOK and 'completed' in events
    if not processOK and case['category']=='not-invoked' and work.exists():case['category']='not-invoked-after-batch-failure'
   except Exception as e:case.update(comparisonEligible=False,category='evidence-integrity-failure',error=str(e))
   allrows.append(case)
 return {'schema':1,'kind':'public027-fixed2000-SDK-retained-evidence','cases':allrows,'inputsAccounted':len(allrows),'actualAnalysisResultsReturned':sum(r['actualAnalysisResultReturned'] for r in allrows),'actualVerificationsReturned':sum(r['actualVerificationReturned'] for r in allrows),'actualSDKExecuted':any(r['actualAnalysisResultReturned'] for r in allrows),'notInvokedNeverCompleted':True}

def compare_cases(elle,sdk,rows):
 need(len(elle['cases'])==len(sdk['cases'])==2000,'complete2000 accounting');results=[];counts={};differences=[]
 for ordinal,(original,e,m) in enumerate(zip(rows,elle['cases'],sdk['cases'])):
  need((e['id'],e['inputSha256'])==(m['id'],m['inputSha256'])==(original['id'],original['inputSha256']),'comparison original facts and identity')
  eligible=e.get('comparisonEligible') is True and e.get('cycleSearchTimeout') is not True and e['status'] in ('returned-true','returned-false') and (e.get('originalValidity') or {}).get('kind')=='boolean' and type(e['originalValidity'].get('value')) is bool and m.get('comparisonEligible') is True and type(m.get('comparisonBoolean')) is bool
  outcome=('agree' if e['originalValidity']['value']==m['comparisonBoolean'] else 'different') if eligible else 'not-compared'
  row={'id':original['id'],'inputSha256':original['inputSha256'],'inputDataModel':original['input']['dataModel'],'comparison':outcome,'originalInputReference':'INPUTS.original.jsonl:'+str(ordinal+1),'ElleEvidence':{'batch':'batch-'+str(ordinal//50).zfill(3),'raw':'elle/actual-outputs/batch-'+str(ordinal//50).zfill(3)+'/raw/'+original['id']+'.edn','summary':'elle/actual-outputs/batch-'+str(ordinal//50).zfill(3)+'/summaries/'+original['id']+'.json'},'notComparedReasons':[] if eligible else ['Elle:'+e['status'],'SDK:'+m.get('category','unknown'),'SDK-process:'+str(m.get('processFailureCategory'))],'ElleStatus':e['status'],'ElleOriginalValidity':e.get('originalValidity'),'ElleComparisonEligible':e.get('comparisonEligible',False),'SDK':m,'scope':'fixed shared serializable point-register/append-list facts only; no expected truth, inferred version order or six-model claim'}
  if outcome=='different':row['explanation']='Original retained Elle serializable boolean and independently verified public027 corresponding-model status disagree on these fixed facts. This is observed disagreement, not a truth assignment; inspect both full raw results, source mapping and original input.';differences.append(row)
  counts[outcome]=counts.get(outcome,0)+1;results.append(row)
 elleCounts={};sdkCounts={};processCounts={}
 for row in results:
  elleCounts[row['ElleStatus']]=elleCounts.get(row['ElleStatus'],0)+1;sdkCounts[row['SDK']['category']]=sdkCounts.get(row['SDK']['category'],0)+1;k=str(row['SDK'].get('processFailureCategory'));processCounts[k]=processCounts.get(k,0)+1
 return {'schema':1,'kind':'fixed2000-common-serializable-observed-comparison','ElleStatuses':elleCounts,'SDKCategories':sdkCounts,'SDKProcessFailureCategories':processCounts,'cases':results,'counts':counts,'differences':differences,'allDifferencesPreserved':True,'agreementRequiredForCompletion':False,'actualAgreementCount':counts.get('agree',0),'actualDifferenceCount':counts.get('different',0),'actualSDKExecuted':sdk['actualSDKExecuted'],'actual2000Executed':elle.get('fullCampaignTransportComplete') is True and sdk['actualAnalysisResultsReturned']==sdk['actualVerificationsReturned']==2000,'semanticTruthOrFullProductClassificationClaimed':False}

def run_sdk_batch(project,output,batch,rows,manifest,manifestPin,public,base,core):
 work=output/'sdk'/batch['name'];work.mkdir();job={'rows':[{'id':r['id'],'inputSha256':r['inputSha256'],'input':r['input']} for r in rows],'owner':str(output),'output':str(work/'case-results'),'publicDist':str(public),'publicManifest':str(project/APP/'campaign-public-dist-manifest.json'),'publicManifestSha256':manifestPin};raw=(json.dumps(job,sort_keys=True,separators=(',',':'))+'\n').encode();write_new(work/'job.json',raw);audit_public(public,manifest,base);process=None;primary=None
 try:
  env={k:v for k,v in os.environ.items() if not any(t in k.upper() for t in ('TOKEN','SECRET','PASSWORD','AUTHORIZATION','PRIVATE_KEY')) and k not in ('NODE_OPTIONS','NODE_PATH','CLASSPATH','JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS','PYTHONPATH')};env.update(HOME=str(work),TMPDIR=str(work),TMP=str(work),TEMP=str(work),MOONTXN_ELLE_CAMPAIGN_SDK='1',TZ='UTC',LANG='C.UTF-8')
  node=Path(os.environ['CAMPAIGN_NODE']);need(node.is_absolute() and node.is_file(),'actual installed Node path');write_new(work/'NODE-BINARY.json',{'binary':str(node),**binding(node)})
  with cancellation_scope():process=core['run_process']([str(node),'--max-old-space-size=768',str(project/APP/'campaign-sdk-worker.mjs'),str(work/'job.json'),sha(raw)],str(output),env,b'',work,timeout=BUDGETS['SDKBatchSeconds'],log_limit=BUDGETS['SDKStreamBytes'],artifact_limit=BUDGETS['SDKBatchBytes'])
  need(process['exitCode']==0 and process['stopReason'] is None and not process['controllerErrors'] and not process['rawStreamsMayBeTruncated'],'SDK batch process failed; first-stop')
  receipt=decode((work/'case-results/receipt.json').read_bytes());need(receipt['passed'] is True and receipt['completed']==receipt['requested']==50,'SDK fifty-case receipt')
 except BaseException as e:primary=e;raise
 finally:
  try:write_new(work/'process.json',process if process is not None else {'exitCode':None,'stopReason':'controller-start-or-execution-failure','error':str(primary)})
  except Exception as e:
   if primary is None:raise
   primary.add_note('SDK process receipt failed: '+repr(e))
  try:audit_public(public,manifest,base)
  except Exception as e:
   if primary is None:raise
   primary.add_note('Public SDK after audit failed: '+repr(e))

def execute(project,output,doc,campaign,plans,rows,base):
 r4=project/APP/'r4';runtimeRoot=Path(base['PRODUCER_LITERAL']);initial=None;primary=None;started=time.monotonic();core=base['verified_module'](r4/'r4_controller.py',base['CORE'],'campaign_fixed_r4_core');public=output/'public-sdk/dist';publicManifest=decode((project/APP/'campaign-public-dist-manifest.json').read_bytes());publicPin=binding(project/APP/'campaign-public-dist-manifest.json')['sha256']
 for n in ('elle','processes','sdk','runtime-audits','public-sdk'):(output/n).mkdir()
 (output/'elle/actual-outputs').mkdir();write_new(output/'INPUTS.original.jsonl',(project/DATASET).read_bytes())
 try:
  need(not runtimeRoot.exists(),'fresh original literal runtime root');archive=Path(RUNTIME_ZIP);need(binding(archive)=={'bytes':base['ARTIFACT_BYTES'],'sha256':base['ARTIFACT_SHA']},'whole admitted runtime ZIP');base['validate_metadata'](decode((output/'runtime-artifact-metadata.original.json').read_bytes()))
  with zipfile.ZipFile(archive) as z:
   raw=z.read('OUTPUT-INDEX.json');need(len(raw)==122404 and sha(raw)==base['INDEX_SHA'],'original output index');index=base['validate_output_index'](decode(raw));base['validate_members'](z.infolist(),index);restored=base['restore_members'](z,runtimeRoot,index,raw)
  initial=base['closure'](runtimeRoot);need(initial=={'files':restored,'directories':sorted(index['directories'])},'full original544 restore');write_new(output/'RUNTIME-BEFORE.json',initial)
  checkpoint(output,started,core);verify_args=['--root',str(runtimeRoot/'runtime'),'--index-sha256',base['RUNTIME_INDEX_SHA'],'--runtime-sha256',base['RUNTIME_SHA'],'--controller',str(r4/'r4_controller.py'),'--output',str(output/'runtime-restore-first.json')];need(base['in_process'](project/APP/'supply/verify_restored_runtime.py',base['VERIFY'],verify_args,output/'processes/runtime-verifier')==0,'original runtime/executable verifier');need(base['closure'](runtimeRoot)==initial,'restore verifier runtime mutation')
  extract_public(Path(PUBLIC_ZIP),public,publicManifest,base);write_new(output/'PUBLIC-SDK-PREPARATION.json',{'archive':binding(PUBLIC_ZIP),'distFiles':102,'entryPoint':'public-sdk/dist/sdk.mjs','anonymousURL':publicManifest['url'],'source':'public anonymous release byte-pinned download; no author dist or historical SDK entry'})
  for i,batch in enumerate(campaign['batches']):
   write_new(output/'runtime-audits'/('budget-before-'+batch['name']+'.json'),checkpoint(output,started,core));runtime_audit(base,initial,runtimeRoot,output/'runtime-audits'/('before-'+batch['name']));args=['--execute','--plan',str(r4/batch['planPath']),'--plan-sha256',batch['planSha256'],'--runtime',str(runtimeRoot/'runtime/runtime-manifest.json'),'--runtime-sha256',base['RUNTIME_SHA'],'--wrapper',str(r4/'elle_batch_r4.clj'),'--summary',str(r4/'original-r3/result_summary.clj'),'--transport',str(r4/'original-r3/transport.clj'),'--output',str(output/'elle'/batch['outputDirectory'])];batchPrimary=None
   try:need(base['in_process'](r4/'r4_controller.py',base['CORE'],args,output/'processes'/batch['name'])==0,'original fixed R4 batch failed '+batch['name'])
   except BaseException as e:batchPrimary=e;raise
   finally:
    try:runtime_audit(base,initial,runtimeRoot,output/'runtime-audits'/('after-'+batch['name']))
    except Exception as e:
     if batchPrimary is None:raise
     batchPrimary.add_note('runtime after batch failed: '+repr(e))
   checkpoint(output,started,core);run_sdk_batch(project,output,batch,rows[i*50:(i+1)*50],publicManifest,publicPin,public,base,core)
 except BaseException as e:primary=e;raise
 finally:
  # Always enumerate original40, even after restore failure or first-stop. No missing case is completed by registration.
  collectorArgs=['--campaign',str(r4/'campaign-plan-final2.json'),'--campaign-sha256',CAMPAIGN_SHA,'--controller',str(r4/'r4_controller.py'),'--outputs-root',str(output/'elle'),'--output',str(output/'ELLE-COLLECTION.original.json'),'--runtime-sha256',base['RUNTIME_SHA']]
  try:
   rc=base['in_process'](r4/'collect_campaign.py',COLLECTOR_SHA,collectorArgs,output/'processes/final-collector');write_new(output/'COLLECTOR-RETURN.json',{'returnCode':rc,'original40Enumerated':True});need(rc==0,'original full campaign transport incomplete')
  except Exception as e:
   if primary is None:primary=e
   else:primary.add_note('final original collector: '+repr(e))
  try:
   sdk=collect_sdk(output,rows,campaign['batches'],base);write_new(output/'SDK-COLLECTION.json',sdk);elle=decode((output/'ELLE-COLLECTION.original.json').read_bytes());comparison=compare_cases(elle,sdk,rows);write_new(output/'COMPARISON.json',comparison);need(comparison['actual2000Executed'],'full actual2000 comparison incomplete')
  except Exception as e:
   if primary is None:primary=e
   else:primary.add_note('comparison collection: '+repr(e))
  if initial is not None:
   try:runtime_audit(base,initial,runtimeRoot,output/'runtime-audits/final')
   except Exception as e:
    if primary is None:primary=e
    else:primary.add_note('final runtime audit: '+repr(e))
  if primary is not None and sys.exc_info()[0] is None:raise primary
 return {'passed':True,'scope':'original fixed2000 shared serializable comparison; raw evidence requires independent review','actual2000Executed':True,'actualSDKExecuted':True,'semanticAgreementRequired':False,'actual2000AcceptedByIndependentReviewer':False,'automaticRetry':False,'publicSDKSource':'anonymous fixed public v027 top-level102 dist','collected':binding(output/'COMPARISON.json')}

def main():
 p=argparse.ArgumentParser();p.add_argument('--phase',choices=('preflight','execute'),required=True);p.add_argument('--source-manifest-sha256',required=True);p.add_argument('--execute-hosted-campaign',action='store_true');a=p.parse_args();need(a.execute_hosted_campaign and sys.platform=='linux' and sys.version_info[:2]==(3,12),'explicit hosted Linux Python312 campaign only');env=dict(os.environ);need(env.get('RUNNER_TEMP')=='/home/runner/work/_temp','original literal temp');project=Path.cwd().absolute();base=load_base(project);output=Path(OUT_LITERAL);base['plain'](output.parent)
 if a.phase=='preflight':need(not output.exists() and not Path(base['PRODUCER_LITERAL']).exists() and not Path(RUNTIME_ZIP).exists() and not Path(PUBLIC_ZIP).exists(),'fresh exclusive output/runtime/downloads');output.mkdir()
 else:base['plain'](output);need(output.is_dir() and not (output/'EXECUTION-STARTED.json').exists(),'one execution only; no retry')
 primary=None
 try:
  source,doc,campaign,plans,rows=source_check(project,a.source_manifest_sha256,env,base)
  if a.phase=='preflight':write_new(output/'SOURCE-ATTESTATION.json',source);write_new(output/'STAGE.original.json',(project/APP/'campaign-stage.json').read_bytes());write_new(output/'SOURCE-MANIFEST.original.json',(project/APP/'campaign-source-manifest.json').read_bytes());write_new(output/'PREFLIGHT.json',{'passed':True,'actual2000Executed':False,'actualSDKExecuted':False,'actualInputScope':{'register':1000,'list':1000},'prior8UnknownsNotConvertedToAgreement':True})
  else:
   need(decode((output/'SOURCE-ATTESTATION.json').read_bytes())==source,'source/context changed since preflight');write_new(output/'EXECUTION-STARTED.json',{'source':source,'oneShot':True,'budgets':BUDGETS,'actualResultsNotInferredFromIntent':True});
   with cancellation_scope():result=execute(project,output,doc,campaign,plans,rows,base)
   after,*_=source_check(project,a.source_manifest_sha256,env,base);need(after==source,'source changed during campaign');write_new(output/'STAGE-RECEIPT.json',result)
 except BaseException as e:
  primary=e
  try:write_new(output/(a.phase+'-FIRST-FAILURE.json'),{'passed':False,'type':type(e).__name__,'reason':str(e),'notes':getattr(e,'__notes__',[]),'actualUnknownOrUnexecutedCasesNeverCompleted':True,'automaticRetry':False,'rawPartialEvidenceNotDeleted':True,'independentAdmissionNotClaimed':True})
  except Exception as diagnostic:e.add_note('first-failure receipt: '+repr(diagnostic))
  raise
 finally:
  try:write_new(output/('OUTPUT-INDEX-'+a.phase+'.json'),{'sourceRoot':str(output),'phase':a.phase,**base['closure'](output),'SDKOrCheckerResultsNotInferredByIndex':True})
  except Exception:
   if primary is None:raise
 return 0
if __name__=='__main__':raise SystemExit(main())