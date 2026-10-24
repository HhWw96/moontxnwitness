"""Freeze actual independently built runtimes before the exact differential."""
from pathlib import Path
import hashlib,json,os,subprocess,sys
BASE='c10b06c5bfcabd1f40b0ff0099717072a816ec74'
BASE_SHA='4b8e9567f363a675cdafebab20547f6964760aa565d5359efccae4aa4f6f9a80'
CAND_SHA='8a214ca4591c7ca2af5fdb0967245022aaca94c76174f64aaf7519a27f8165ea'
def sha(b):return hashlib.sha256(b).hexdigest()
def need(v,m):
 if not v:raise ValueError(m)
def git(p,*args):return subprocess.check_output(['git',*args],cwd=p).decode().strip()
def save(p,o):
 with p.open('x',encoding='utf8',newline='\n')as f:json.dump(o,f,indent=2);f.write('\n')
workspace=Path(os.environ['GITHUB_WORKSPACE']).resolve(); candidate=workspace/'candidate';baseline=workspace/'baseline';home=candidate/'.github/experiments/reduction-structured';out=workspace/'reduction-evidence';out.mkdir(exist_ok=True)
need(git(baseline,'rev-parse','HEAD')==BASE,'Baseline commit mismatch')
need(git(candidate,'rev-parse','HEAD')==os.environ['GITHUB_SHA'],'Actual experiment checkout mismatch')
need(os.environ['GITHUB_REPOSITORY']=='HhWw96/moontxnwitness','Repository mismatch')
need(os.environ['GITHUB_EVENT_NAME']=='push','Only one declared experimental push')
need(os.environ['GITHUB_REF']=='refs/heads/experimental/v028-reduction-structured-20261025','Exact experimental branch required')
need(git(candidate,'merge-base',BASE,'HEAD')==BASE,'Experiment must descend from frozen release')
changed=git(candidate,'diff','--name-only',BASE,'HEAD').splitlines()
products={'src/api_v3.mbt','src/list_v3.mbt','src/relation_v3.mbt'}
allowed=products|{'.github/workflows/experimental-reduction-structured.yml'}
need(products<=set(changed),'Candidate product changes missing')
need(all(p in allowed or p.startswith('.github/experiments/reduction-structured/')for p in changed),'Unexpected changed source')
for role,root,wanted in [('baseline',baseline,BASE_SHA),('candidate',candidate,CAND_SHA)]:
 need(sha((root/'src/api_v3.mbt').read_bytes())==wanted,'Actual '+role+' source differs')
 need((root/'src/api_v3.mbt').read_bytes()==(home/role/'src/api_v3.mbt').read_bytes(),'Handoff differs from actual '+role)
manifest=json.loads((home/'CANDIDATE.json').read_bytes());need(manifest['baseCommit']==BASE,'Wrong manifest baseline')
need({r['path']for r in manifest['productFiles']}==products,'Exact three product files required')
for row in manifest['productFiles']:
 for role,root in [('baseline',baseline),('candidate',candidate)]:
  raw=(root/row['path']).read_bytes();need(sha(raw)==row[role+'Sha256'],'Actual product differs from frozen '+role)
  need(raw==(home/role/row['path']).read_bytes(),'Source evidence differs from actual product')
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
receipt=json.loads((out/'differential-first/RECEIPT.json').read_bytes());need(receipt['passed']is True and len(receipt['cases'])==284 and all(r['passed']for r in receipt['cases']),'Incomplete or failed differential')
print(json.dumps({'passed':True,'cases':len(receipt['cases']),'calls':receipt['calls'],'performanceMeasured':False}))
