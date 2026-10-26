"""Freeze actual independently built runtimes before the exact differential."""
from pathlib import Path
import hashlib,json,os,subprocess,sys
BASE='c10b06c5bfcabd1f40b0ff0099717072a816ec74'
BASE_SHA='4b8e9567f363a675cdafebab20547f6964760aa565d5359efccae4aa4f6f9a80'
CAND_SHA='f2c5a8f149f8f17c566cd7668cdbd0dfbf2dc935215261ec35c3958eb86ea54d'
def sha(b):return hashlib.sha256(b).hexdigest()
def need(v,m):
 if not v:raise ValueError(m)
def git(p,*args):return subprocess.check_output(['git',*args],cwd=p).decode().strip()
def save(p,o):
 with p.open('x',encoding='utf8',newline='\n')as f:json.dump(o,f,indent=2);f.write('\n')
workspace=Path(os.environ['GITHUB_WORKSPACE']).resolve(); candidate=workspace/'candidate';baseline=workspace/'baseline';home=candidate/'.github/experiments/reduction-relation-only';out=workspace/'reduction-evidence';out.mkdir(exist_ok=True)
need(git(baseline,'rev-parse','HEAD')==BASE,'Baseline commit mismatch')
need(git(candidate,'rev-parse','HEAD')==os.environ['GITHUB_SHA'],'Actual experiment checkout mismatch')
need(os.environ['GITHUB_REPOSITORY']=='HhWw96/moontxnwitness','Repository mismatch')
need(os.environ['GITHUB_EVENT_NAME']=='push','Only one declared experimental push')
need(os.environ['GITHUB_REF']=='refs/heads/experimental/v028-reduction-relation-only-20261025','Exact experimental branch required')
need(git(candidate,'merge-base',BASE,'HEAD')==BASE,'Experiment must descend from frozen release')
changed=git(candidate,'diff','--name-only',BASE,'HEAD').splitlines()
products={'src/api_v3.mbt','src/relation_v3.mbt'}
allowed=products|{'.github/workflows/experimental-reduction-relation-only.yml'}
need(products<=set(changed),'Candidate product changes missing')
need(all(p in allowed or p.startswith('.github/experiments/reduction-relation-only/')for p in changed),'Unexpected changed source')
for role,root,wanted in [('baseline',baseline,BASE_SHA),('candidate',candidate,CAND_SHA)]:
 need(sha((root/'src/api_v3.mbt').read_bytes())==wanted,'Actual '+role+' source differs')
 need((root/'src/api_v3.mbt').read_bytes()==(home/role/'src/api_v3.mbt').read_bytes(),'Handoff differs from actual '+role)
manifest=json.loads((home/'CANDIDATE.json').read_bytes());need(manifest['baseCommit']==BASE,'Wrong manifest baseline')
need({r['path']for r in manifest['productFiles']}==products,'Exact two modified product files required')
for row in manifest['productFiles']:
 for role,root in [('baseline',baseline),('candidate',candidate)]:
  raw=(root/row['path']).read_bytes();need(sha(raw)==row[role+'Sha256'],'Actual product differs from frozen '+role)
  need(raw==(home/role/row['path']).read_bytes(),'Source evidence differs from actual product')
# The source certificates are original raw UTF-8, including historical failure
# records. This validates a source-only handoff, not an executed SDK result.
certificate_pins={'handoff': '65655fbfcc51e78d287e9cba0c58421dae10b25ff327d48aae5056f12a84733a', 'sourceClosure': 'c907d7a0f34b5c087301f6bffdc611e06b9522234a7d94a9d325495a7f97f06f', 'sourceCandidate': 'f3bf3dbdbe325f958ea22df8c4a06c5599c251cd0aa95ae3185898337cff46ef', 'sourceLocations': 'd0eedd414e953e010926c7701ad0521e1cfa6d9d7b258a023957a16341f3faff', 'independentSourceReview': '3a751d0e539e5892f771f50dffbaa0ebebb49c212e62cf140c5824bf30a39328'}
certificates=manifest['sourceCertificates'];need(set(certificates)==set(certificate_pins),'Exact source certificate closure required')
decoded={}
for key,wanted in certificate_pins.items():
 row=certificates[key];raw=row['utf8Text'].encode('utf8')
 need(len(raw)==row['bytes']and sha(raw)==wanted and row['sha256']==wanted,'Source certificate differs: '+key)
 decoded[key]=json.loads(raw)
