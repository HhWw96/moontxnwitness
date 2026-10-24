"""Actual-public26-only provider preparation. Never accepts an author checkout."""
from pathlib import Path,PurePosixPath
import argparse,hashlib,json,re,stat,zipfile,sys
VERSION='0.2.6';MODULE='HhWw96/moontxnwitness';REPO='https://github.com/'+MODULE
MAX_ENTRY=32*1024*1024;sha=lambda raw:hashlib.sha256(raw).hexdigest();meta=lambda raw:{'bytes':len(raw),'sha256':sha(raw)}
def safe(name):
 if not isinstance(name,str) or not name or '\\' in name or ':' in name or PurePosixPath(name).is_absolute() or any(x in ('','.','..') for x in name.split('/')):raise ValueError('Unsafe original package path')
 return name
def bounded_file(path,limit):
 p=Path(path)
 if p.is_symlink() or not p.is_file() or p.stat().st_size>limit:raise ValueError('Bounded regular downloaded input required')
 raw=p.read_bytes()
 if len(raw)>limit:raise ValueError('Downloaded input changed beyond byte budget')
 return raw
def frozen_zip(path,prefix=''):
 z=zipfile.ZipFile(path);seen=set();total=0
 for r in z.infolist():
  n=safe(r.filename.rstrip('/'))
  if not n.startswith(prefix) or n.casefold() in seen or stat.S_ISLNK(r.external_attr>>16) or r.flag_bits&1:raise ValueError('Unsafe or duplicate original archive entry')
  seen.add(n.casefold());total+=r.file_size
 if len(seen)>32768 or total>1024*1024*1024:raise ValueError('Archive bounds exceeded')
 return z

def esm_closure(read,entry):
 pending=[entry];seen=set();patterns=[re.compile(r"\b(?:import|export)\s*(?:\{[^}]*\}|[\w*$,\s]+)\s*from\s*['\"]([^'\"]+)['\"]"),re.compile(r"\bimport\s*['\"]([^'\"]+)['\"]")]
 while pending:
  name=pending.pop()
  if name in seen:continue
  seen.add(name);text=read(name).decode('utf8')
  if re.search(r'\bimport\s*\(',text):raise ValueError('Changed dynamic-import closure requires review')
  for target in sum([p.findall(text) for p in patterns],[]):
   if target.startswith('node:'):continue
   if not target.startswith('./') or not target.endswith('.mjs'):raise ValueError('Unreviewed ESM dependency')
   pending.append(safe((PurePosixPath(name).parent/target[2:]).as_posix()))
 return sorted(seen)

