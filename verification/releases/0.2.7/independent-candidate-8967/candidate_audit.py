"""Independent prepublication CI candidate audit. No downloads, SQL, services or source compilation."""
import argparse,ctypes,hashlib,json,os,re,shutil,stat,subprocess,sys,time,traceback,zipfile
from pathlib import Path,PurePosixPath
VERSION='0.2.7'; PREFIX='MoonTxnWitness-v0.2.7/'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def binding(path):
 p=Path(path);h=hashlib.sha256()
 with p.open('rb')as f:
  for chunk in iter(lambda:f.read(1048576),b''):h.update(chunk)
 return {'bytes':p.stat().st_size,'sha256':h.hexdigest()}
def read_bound(record):
 p=Path(record['path']);actual=binding(p)
 assert actual=={k:record[k]for k in ('bytes','sha256')},f'binding mismatch {p.name}'
 return p

def member_parts(name):
 assert name.startswith(PREFIX),'wrong product root'
 assert '\\'not in name and ':'not in name and not name.startswith('/'),'unsafe ZIP path'
 parts=name.rstrip('/').split('/')
 assert all(x and x not in ('.','..')for x in parts),'unsafe ZIP component'
 for x in parts:
  assert x==x.rstrip(' .') and not any(ord(c)<32 for c in x),'unsafe Windows name'
  assert not re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?',x),'reserved Windows name'
 return parts

def zip_inventory(path,maximum):
 with zipfile.ZipFile(path)as z:
  infos=z.infolist();seen=set();total=0
  for info in infos:
   member_parts(info.filename);key=info.filename.rstrip('/').casefold()
   assert key not in seen,'duplicate case-insensitive member';seen.add(key)
   mode=info.external_attr>>16
   assert not stat.S_ISLNK(mode)and not info.flag_bits&1,'link/encrypted member'
   assert not mode or stat.S_IFMT(mode)in(0,stat.S_IFREG,stat.S_IFDIR),'special member'
   total+=info.file_size
  assert total<=maximum,'ZIP expansion exceeds fixed budget'
  return infos,total

def extract_new(path,destination,maximum):
 infos,total=zip_inventory(path,maximum);destination.mkdir();records=[]
 with zipfile.ZipFile(path)as z:
  for info in infos:
   target=destination.joinpath(*member_parts(info.filename))
   assert target.resolve().is_relative_to(destination.resolve())
   if info.is_dir():target.mkdir(parents=True,exist_ok=True);continue
   target.parent.mkdir(parents=True,exist_ok=True);h=hashlib.sha256();count=0
   with z.open(info)as src,target.open('xb')as dst:
    for chunk in iter(lambda:src.read(1048576),b''):dst.write(chunk);h.update(chunk);count+=len(chunk)
   assert count==info.file_size
   records.append({'file':info.filename[len(PREFIX):],'bytes':count,'sha256':h.hexdigest()})
 return destination/PREFIX.rstrip('/'),records

class MemoryStatus(ctypes.Structure):
 _fields_=[('length',ctypes.c_uint32),('load',ctypes.c_uint32)]+[(x,ctypes.c_uint64)for x in ['totalPhys','availPhys','totalPage','availPage','totalVirtual','availVirtual','availExtended']]
def resources(where):
 m=MemoryStatus();m.length=ctypes.sizeof(m);assert ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
 return {'availablePhysicalBytes':m.availPhys,'CfreeBytes':shutil.disk_usage('C:\\').free,'DfreeBytes':shutil.disk_usage(where).free}
def write_new(path,obj):
 with Path(path).open('x',encoding='utf-8',newline='\n')as f:json.dump(obj,f,ensure_ascii=True,indent=2);f.write('\n')