review=decoded['independentSourceReview'];handoff=decoded['handoff'];description=decoded['sourceCandidate']
need(review['passed']is True and review['readyForHostedDifferentialReview']is True and review['hostedPackageReviewStillRequired']is True,'Only independent source review is recorded')
need(review['baseCommit']==BASE and handoff['baseCommit']==BASE and description['baseCommit']==BASE,'Source certificate baseline differs')
need(review['handoff']['sha256']==certificate_pins['handoff']and review['sourceClosure']['sha256']==certificate_pins['sourceClosure']and review['candidateDescription']['sha256']==certificate_pins['sourceCandidate'],'Independent review source certificate binding differs')
need(handoff['sourceClosure']['sha256']==certificate_pins['sourceClosure']and handoff['candidateDescription']['sha256']==certificate_pins['sourceCandidate'],'Handoff source closure differs')
need(review['patch']['sha256']==manifest['patchSha256']and handoff['patch']['sha256']==manifest['patchSha256']and description['patch']['sha256']==manifest['patchSha256'],'Relation-only source patch binding differs')
need(set(review['modifiedProductPaths'])==products and set(handoff['exactModifiedPaths'])==products and set(description['exactModifiedPaths'])==products,'Source certificate product scope differs')
need(len(manifest['sourceSnapshots'])==3 and {r['path']for r in manifest['sourceSnapshots']}==products|{'src/list_v3.mbt'},'Exact three source snapshots required')
for row in manifest['sourceSnapshots']:
 for role,root in [('baseline',baseline),('candidate',candidate)]:
  raw=(root/row['path']).read_bytes();need(len(raw)==row[role+'Bytes']and sha(raw)==row[role+'Sha256'],'Actual source snapshot differs: '+role+' '+row['path'])
  need(raw==(home/role/row['path']).read_bytes(),'Source snapshot handoff differs from actual tree')
 for source_row in description['sourceFiles']:
  if source_row['path']==row['path']:
   need(source_row['baseline']['sha256']==row['baselineSha256']and source_row['candidate']['sha256']==row['candidateSha256'],'Candidate certificate selected source differs')
 for selection in [review['selectedSourceFiles'],handoff['selectedSources'],decoded['sourceClosure']['selectedFormattedFiles']]:
  matches=[r for r in selection if r['path'].replace('\\','/').endswith('/formatted/'+row['path'])]
  need(len(matches)==1 and matches[0]['sha256']==row['candidateSha256']and matches[0]['bytes']==row['candidateBytes'],'Reviewed source selection differs')
need((baseline/'src/list_v3.mbt').read_bytes()==(candidate/'src/list_v3.mbt').read_bytes(),'List source must remain complete baseline bytes')
need(manifest['unchangedHarness']=={'sha256':'d11e76c9b2734e276391f05580b6ea3abe47e6de444025013021bf4dcd7114e1','cases':284,'priorFullStructuredCalls':1658,'sdkOverLimitExceptionCases':2,'allInputsAndExpectationsUnchanged':True},'Differential scope or expectations changed')
need(sha((home/'run_differential.mjs').read_bytes())==manifest['unchangedHarness']['sha256'],'Original exact differential harness changed')
need(manifest['experimentalBranch']=='experimental/v028-reduction-relation-only-20261025','Declared branch differs')
for row in manifest['inputs']:
 raw=(home/'inputs'/row['path']).read_bytes();need(len(raw)==row['bytes']and sha(raw)==row['sha256'],'Frozen differential input differs')
 for root in (baseline,candidate):need((root/row['path']).read_bytes()==raw,'Original fixture differs')
for row in manifest['sourceReferences']:
 raw=(baseline/row['path']).read_bytes();need(len(raw)==row['bytes']and sha(raw)==row['sha256'],'Fixed source reference differs')
 if row['path']not in products:need((candidate/row['path']).read_bytes()==raw,'Non-target implementation changed')