def load_bindings(path,expected_sha256,expected_source):
 if sys.flags.optimize:raise ValueError('Optimized Python assertions are forbidden')
 if not re.fullmatch('[0-9a-f]{64}',expected_sha256) or expected_sha256=='0'*64:raise ValueError('Exact external asset-bindings SHA required')
 if not re.fullmatch('[0-9a-f]{40}',expected_source) or expected_source=='0'*40:raise ValueError('Exact externally confirmed source commit required')
 raw=bounded_file(path,65536)
 if sha(raw)!=expected_sha256:raise ValueError('External asset bindings differ')
 value=json.loads(raw)
 if set(value)!={'format','version','sourceCommit','assets'} or value['format']!='moontxnwitness-public-assets/v1' or value['version']!=VERSION or value['sourceCommit']!=expected_source:raise ValueError('Unsupported external asset binding contract')
 names={f'MoonTxnWitness-v{VERSION}-source.zip',f'MoonTxnWitness-v{VERSION}-portable.zip',f'MoonTxnWitness-v{VERSION}-SHA256SUMS.txt','registry.zip'}
 if not isinstance(value['assets'],dict) or set(value['assets'])!=names:raise ValueError('All four exact public asset pins required')
 for name,row in value['assets'].items():
  if not isinstance(row,dict) or set(row)!={'bytes','sha256','url'} or type(row['bytes']) is not int or not 0<row['bytes']<=(16*1024*1024 if name=='registry.zip' else 65536 if name.endswith('.txt') else 256*1024*1024) or not isinstance(row['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',row['sha256']) or row['sha256']=='0'*64:raise ValueError('Every public asset requires explicit bounded bytes and SHA')
  url='https://download.mooncakes.io/user/'+MODULE+'/'+VERSION+'.zip' if name=='registry.zip' else REPO+'/releases/download/v'+VERSION+'/'+name
  if row['url']!=url:raise ValueError('Only exact anonymous public release/registry URLs allowed')
 return raw,value

def main():
 a=argparse.ArgumentParser(description=__doc__)
 for n in ['publication-receipt','publisher-upload-reference','transport-receipt','tag-response','expected-source','expected-sums-sha256','asset-bindings','expected-bindings-sha256','source','portable','sums','registry','out']:a.add_argument('--'+n,required=True)
 v=a.parse_args();external_raw,external=load_bindings(v.asset_bindings,v.expected_bindings_sha256,v.expected_source);out=Path(v.out).resolve()
 if out.exists():raise ValueError('Never overwrite an original provider')
 if not re.fullmatch('[0-9a-f]{40}',v.expected_source) or not re.fullmatch('[0-9a-f]{64}',v.expected_sums_sha256):raise ValueError('Exact independently recorded source and sums SHA required')
 publication_raw=bounded_file(v.publication_receipt,4*1024*1024);publication=json.loads(publication_raw);upload_raw=bounded_file(v.publisher_upload_reference,1024*1024);upload=json.loads(upload_raw);transport_raw=bounded_file(v.transport_receipt,4*1024*1024);transport=json.loads(transport_raw);tag_raw=bounded_file(v.tag_response,1024*1024);tag=json.loads(tag_raw)
 assert publication['passed'] and publication['version']==VERSION and publication['account']=='HhWw96'
 assert publication['github']['repository']==REPO and publication['github']['release']==REPO+'/releases/tag/v'+VERSION
 assert publication['github']['ci']['headSha']==v.expected_source and publication['github']['ci']['conclusion']=='success' and publication['github']['ci']['linuxNativeExecuted']
 assert publication['github']['postgresCi']['sourceCommit']==v.expected_source and publication['github']['postgresCi']['conclusion']=='success'
 assert tag['ref']=='refs/tags/v'+VERSION and tag['object']['type']=='commit' and tag['object']['sha']==v.expected_source
 assert transport['passed'] and transport['expectedSourceCommit']==v.expected_source and transport['authorizationHeaderSentForPublicDownloads'] is False and transport['cookieHeaderSentForPublicDownloads'] is False
 assets={r['name']:r for r in publication['github']['assets']};expected_names={f'MoonTxnWitness-v{VERSION}-{k}.zip' for k in ['source','portable']};assert set(assets)==expected_names
 packages={};downloads={r['file']:r for r in transport['downloads']}
 for kind in ['source','portable']:
  name=f'MoonTxnWitness-v{VERSION}-{kind}.zip';r=assets[name];raw=bounded_file(getattr(v,kind),256*1024*1024);assert len(raw)<=256*1024*1024
  assert r['anonymousDownload'] and r['url']==REPO+'/releases/download/v'+VERSION+'/'+name and meta(raw)=={k:r[k] for k in ['bytes','sha256']}
  assert downloads[name]['anonymous'] and downloads[name]['sha256']==sha(raw) and downloads[name]['bytes']==len(raw)
  assert meta(raw)=={k:external['assets'][name][k] for k in ['bytes','sha256']} and r['url']==external['assets'][name]['url']
  packages[kind]={'name':name,**r}
 sums=bounded_file(v.sums,65536);assert meta(sums)=={k:external['assets'][f'MoonTxnWitness-v{VERSION}-SHA256SUMS.txt'][k] for k in ['bytes','sha256']} and sha(sums)==v.expected_sums_sha256 and len(sums)<=65536
 if b'\r\n' in sums:assert sums.count(b'\n')==sums.count(b'\r\n'),'Mixed checksum line endings are forbidden'
 normalized=sums.replace(b'\r\n',b'\n');assert b'\r' not in normalized and normalized.endswith(b'\n')
 rows={}
 for line in normalized.decode('ascii').splitlines():
  h,n=line.split('  ',1);assert re.fullmatch('[0-9a-f]{64}',h) and n not in rows;rows[n]=h
 assert rows=={n:r['sha256'] for n,r in assets.items()}
 sum_name=f'MoonTxnWitness-v{VERSION}-SHA256SUMS.txt';assert downloads[sum_name]['sha256']==sha(sums) and downloads[sum_name]['bytes']==len(sums)
 cakes=publication['mooncakes'];registry=bounded_file(v.registry,16*1024*1024);assert meta(registry)=={k:cakes[k] for k in ['bytes','sha256']}=={k:external['assets']['registry.zip'][k] for k in ['bytes','sha256']}
 assert cakes['module']==MODULE and cakes['version']==VERSION and cakes['download']=='https://download.mooncakes.io/user/'+MODULE+'/'+VERSION+'.zip'
 assert cakes['uploadedBytesMatchPublicDownload'] and cakes['registryOnlyConsumer']['passed'] and cakes['registryOnlyConsumer']['workspaceOverride'] is False
 assert upload['version']==VERSION and upload['sourceCommit']==v.expected_source and upload['actualUploadedSha256']==cakes['sha256'] and upload['actualUploadedBytes']==cakes['bytes'] and upload['recordedBeforePublicDownload']
 assert downloads['registry.zip']['sha256']==cakes['sha256'] and downloads['registry.zip']['bytes']==cakes['bytes']
 prefix=f'MoonTxnWitness-v{VERSION}/';portable=frozen_zip(v.portable,prefix);source=frozen_zip(v.source,prefix);reg=frozen_zip(v.registry)
 saved={}
 def save(name,raw):
  safe(name)
  if len(raw)>MAX_ENTRY:raise ValueError('Provider entry byte budget exceeded')
  if name in saved:assert saved[name]==raw
  saved[name]=raw;return raw
 def read(name):
  n=prefix+safe(name);r=portable.getinfo(n);assert not r.is_dir() and r.file_size<=MAX_ENTRY;return portable.read(r)
 def public(name):return save('package/'+safe(name),read(name))
 # Bind every native registry source file to the independently downloaded source archive.
 source_matches=0
 for r in reg.infolist():
  if r.is_dir():continue
  name=safe(r.filename);assert r.file_size<=MAX_ENTRY and reg.read(r)==source.read(prefix+name);source_matches+=1
 assert source_matches>0
 runtime={}
 def runtime_read(name):
  raw=read('dist/'+safe(name));save('runtime/'+name,raw);runtime[name]=meta(raw);return raw
 # Preserve every original portable dist file, including non-static fixed workers/resources.
 dist_names=[]
 for item in portable.infolist():
  if item.is_dir() or not item.filename.startswith(prefix+'dist/'):continue
  name=safe(item.filename[len(prefix+'dist/'):]);dist_names.append(name);runtime_read(name)
 assert len(dist_names)==len(set(dist_names)) and sum(x['bytes'] for x in runtime.values())<=128*1024*1024
 full=sorted(set(esm_closure(runtime_read,'sdk.mjs')+esm_closure(runtime_read,'evidence.mjs')))
 model_minimum=esm_closure(runtime_read,'classification-models.mjs');assert model_minimum==['classification-models.mjs','core.mjs']
 minimum=esm_closure(runtime_read,'classification.mjs');orm_minimum=esm_closure(runtime_read,'orm-profile.mjs')
 for version,kind in [('0.2.4','moontxnwitness-frozen-orm-runtime/v1'),('0.2.5','moontxnwitness-frozen-public-runtime/v1')]:
  folder='legacy/v'+version.replace('.','')+'/'
  legacy=json.loads(runtime_read(folder+'manifest.json'));assert legacy['format']==kind and legacy['version']==version
  assert isinstance(legacy['files'],dict) and 0<len(legacy['files'])<=128
  for n,row in legacy['files'].items():assert meta(runtime_read(folder+safe(n)))==row
 for n in ['legacy-v025.mjs','legacy-v025-runtime.mjs','legacy-v025-worker.mjs','legacy-v025-binding.mjs','build-manifest.json','THIRD_PARTY_NOTICES.txt']:assert n in runtime
 save('runtime/LICENSE',read('LICENSE'));runtime['LICENSE']=meta(saved['runtime/LICENSE'])
 build=json.loads(saved['runtime/build-manifest.json']);assert build['version']==VERSION and runtime['core.mjs']['sha256']==build['coreSha256'] and runtime['capture-core.mjs']['sha256']==build['captureCoreSha256']
 old=json.loads(public('fixtures/compat-v025/manifest.json'));assert old['actualPublishedProducer'] and old['producerEngineVersion']=='0.2.5' and len(old['cases'])==21
 cases=[]
 for row in old['cases']:
  name='fixtures/compat-v025/'+safe(row['input']['file']);raw=public(name);assert meta(raw)=={k:row['input'][k] for k in ['bytes','sha256']}
  cases.append({**row,'inputPath':name,'preservedPriorInputOrigin':row['inputOrigin'],'inputReusedFromVersion':'0.2.5','databaseExecutedAs26':False})
 model_root='fixtures/classification-models-v3/'
 model_manifest=json.loads(public(model_root+'manifest.json'));assert model_manifest['format']=='moontxnwitness-model-host-fixtures/v1' and model_manifest['newDatabaseExecution'] is False
 model_origins={}
 for group in ['syntheticCases','retainedCollectorCases','frozenG1bCases']:
  for name,row in model_manifest[group].items():
   path=model_root+safe(name)+'.json';assert meta(public(path))=={k:row[k] for k in ['bytes','sha256']};model_origins[path]={'kind':group,'originalOrigin':row['origin']}
 specs=[('model-empty-default','empty-register',{}),('model-empty-pl1','empty-register',{'models':['adya-pl-1-v1']}),('model-list-skew','list-skew',{}),('model-internal','own-internal',{}),('model-strict-bound','strict-bound-synthetic',{}),('model-strict-equal','strict-equal-synthetic',{}),('model-g1a','g1b/dirty-final-source-keeps-G1a-without-false-G1b',{}),('model-g1b','g1b/intermediate-last-append-positive-control',{}),('model-source-gap','g1b/list-external-abort-b',{}),('model-relation-unsupported','relation-unsupported',{}),('model-zero-budget','list-skew',{'maxStates':0,'maxEdgeChecks':0}),('model-retained-lost-commit','retained-lost-commit-sync',{})]
 model_cases=[{'name':name,'inputPath':model_root+file+'.json','options':options,'origin':model_origins[model_root+file+'.json']} for name,file,options in specs]
 for name,file in [('model-g0','g0'),('model-register-g2','source-closed-noisy-g2')]:
  path='fixtures/classification-v3/'+file+'.json';public(path);model_cases.append({'name':name,'inputPath':path,'options':{},'origin':{'kind':'published-synthetic-register-source','actualPostgresAnomaly':False}})
 assert len(model_cases)==14
 for name,raw in [('publication.json',publication_raw),('publisher-upload.json',upload_raw),('transport.json',transport_raw),('tag-response.json',tag_raw)]:save('origin/'+name,raw)
 save('origin/external-asset-bindings.json',external_raw)
 provider={'format':'moontxnwitness-v026-provider/v1','version':VERSION,'sourceCommit':v.expected_source,'actualPublishedProducer':True,'authorDistRead':False,'headerRewriting':False,'runtimeDirectory':'runtime','packageDirectory':'package','runtime':runtime,'fullSdkEsmFiles':full,'minimalCategoryReplayFiles':minimum,'minimalOrmEsmReplayFiles':orm_minimum,'rawEsmIdentityPreserved':True,'buildManifest':build,'existingCases':cases,'modelCases':model_cases,'existingFamilies':21,'plannedModelCases':14,'plannedTotalCases':35,'minimalModelReplayFiles':model_minimum,'entirePublicDistPreserved':True,'externalBindingsSha256':sha(external_raw),'publicPackages':packages,'checksumAsset':{'name':sum_name,**meta(sums)},'registryPackage':{k:cakes[k] for k in ['download','bytes','sha256']},'registrySourceFilesCompared':source_matches,'publicationReceiptSha256':sha(publication_raw),'publisherReferenceSha256':sha(upload_raw),'transportReceiptSha256':sha(transport_raw),'actualDatabaseExecutedHere':False,'compilerExecutedHere':False,'bindings':{n:meta(r) for n,r in saved.items()}}
 out.mkdir(parents=True,exist_ok=False)
 for name,raw in saved.items():
  path=out/name;path.parent.mkdir(parents=True,exist_ok=True)
  with path.open('xb') as f:assert f.write(raw)==len(raw)
 (out/'provider.json').write_text(json.dumps(provider,indent=2)+'\n',encoding='utf8',newline='\n')
 print(json.dumps({'prepared':True,'version':VERSION,'actualPublishedProducer':True,'plannedCases':35,'providerSha256':sha((out/'provider.json').read_bytes()),'authorDistRead':False,'compilerExecuted':False,'actualDatabaseExecution':False}))
if __name__=='__main__':main()
