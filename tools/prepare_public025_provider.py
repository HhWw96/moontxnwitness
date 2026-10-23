"""Actual-public25-only provider preparation. Never accepts an author checkout."""
from pathlib import Path,PurePosixPath
import argparse,hashlib,json,re,stat,zipfile
VERSION='0.2.5';MODULE='HhWw96/moontxnwitness';REPO='https://github.com/'+MODULE
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

def main():
 a=argparse.ArgumentParser(description=__doc__)
 for n in ['publication-receipt','publisher-upload-reference','transport-receipt','tag-response','expected-source','expected-sums-sha256','source','portable','sums','registry','out']:a.add_argument('--'+n,required=True)
 v=a.parse_args();out=Path(v.out).resolve()
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
  packages[kind]={'name':name,**r}
 sums=bounded_file(v.sums,65536);assert sha(sums)==v.expected_sums_sha256 and len(sums)<=65536
 if b'\r\n' in sums:assert sums.count(b'\n')==sums.count(b'\r\n'),'Mixed checksum line endings are forbidden'
 normalized=sums.replace(b'\r\n',b'\n');assert b'\r' not in normalized and normalized.endswith(b'\n')
 rows={}
 for line in normalized.decode('ascii').splitlines():
  h,n=line.split('  ',1);assert re.fullmatch('[0-9a-f]{64}',h) and n not in rows;rows[n]=h
 assert rows=={n:r['sha256'] for n,r in assets.items()}
 sum_name=f'MoonTxnWitness-v{VERSION}-SHA256SUMS.txt';assert downloads[sum_name]['sha256']==sha(sums) and downloads[sum_name]['bytes']==len(sums)
 cakes=publication['mooncakes'];registry=bounded_file(v.registry,16*1024*1024);assert meta(registry)=={k:cakes[k] for k in ['bytes','sha256']}
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
 full=sorted(set(esm_closure(runtime_read,'sdk.mjs')+esm_closure(runtime_read,'evidence.mjs')))
 minimum=esm_closure(runtime_read,'classification.mjs');assert minimum==['classification.mjs','core.mjs']
 orm_minimum=esm_closure(runtime_read,'orm-profile.mjs')
 # Retain the already-published fixed public24 resources unchanged, never derive new CJS.
 legacy=json.loads(runtime_read('legacy/v024/manifest.json'))
 assert legacy['format']=='moontxnwitness-frozen-orm-runtime/v1' and legacy['version']=='0.2.4'
 for n,r in legacy['files'].items():assert meta(runtime_read('legacy/v024/'+safe(n)))==r
 for n in ['build-manifest.json','THIRD_PARTY_NOTICES.txt']:runtime_read(n)
 save('runtime/LICENSE',read('LICENSE'));runtime['LICENSE']=meta(saved['runtime/LICENSE'])
 build=json.loads(saved['runtime/build-manifest.json']);assert build['version']==VERSION and runtime['core.mjs']['sha256']==build['coreSha256'] and runtime['capture-core.mjs']['sha256']==build['captureCoreSha256']
 old=json.loads(public('fixtures/compat-v024/manifest.json'));assert old['actualPublishedProducer'] and old['producerEngineVersion']=='0.2.4' and len(old['cases'])==15
 cases=[]
 for row in old['cases']:
  name='fixtures/compat-v024/'+safe(row['input']['file']);raw=public(name);assert meta(raw)=={k:row['input'][k] for k in ['bytes','sha256']}
  cases.append({**row,'inputPath':name,'preservedPriorInputOrigin':row['inputOrigin'],'inputReusedFromVersion':'0.2.4','databaseExecutedAs25':False})
 category={}
 for n in ['g0','g1c','source-closed-noisy-g2','missing-source']:
  path='fixtures/classification-v3/'+n+'.json';public(path);category[n]=path
 for name,raw in [('publication.json',publication_raw),('publisher-upload.json',upload_raw),('transport.json',transport_raw),('tag-response.json',tag_raw)]:save('origin/'+name,raw)
 provider={'format':'moontxnwitness-v025-provider/v1','version':VERSION,'sourceCommit':v.expected_source,'actualPublishedProducer':True,'authorDistRead':False,'headerRewriting':False,'runtimeDirectory':'runtime','packageDirectory':'package','runtime':runtime,'fullSdkEsmFiles':full,'minimalCategoryReplayFiles':minimum,'minimalOrmEsmReplayFiles':orm_minimum,'rawEsmIdentityPreserved':True,'buildManifest':build,'existingCases':cases,'categoryInputPaths':category,'existingFamilies':15,'plannedCategoryCases':6,'plannedTotalCases':21,'publicPackages':packages,'checksumAsset':{'name':sum_name,**meta(sums)},'registryPackage':{k:cakes[k] for k in ['download','bytes','sha256']},'registrySourceFilesCompared':source_matches,'publicationReceiptSha256':sha(publication_raw),'publisherReferenceSha256':sha(upload_raw),'transportReceiptSha256':sha(transport_raw),'actualDatabaseExecutedHere':False,'compilerExecutedHere':False,'bindings':{n:meta(r) for n,r in saved.items()}}
 out.mkdir(parents=True,exist_ok=False)
 for name,raw in saved.items():
  path=out/name;path.parent.mkdir(parents=True,exist_ok=True)
  with path.open('xb') as f:assert f.write(raw)==len(raw)
 (out/'provider.json').write_text(json.dumps(provider,indent=2)+'\n',encoding='utf8',newline='\n')
 print(json.dumps({'prepared':True,'version':VERSION,'actualPublishedProducer':True,'plannedCases':21,'providerSha256':sha((out/'provider.json').read_bytes()),'authorDistRead':False,'compilerExecuted':False,'actualDatabaseExecution':False}))
if __name__=='__main__':main()