need(sha((home/'candidate.patch').read_bytes())==manifest['patchSha256'],'Original patch differs')
binding={'schema':1,'baseCommit':BASE,'baseline':{},'candidate':{}}
for role,root,wanted in [('baseline',baseline,BASE_SHA),('candidate',candidate,CAND_SHA)]:
 runtime=root/'dist';need(runtime.is_dir(),'Runtime was not built')
 files=[]
 for p in sorted(runtime.rglob('*')):
  need(not p.is_symlink(),'Runtime symlink refused')
  if p.is_dir():continue
  need(p.is_file(),'Plain runtime file required');raw=p.read_bytes();files.append({'path':p.relative_to(runtime).as_posix(),'bytes':len(raw),'sha256':sha(raw)})
 names={r['path']for r in files};need({'sdk.mjs','core.mjs','capture-core.mjs','build-manifest.json'}<=names,'Incomplete runtime')
 build=json.loads((runtime/'build-manifest.json').read_bytes());need(build['version']=='0.2.7','Same-version experimental comparison required')
 need(build['coreSha256']==sha((runtime/'core.mjs').read_bytes()),'Compiled core binding differs')
 need(build['captureCoreSha256']==sha((runtime/'capture-core.mjs').read_bytes()),'Compiled capture binding differs')
 source_names=['moon.mod']+[p.relative_to(root).as_posix()for p in(root/'src').rglob('*')if p.is_file()and(p.suffix=='.mbt'or p.name=='moon.pkg')]
 h=hashlib.sha256()
 for name in sorted(source_names):h.update(name.encode()+b'\0'+(root/name).read_bytes()+b'\0')
 need(h.hexdigest()==build['sourceSha256'],'Actual runtime source fingerprint differs')
 need('0.10.14+7d59c7ec9'in build['toolchain']['compiler'],'Compiler must match fixed release')
 binding[role]={'sourceFileSha256':wanted,'files':files,'buildManifest':build}
 runtime_inventory=out/(role+'-runtime.json');save(runtime_inventory,{'role':role,'files':files,'buildManifest':build})
raw=(json.dumps(binding,indent=2)+'\n').encode();bp=out/'RUNTIME-BINDINGS.json';bp.write_bytes(raw)
save(out/'SOURCE-ATTESTATION.json',{'schema':1,'actualBaseCommit':BASE,'actualCandidateCommit':os.environ['GITHUB_SHA'],'changedFiles':changed,'sourceDifferentOnlyIn':sorted(products),'harnessSha256':sha((home/'run_differential.mjs').read_bytes()),'bindingsSha256':sha(raw),'performanceMeasured':False,'databaseExecutedByThisJob':False,'publicRelease':False})
command=['node','--max-old-space-size=768',str(home/'run_differential.mjs'),'--baseline-runtime',str(baseline/'dist'),'--candidate-runtime',str(candidate/'dist'),'--bindings',str(bp),'--bindings-sha256',sha(raw),'--output',str(out/'differential-first')]
save(out/'EXECUTION-INTENT.json',{'command':command,'runtimePinProducedOnlyAfterActualBuild':True,'automaticRetry':False})
with(out/'differential.stdout.original.log').open('xb')as stdout,(out/'differential.stderr.original.log').open('xb')as stderr:
 result=subprocess.run(command,cwd=workspace,stdout=stdout,stderr=stderr,timeout=1800)
save(out/'EXECUTION.json',{'exitCode':result.returncode,'actualProcessExecuted':True,'automaticRetry':False})
need(result.returncode==0,'First differential execution failed; preserve all original outputs')
receipt=json.loads((out/'differential-first/RECEIPT.json').read_bytes());need(receipt['passed']is True and len(receipt['cases'])==284 and receipt['calls']==1658 and sum(bool(r.get('sdkExceptionCompared'))for r in receipt['cases'])==2 and all(r['passed']for r in receipt['cases']),'Incomplete or failed differential')
print(json.dumps({'passed':True,'cases':len(receipt['cases']),'calls':receipt['calls'],'performanceMeasured':False}))