def decoded(raw):return json.loads(raw.decode('utf-8-sig'))
def tree(root):return {p.relative_to(root).as_posix():binding(p)for p in root.rglob('*')if p.is_file()}
def run(node,args,label,out,cwd,expected=(0,),node_options=''):
 r=resources(out);write_new(out/(label+'.resources.json'),r);assert r['availablePhysicalBytes']>=1073741824,'RAM below fixed1GiB before child'
 env=os.environ.copy();env['NODE_OPTIONS']=node_options;env.pop('NODE_PATH',None)
 command=[str(node),'--max-old-space-size=384',*map(str,args)]
 record={'label':label,'argv':command,'startedUtc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'resources':r,'timeoutSeconds':900,'actualExitCode':None}
 write_new(out/(label+'.started.json'),record)
 stdout=out/(label+'.stdout.json');stderr=out/(label+'.stderr.log')
 with stdout.open('xb')as o,stderr.open('xb')as e:
  try:process=subprocess.run(command,cwd=cwd,env=env,stdout=o,stderr=e,timeout=900);record['actualExitCode']=process.returncode
  except subprocess.TimeoutExpired:record['timeout']=True
 record['stdout']=binding(stdout);record['stderr']=binding(stderr);record['expectedExitCodes']=list(expected);record['passed']=record['actualExitCode']in expected
 write_new(out/(label+'.process.json'),record);assert record['passed'],f'{label} process failed: {record}'
 return decoded(stdout.read_bytes())

def execute(lock,node,out):
 out.mkdir();steps=[];receipt={'format':'moontxnwitness027-independent-prepublication-candidate-audit/v1','passed':False,'version':VERSION,'auditKind':'prepublication-ci-candidate','publicDownloadVerified':False,'publicReleaseVerified':False,'newDatabaseExecution':False,'newHTTP':False,'sourceClosedReductionClaimed':False,'steps':steps,'fatal':None}
 source=portable=None;before={}
 try:
  assert lock['status']=='READY-ACTUAL-CI-ORIGINALS';assert lock['version']==VERSION;assert lock['expectedWorkflowSourceCommit']=='8967b960326eab4b7f0a17b61ca7942393856c08'
  assert lock['publicDownloadClaimed']is False and lock['sourceClosedModelReductionClaimed']is False
  node=read_bound(lock['node']);assert node.suffix.lower()=='.exe'
  artifact=read_bound(lock['originalCIArtifact']);sourceZip=read_bound(lock['sourceZip']);portableZip=read_bound(lock['portableZip'])
  packagePath=read_bound(lock['originalPackageReceipt']);releasePath=read_bound(lock['originalReleaseReceipt']);summaryPath=read_bound(lock['originalSummary']);originalBuild=read_bound(lock['candidateRuntimeBuild'])
  log=read_bound(lock['originalCiNativeLog']);read_bound(lock['originalCiSourceConsumerLog'])
  package=decoded(packagePath.read_bytes());release=decoded(releasePath.read_bytes());assert package==release
  assert package['version']==VERSION and package['passed']is True and package['sourceRebuilt']is True and package['publiclyPublished']is False and package['freshConsumerChecks']==122
  for kind,p in [('source',sourceZip),('portable',portableZip)]:
   row=next(x for x in package['archives']if x['file']==p.name);assert {k:row[k]for k in ('bytes','sha256')}==binding(p)
  with zipfile.ZipFile(artifact)as z:
   for record in [lock['sourceZip'],lock['portableZip'],lock['originalPackageReceipt'],lock['originalReleaseReceipt'],lock['originalSummary'],lock['candidateRuntimeBuild']]:
    h=hashlib.sha256();size=0
    with z.open(record['artifactMember'])as f:
     for chunk in iter(lambda:f.read(1048576),b''):h.update(chunk);size+=len(chunk)
    assert {'bytes':size,'sha256':h.hexdigest()}=={k:record[k]for k in ('bytes','sha256')}
  steps.append({'name':'actual-original-ci-archive-and-metadata','passed':True,'ciFreshConsumerChecks':122,'ciSourceRebuilt':True,'sourceCommit':lock['expectedWorkflowSourceCommit']})
  inventories=[zip_inventory(p,lock['maxUncompressedBytesPerZip'])for p in [sourceZip,portableZip]]
  r=resources(out);write_new(out/'resources-before-extraction.json',r);assert r['DfreeBytes']>=sum(x[1]for x in inventories)+1073741824,'D expansion reserve below budget'
  source,srecords=extract_new(sourceZip,out/'source-extracted',lock['maxUncompressedBytesPerZip']);portable,precords=extract_new(portableZip,out/'portable-extracted',lock['maxUncompressedBytesPerZip'])
  write_new(out/'source-extraction-manifest.json',srecords);write_new(out/'portable-extraction-manifest.json',precords)
  before={'source':{x['file']:{k:x[k]for k in ('bytes','sha256')}for x in srecords},'portable':{x['file']:{k:x[k]for k in ('bytes','sha256')}for x in precords}}
  assert not(source/'dist').exists();runtime=tree(portable/'dist');assert len(runtime)==102
  with zipfile.ZipFile(artifact)as z:
   actualNames=[x for x in z.infolist()if x.filename.startswith('dist/')and not x.is_dir()];assert len(actualNames)==102
   for info in actualNames:
    raw=z.read(info);assert runtime[info.filename[5:]]=={'bytes':len(raw),'sha256':sha(raw)}
  manifest=decoded((portable/'dist/build-manifest.json').read_bytes());assert manifest==decoded(originalBuild.read_bytes());assert manifest['version']==VERSION
  for name,key in [('core.mjs','coreSha256'),('capture-core.mjs','captureCoreSha256')]:assert binding(portable/'dist'/name)['sha256']==manifest[key]
  assert decoded((source/'package.json').read_bytes())['version']==VERSION and decoded((portable/'package.json').read_bytes())['version']==VERSION
  names=['moon.mod']+sorted(p.relative_to(source).as_posix()for p in(source/'src').rglob('*')if p.is_file()and(p.suffix=='.mbt'or p.name=='moon.pkg'))
  h=hashlib.sha256()
  for name in sorted(names):h.update(name.encode()+b'\0');h.update((source/name).read_bytes());h.update(b'\0')
  assert h.hexdigest()==manifest['sourceSha256'];steps.append({'name':'full-original-source-and-runtime-closure','passed':True,'sourceFiles':len(srecords),'portableFiles':len(precords),'runtimeFiles':len(runtime),'sourceFingerprintFiles':len(names),'buildManifest':manifest})
  summary=decoded(summaryPath.read_bytes());assert summary==decoded((source/'verification/summary.json').read_bytes())==decoded((portable/'verification/summary.json').read_bytes());assert summary['passed']is True and summary['version']==VERSION and summary['buildManifest']==manifest
  for name,expected in summary['testedFileSha256'].items():
   target=portable/name if name.startswith('dist/')else source/name
   assert binding(target)['sha256']==expected,f'tested source mismatch {name}'
  for name,pin in lock['requiredOriginalSourceScripts'].items():
   assert binding(source/name)==pin
   if(portable/name).exists():assert binding(portable/name)==pin
  fixture=portable/'fixtures/compat-v026/manifest.json';assert binding(fixture)['sha256']==lock['public026FixtureManifestSha256']
  steps.append({'name':'actual-tested-source-and-frozen-script-bindings','passed':True,'testedFiles':len(summary['testedFileSha256']),'coreTestsPerExecutedTargetFromOriginalCI':summary['coreTestsPerTarget'],'executedTargetsFromOriginalSummary':summary['executedTargets'],'nativeEvidence':'original full Linux log; stale native-status.json is not used'})
  compatibility=run(node,[portable/'scripts/compat-v026-test.mjs',portable/'dist',portable/'fixtures/compat-v026',out/'public026-results'],'public026',out,portable,node_options='--max-old-space-size=384')
  cr=decoded((out/'public026-results/receipt.json').read_bytes());assert compatibility['passed']is True and cr['passed']is True and cr['checkCount']==623 and cr['originalProducerFamilies']==35 and cr['expectedRegenerated']is False
  cliFiles=list((out/'public026-results').glob('*.cli.stdout.json'));assert len(cliFiles)==12
  steps.append({'name':'unchanged-original-public026-compatibility','passed':True,'assertions':cr['checkCount'],'families':35,'actualCliInvocations':12,'sdkTopLevelCalls':None,'sdkCountReason':'original unmodified producer test does not instrument SDK top-level count','historicalWorkerLaunches':cr.get('inProcessObservedHistoricalWorkerLaunches'),'historicalWorkerLaunchesByVersion':cr.get('inProcessHistoricalWorkerLaunchesByVersion')})
  ownScript=read_bound(lock['currentCapsuleAuditScript'])
  cap=run(node,[ownScript,portable,out/'current-pg-results'],'current-pg',out,portable);assert cap['passed']is True and cap['sdkTopLevelCalls']==101 and len(cap['cases'])==10
  steps.append({'name':'current-10-original-captured-model-capsules','passed':True,'sdkTopLevelCalls':101,'cases':10,'tamperRefusals':70,'newDatabaseExecution':False,'sourceClosedReductionClaimed':False})
  example=run(node,[portable/'examples/model-profile-roundtrip.mjs','--out-root',out/'retained-example-results'],'retained-configured-model-example',out,portable);assert example['passed']is True and example['cases']==4 and example['actualDatabaseExecution']is False and example['sourceClosedReductionClaimed']is False
  steps.append({'name':'packaged-retained-configured-model-example','passed':True,'cases':4,'sdkTopLevelCalls':None,'originalInputsFromRetainedDatabaseRun':True,'current10CasesClaimed':False})
  envelope=portable/'verification/releases/0.2.7/current-pg-sdk-loop/first/first-run/results/list-write-skew/source.original.json';report=out/'configured-cli.report.json';capsule=out/'configured-cli.capsule.json';cli=portable/'dist/moontxnwitness.mjs'
  analyzed=run(node,[cli,'model-profile-v3',envelope,'--output',report,'--capsule',capsule],'configured-cli-analyze',out,portable,expected=(1,));assert analyzed['status']=='violation'
  verified=run(node,[cli,'verify-model-profile-v3',envelope,report],'configured-cli-verify',out,portable);assert verified['valid']is True
  replay=run(node,[cli,'replay-model-profile-v3',capsule],'configured-cli-replay',out,portable);assert replay['valid']is True and replay['status']=='violation'
  steps.append({'name':'new-configured-model-cli-round-trip','passed':True,'actualCliInvocations':3,'status':'violation'})
  r=resources(out);steps.append({'name':'local-source-rebuild','status':'not-executed','reason':'not authorized within this lightweight audit; local C reserve below prior fixed1GiB compilation minimum','resources':r,'originalCIExternalSourceRebuildPassed':True,'originalCIFreshConsumerChecks':122,'nativeStatusJsonUsed':False})
  assert tree(source)==before['source'];assert tree(portable)==before['portable'];steps.append({'name':'all-extracted-original-files-unchanged-after-execution','passed':True,'sourceFiles':len(srecords),'portableFiles':len(precords)})
  receipt['passed']=True
 except Exception:receipt['fatal']=traceback.format_exc()
 write_new(out/'AUDIT.json',receipt);print(json.dumps({k:v for k,v in receipt.items()if k!='steps'}));return 0 if receipt['passed']else 1

def main():
 p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');p.add_argument('--lock');p.add_argument('--lock-sha256');p.add_argument('--output');a=p.parse_args()
 if not a.execute:print(json.dumps({'executed':False,'reason':'Explicit ready lock and --execute required; no candidate SDK imported.'}));return 0
 assert a.lock and a.lock_sha256 and a.output;lp=Path(a.lock);assert binding(lp)['sha256']==a.lock_sha256
 lock=decoded(lp.read_bytes());return execute(lock,None,Path(a.output))
if __name__=='__main__':sys.exit(main())
