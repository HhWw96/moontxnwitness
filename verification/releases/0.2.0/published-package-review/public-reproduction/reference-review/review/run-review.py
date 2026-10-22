"""Actual20 independent review. Production imports require root's external SHA."""
from pathlib import Path
from datetime import datetime, timezone
import argparse,hashlib,json,re,subprocess,tempfile
HERE=Path(__file__).resolve().parent
SHA=lambda raw:hashlib.sha256(raw).hexdigest()
HEX=re.compile(r'^[a-f0-9]{64}$')
def safe(root,name):
 root=Path(root).resolve();target=(root/name).resolve()
 assert target.is_relative_to(root) and target!=root,name
 return target
def verify(row,path):
 assert HEX.fullmatch(row['sha256']),str(path)
 raw=Path(path).read_bytes();assert len(raw)==row['bytes'] and SHA(raw)==row['sha256'],str(path)
 return raw
def json_strict(raw):
 def object_pairs(pairs):
  value={}
  for key,item in pairs:
   assert key not in value,'Duplicate JSON key: '+key
   value[key]=item
  return value
 return json.loads(raw,object_pairs_hook=object_pairs)
def validate_engine(value,version):
 source=value['source'];source_map={r['file']:r for r in source['files']}
 assert len(source_map)==len(source['files']) and len(source_map)>2
 assert {'moon.mod','package.json'}.issubset(source_map)
 for name,row in source_map.items():verify(row,safe(source['root'],name))
 assert json_strict(safe(source['root'],'package.json').read_bytes())['version']==version
 names=sorted(['moon.mod']+[n for n in source_map if n.startswith('src/') and (n.endswith('.mbt') or n.endswith('/moon.pkg'))])
 actual=sorted(p.relative_to(Path(source['root'])).as_posix() for p in (Path(source['root'])/'src').rglob('*') if p.is_file() and (p.suffix=='.mbt' or p.name=='moon.pkg'))
 assert names==sorted(['moon.mod']+actual),'Incomplete compilation source list'
 h=hashlib.sha256()
 for name in names:h.update(name.encode()+b'\0');h.update(safe(source['root'],name).read_bytes());h.update(b'\0')
 assert h.hexdigest()==source['sourceFingerprint']
 runtime=value['runtime'];mapping={r['file']:r for r in runtime['files']}
 assert len(mapping)==len(runtime['files'])
 assert {runtime['sdk'],runtime['evidence'],'core.mjs','capture-core.mjs','build-manifest.json','THIRD_PARTY_NOTICES.txt'}.issubset(mapping)
 data={name:verify(row,safe(runtime['root'],name)) for name,row in mapping.items()}
 build=json_strict(data['build-manifest.json']);assert build['version']==version
 assert build['sourceSha256']==source['sourceFingerprint']
 assert build['coreSha256']==mapping['core.mjs']['sha256'] and build['captureCoreSha256']==mapping['capture-core.mjs']['sha256']
 imports=[]
 for name,raw in data.items():
  if not name.endswith('.mjs'):continue
  text=raw.decode('utf-8');assert not re.search(r'\bimport\s*\(',text),'Unbound dynamic import: '+name
  specs=[]
  for line in text.splitlines():
   if re.match(r'^\s*import\b',line):
    match=re.fullmatch(r'''\s*import\s+(?:(?:[^;
]+?)\s+from\s+)?['"]([^'"]+)['"]\s*;?\s*(?://.*)?''',line)
    assert match,'Unreviewed import declaration: '+name
    specs.append(match.group(1))
   elif re.match(r'^\s*export\s*(?:\{|\*)',line):
    match=re.fullmatch(r'''\s*export\s+(?:[^;
]+?)\s+from\s+['"]([^'"]+)['"]\s*;?\s*(?://.*)?''',line)
    if match:specs.append(match.group(1))
    else:assert re.fullmatch(r'\s*export\s*\{[^;\n]*\}\s*;?\s*(?://.*)?',line),'Unreviewed export: '+name
  for spec in specs:
   if spec.startswith('node:'):continue
   assert spec.startswith('.'),'External import: '+spec
   target=safe(runtime['root'],str(Path(name).parent/spec));relative=target.relative_to(Path(runtime['root']).resolve()).as_posix()
   assert relative in mapping,'Unfrozen dependency: '+relative
   imports.append({'from':name,'to':relative})
 return data,{'version':version,'sourceFingerprint':source['sourceFingerprint'],'sourceFiles':len(source_map),'runtimeFiles':len(mapping),'localImports':imports}
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--freeze',type=Path,required=True);parser.add_argument('--freeze-sha256',required=True);parser.add_argument('--preparation-sha256',required=True)
 args=parser.parse_args();runs=HERE/'runs';runs.mkdir(exist_ok=True);output=Path(tempfile.mkdtemp(prefix='actual20-',dir=runs))
 guard={'schema':1,'kind':'actual20-independent-pre-import-guard','createdAt':datetime.now(timezone.utc).isoformat(),'passed':False,'productionImported':False,'actualDatabaseExecution':False,'newCoreBuild':False,'networkUsed':False,'formalPerformanceMeasurement':False,'packagesExecuted':False,'packageReviewPending':True,'checks':[]}
 try:
  assert HEX.fullmatch(args.preparation_sha256);raw=(HERE/'preparation-manifest.json').read_bytes();assert SHA(raw)==args.preparation_sha256,'External preparation SHA mismatch'
  prepared=json_strict(raw);assert prepared['actual20Executed'] is False and prepared['SDKImported'] is False
  for row in prepared['files']:verify(row,safe(HERE,row['file']))
  guard['checks'].append({'name':'all-prepared-code-inputs-old-receipts-and-oracle-bytes','passed':True,'files':len(prepared['files'])})
  assert HEX.fullmatch(args.freeze_sha256);raw=args.freeze.read_bytes();assert SHA(raw)==args.freeze_sha256,'External root freeze SHA mismatch'
  frozen=json_strict(raw);assert frozen['schema']==1 and frozen['kind']=='root-frozen-actual20-independent-review-input'
  assert frozen['executeReview'] is True and frozen['authorizationSignal']=='actual-0.2.0-frozen-by-root' and frozen['expectedVersion']=='0.2.0'
  assert frozen['source']['sourceFingerprint']=='d3adf5c906b27f2414344acef8be963f2bccb07310cebe487c9ddd14135b4b57','Only root-frozen actual20 is accepted as current'
  stable_runtime={r['file']:r for r in frozen['runtime']['files']}
  assert stable_runtime['core.mjs']['sha256']=='2a6d2055a0127a0dab486389bbe169b97fc9ba50de2722400c521a1ffc915681'
  assert stable_runtime['capture-core.mjs']['sha256']=='60da31aafe9d8fb034289d6deb132c36eb61cb021bf3bc0668401e27987bf5ee'
  assert frozen['performanceAuthorized'] is False and frozen['stableBuildPerformanceMeasured'] is False
  baseline=json_strict((HERE/'baseline17-binding.json').read_bytes());assert baseline['version']=='0.1.7';baseline['source']['root']=frozen['baseline']['sourceRoot'];baseline['runtime']['root']=frozen['baseline']['runtimeRoot']
  prior18=json_strict((HERE/'baseline18-binding.json').read_bytes());assert prior18['version']=='0.1.8';prior18['source']['root']=frozen['additionalBaseline18']['sourceRoot'];prior18['runtime']['root']=frozen['additionalBaseline18']['runtimeRoot'];assert frozen['additionalBaseline18']['sourceFingerprint']==prior18['source']['sourceFingerprint']
  _,prior18_summary=validate_engine(prior18,'0.1.8')
  old_data,old_summary=validate_engine(baseline,'0.1.7');new_data,new_summary=validate_engine(frozen,'0.2.0')
  old_sources={r['file']:r for r in baseline['source']['files']};new_sources={r['file']:r for r in frozen['source']['files']}
  assert old_sources['src/parse_optimized.mbt']['sha256']==new_sources['src/parse_optimized.mbt']['sha256'],'Production parser must exactly match frozen17'
  prior18_sources={r['file']:r for r in prior18['source']['files']};assert new_sources['src/performance_ascii_symbol_wbtest.mbt']['sha256']==prior18_sources['src/performance_ascii_symbol_wbtest.mbt']['sha256']=='4e54d2312ac71c3206cde501e3f4796b0650f79a13f0fc795d24177388c36551'
  guard['checks'].append({'name':'frozen-stable18-producer-full-source-runtime-closure','passed':True,**prior18_summary})
  guard['stableBuild']=True;guard['priorExperimentalSourceAccepted']=False
  guard['checks'].extend([{'name':'frozen17-full-source-runtime-and-dependency-closure','passed':True,**old_summary},{'name':'actual20-full-source-runtime-and-dependency-closure','passed':True,**new_summary}])
  assert frozen['packages']==[],'This semantic phase does not claim package review; package consumers are separate'
  oracle=json_strict((HERE/'oracle15/build-manifest.json').read_bytes());assert oracle['version']=='0.1.5';assert oracle['coreSha256']==SHA((HERE/'oracle15/core.mjs').read_bytes())=='a42c29e0ffcb516d6b6cd84ee273d50aa99ad6c989ad4d3e6f97d6c433ec0cef'
  oracle_text=(HERE/'oracle15/core.mjs').read_text(encoding='utf-8');assert not re.search(r'''(?m)^\s*import|^\s*export[^;
]*from\s*['"]|import\s*\(''',oracle_text),'Legacy oracle has unbound imports'
  for label,data in [('baseline17',old_data),('runtime',new_data)]:
   for name,raw in data.items():
    target=safe(output/label,name);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw);assert target.read_bytes()==raw
  guard.update(passed=True,rootFreezeSha256=args.freeze_sha256,preparationManifestSha256=args.preparation_sha256,rootFreezeFile=str(args.freeze.resolve()),expectedVersion='0.2.0',runtimeRoot=str(output/'runtime'),runtimeFiles=frozen['runtime']['files'],sdk=frozen['runtime']['sdk'],evidence=frozen['runtime']['evidence'],baselineRuntimeRoot=str(output/'baseline17'),baselineRuntimeFiles=baseline['runtime']['files'],baselineSdk=baseline['runtime']['sdk'],baselineEvidence=baseline['runtime']['evidence'],sourceFingerprint=frozen['source']['sourceFingerprint'],sourceRuntimeCopiedOnlyAfterBothGuards=True)
 except Exception as error:guard.update(errorClass=type(error).__name__,error=str(error))
 target=output/'preflight.json';target.write_text(json.dumps(guard,indent=2)+'\n',encoding='utf-8')
 if not guard['passed']:
  print(json.dumps({'passed':False,'productionImported':False,'preflight':str(target),'error':guard.get('error')}));return 1
 result=subprocess.run([frozen.get('nodeExecutable','node'),str(HERE/'run-tests.mjs'),'--preflight',str(target),'--preflight-sha256',SHA(target.read_bytes())],capture_output=True,text=True,encoding='utf-8',timeout=1200)
 (output/'stdout.log').write_text(result.stdout,encoding='utf-8');(output/'stderr.log').write_text(result.stderr,encoding='utf-8')
 post={'schema':1,'passed':False,'productionReexecuted':False}
 try:
  _,before=validate_engine(baseline,'0.1.7');_,after=validate_engine(frozen,'0.2.0');_,prior18_after=validate_engine(prior18,'0.1.8')
  for row in prepared['files']:verify(row,safe(HERE,row['file']))
  assert SHA(args.freeze.read_bytes())==args.freeze_sha256
  post.update(passed=True,baseline17=before,actual20=after,stable18Producer=prior18_after,allPreparedInputsUnchanged=True,originalRootFreezeUnchanged=True)
 except Exception as error:post.update(errorClass=type(error).__name__,error=str(error))
 (output/'post-preservation.json').write_text(json.dumps(post,indent=2)+'\n',encoding='utf-8')
 print(result.stdout,end='');print(result.stderr,end='');return result.returncode if post['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
