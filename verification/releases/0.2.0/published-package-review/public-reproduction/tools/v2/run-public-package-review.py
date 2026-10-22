"""Immutable public-package review: no network or product code runs on import.
Only main(), after root's externally hashed real publication bindings, downloads.
No package is rebuilt; source wrappers use that version's public portable core.
"""
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
import argparse, hashlib, json, os, re, shutil, stat, struct, subprocess, sys, tempfile, time, traceback, unicodedata, urllib.request, urllib.parse, zipfile
HERE=Path(__file__).resolve().parent
HEX=re.compile(r'^[0-9a-f]{64}$');COMMIT=re.compile(r'^[0-9a-f]{40}$')
SHA=lambda b:hashlib.sha256(b).hexdigest()
REPO='https://github.com/HhWw96/moontxnwitness'
API='https://api.github.com/repos/HhWw96/moontxnwitness'
VERSIONS=('0.1.7','0.1.8','0.2.0')
MAX_ARCHIVE_BYTES=2*1024**3;MAX_MANIFEST_BYTES=1024**2
MAX_MEMBERS=65534;MAX_DIRECTORY_BYTES=64*1024**2;MAX_SELECTED_BYTES=64*1024**2;MAX_TOTAL_UNCOMPRESSED=8*1024**3
MAX_REDIRECTS=5;DOWNLOAD_SECONDS=900;CHUNK=1024**2
ALLOWED_HOSTS={'github.com','api.github.com','release-assets.githubusercontent.com','objects.githubusercontent.com'}
RESERVED=re.compile(r'^(?:CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\.|$)',re.I)

def strict(raw):
 def pairs(items):
  obj={}
  for k,v in items:
   assert k not in obj,'Duplicate JSON key: '+k
   obj[k]=v
  return obj
 return json.loads(raw,object_pairs_hook=pairs)
def dump(path,value):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def hashed_file(path):
 h=hashlib.sha256();count=0
 with Path(path).open('rb') as f:
  for chunk in iter(lambda:f.read(CHUNK),b''):h.update(chunk);count+=len(chunk)
 return {'bytes':count,'sha256':h.hexdigest()}
def safe(root,name):
 root=Path(root).resolve();p=(root/name).resolve();assert p.is_relative_to(root) and p!=root
 return p
def check_bound(path,sha):
 assert HEX.fullmatch(sha);raw=Path(path).read_bytes();assert SHA(raw)==sha,'External file SHA mismatch';return raw
def prepared(sha):
 raw=check_bound(HERE/'preparation-manifest.json',sha);m=strict(raw)
 assert m['networkExecuted'] is False and m['SDKImported'] is False
 for row in m['files']:
  b=safe(HERE,row['file']).read_bytes();assert len(b)==row['bytes'] and SHA(b)==row['sha256'],row['file']
 return m

def url_allowed(url):
 p=urllib.parse.urlsplit(url)
 assert p.scheme=='https' and p.hostname in ALLOWED_HOSTS and p.port in (None,443) and p.username is None and p.password is None and not p.fragment
 return p
class RestrictedRedirect(urllib.request.HTTPRedirectHandler):
 def __init__(self):self.redirects=0
 def redirect_request(self,req,fp,code,msg,headers,newurl):
  url_allowed(newurl);self.redirects+=1;assert self.redirects<=MAX_REDIRECTS
  out=super().redirect_request(req,fp,code,msg,headers,newurl)
  assert not any(k.lower() in ('authorization','cookie','proxy-authorization') for k in out.headers)
  return out

def download(url,dest,receipt,limit,expected=None):
 url_allowed(url);dest=Path(dest);dest.parent.mkdir(parents=True,exist_ok=True);part=dest.with_name(dest.name+'.partial');assert not dest.exists() and not part.exists()
 row={'url':url,'anonymousRequest':True,'authorizationHeaderUsed':False,'cookieJarUsed':False,'environmentProxyUsed':False,'automaticRetries':0,'passed':False};receipt['downloads'].append(row);receipt['networkExecuted']=True
 request=urllib.request.Request(url,headers={'User-Agent':'MoonTxnWitness-independent-published-package-review/1','Accept':'application/vnd.github+json' if urllib.parse.urlsplit(url).hostname=='api.github.com' else 'application/octet-stream'})
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),RestrictedRedirect());h=hashlib.sha256();count=0;start=time.monotonic()
 try:
  with opener.open(request,timeout=30) as response,part.open('xb') as out:
   final=url_allowed(response.geturl());row.update(finalHost=final.hostname,finalPath=final.path,finalQueryOmitted=bool(final.query),httpStatus=response.status)
   assert response.status==200
   length=response.headers.get('Content-Length')
   if length is not None:assert int(length)<=limit and (expected is None or int(length)==expected['bytes'])
   while True:
    assert time.monotonic()-start<=DOWNLOAD_SECONDS,'Bounded download time exceeded'
    block=response.read(CHUNK)
    if not block:break
    count+=len(block);assert count<=limit and (expected is None or count<=expected['bytes']),'Download byte budget exceeded'
    out.write(block);h.update(block)
  row.update(bytes=count,sha256=h.hexdigest())
  if expected:assert row['sha256']==expected['sha256'] and count==expected['bytes'],'Anonymous bytes differ from publisher receipts'
  part.replace(dest);row['passed']=True;return row
 except Exception:
  row.update(bytes=count,partialSha256=h.hexdigest(),partialRetained=part.exists());raise

def receipts_for(config,version,config_dir):
 c=config['releases'][version];assert COMMIT.fullmatch(c['sourceCommit'])
 receipts={}
 for k in ('publicationReceipt','publisherPackageReceipt'):
  p=Path(c[k]['file']);p=p if p.is_absolute() else config_dir/p
  receipts[k]={'raw':check_bound(p,c[k]['sha256']),'sha256':c[k]['sha256']}
 pub=strict(receipts['publicationReceipt']['raw']);pkg=strict(receipts['publisherPackageReceipt']['raw'])
 for r in (pub,pkg):assert r['tool']=='MoonTxnWitness' and r['version']==version and r['passed'] is True
 assert pub['account']=='HhWw96' and pub['github']['repository']==REPO and pub['github']['release']==REPO+'/releases/tag/v'+version
 assert pkg['sourceRebuilt'] is True and type(pkg['freshConsumerChecks']) is int and pkg['freshConsumerChecks']>0
 assets=pub['github']['assets'];archives=pkg['archives'];assert len(assets)==len(archives)==2
 by_name={r['file']:r for r in archives};assert len(by_name)==2
 expected={}
 for kind in ('source','portable'):
  name='MoonTxnWitness-v'+version+'-'+kind+'.zip';matches=[r for r in assets if r['name']==name];assert len(matches)==1
  a=matches[0];r=by_name[name];assert a['anonymousDownload'] is True and a['url']==REPO+'/releases/download/v'+version+'/'+name
  assert a['sha256']==r['sha256'] and HEX.fullmatch(a['sha256']) and a['bytes']==r['bytes'] and type(a['bytes']) is int and 0<a['bytes']<=MAX_ARCHIVE_BYTES
  expected[kind]={'name':name,'url':a['url'],'sha256':a['sha256'],'bytes':a['bytes']}
 ci=pub['github']['ci'];assert ci['conclusion']=='success' and ci['headSha']==c['sourceCommit'] and ci['linuxNativeExecuted'] is True
 assert len(ci['jobs'])==2 and {r['name'] for r in ci['jobs']}=={'verify (ubuntu-24.04)','verify (windows-2022)'} and all(r['conclusion']=='success' for r in ci['jobs'])
 pg=pub['github']['postgresCi'];assert pg['conclusion']=='success' and pg['actualDatabaseExecution'] is True
 for k in ('headSha','sourceCommit','workflowCommit'):assert pg[k]==c['sourceCommit']
 return {'version':version,'commit':c['sourceCommit'],'expected':expected,'receipts':receipts,'publisherFreshConsumerChecks':pkg['freshConsumerChecks'],'publisherSourceRebuilt':True}

def tag_anchor(release,work,receipt):
 version=release['version'];path=work/'tag-ref.json';url=API+'/git/ref/tags/v'+version
 download(url,path,receipt,MAX_MANIFEST_BYTES);ref=strict(path.read_bytes());assert ref['ref']=='refs/tags/v'+version
 obj=ref['object'];chain=[]
 for depth in range(4):
  assert COMMIT.fullmatch(obj['sha']);chain.append({'type':obj['type'],'sha':obj['sha']})
  if obj['type']=='commit':assert obj['sha']==release['commit'];return chain
  assert obj['type']=='tag' and depth<3
  path=work/('annotated-tag-'+str(depth)+'.json');download(API+'/git/tags/'+obj['sha'],path,receipt,MAX_MANIFEST_BYTES);tag=strict(path.read_bytes());assert tag['sha']==obj['sha'];obj=tag['object']
 raise AssertionError('Tag chain has no expected exact commit')

def directory_bound(path):
 # Bound allocations before ZipFile parses any central-directory entry.
 size=Path(path).stat().st_size
 assert 22<=size<=MAX_ARCHIVE_BYTES
 with Path(path).open('rb') as stream:
  stream.seek(max(0,size-65557));tail=stream.read(min(size,65557));at=tail.rfind(b'PK\x05\x06');assert at>=0 and len(tail)-at>=22
  signature,disk,cd_disk,disk_entries,entries,cd_size,cd_start,comment=struct.unpack('<4s4H2LH',tail[at:at+22]);end=size-len(tail)+at
  assert at+22+comment==len(tail),'Noncanonical ZIP end/comment range'
  assert disk==cd_disk==0 and disk_entries==entries,'Multi-volume ZIP is unsupported'
  assert entries!=65535 and cd_size!=0xffffffff and cd_start!=0xffffffff,'ZIP64 is outside the bounded publication profile'
  assert 0<entries<=MAX_MEMBERS and cd_size<=MAX_DIRECTORY_BYTES
  assert cd_start+cd_size==end and cd_start<=size,'Noncanonical central-directory range'
  return entries

def scan_zip(z,root):
 infos=z.infolist();assert 0<len(infos)<=MAX_MEMBERS
 exact={};aliases={};prefixes={};files=set();directories=set();total=0;inventory=[]
 for info in infos:
  name=info.filename;assert info.orig_filename==name and name and '\\' not in name and '\x00' not in name and ':' not in name and not name.startswith('/')
  assert len(name.encode('utf-8'))<=4096 and not any(ord(c)<32 or ord(c)==127 or c in '<>\"|?*' for c in name),'Windows-invalid archive member'
  directory=info.is_dir();bare=name[:-1] if directory else name;parts=bare.split('/')
  assert parts[0]==root and len(parts)<=64 and all(p not in ('','.','..') and p==p.rstrip(' .') and not RESERVED.match(p) for p in parts)
  assert len(parts)>1 or directory
  assert all(len(p.encode('utf-8'))<=255 for p in parts),'Path component byte budget'
  assert name not in exact,'Duplicate archive member';exact[name]=info
  canonical='/'.join(unicodedata.normalize('NFC',p).casefold() for p in parts)
  assert canonical not in aliases,'Casefold/NFC member alias';aliases[canonical]=name
  for i in range(1,len(parts)+1):
   spelling='/'.join(parts[:i]);key='/'.join(unicodedata.normalize('NFC',p).casefold() for p in parts[:i]);assert key not in prefixes or prefixes[key]==spelling,'Directory-prefix casefold/NFC alias';prefixes[key]=spelling
  mode=info.external_attr>>16;assert stat.S_IFMT(mode) in (0,stat.S_IFREG,stat.S_IFDIR),'Links/special members are forbidden';assert not info.flag_bits&1,'Encrypted member'
  assert not (stat.S_IFMT(mode)==stat.S_IFDIR and not directory) and not (stat.S_IFMT(mode)==stat.S_IFREG and directory),'Directory mode/name mismatch'
  assert not directory or info.file_size==0,'Directory carries payload'
  assert info.file_size>=0 and info.compress_size>=0;total+=info.file_size;assert total<=MAX_TOTAL_UNCOMPRESSED
  (directories if directory else files).add(canonical)
  inventory.append({'member':name,'bytes':info.file_size,'compressedBytes':info.compress_size,'crc32':format(info.CRC,'08x'),'directory':directory})
 for name in files:
  assert name not in directories
  components=name.split('/')
  for i in range(1,len(components)):assert '/'.join(components[:i]) not in files,'File/directory ancestor conflict'
 return exact,inventory,total

def extract_selected(path,release,kind,binding,destination,receipt):
 root='MoonTxnWitness-v'+release['version'];selected={}
 if kind=='source':
  for row in binding['source']['files']:selected[row['file']]={**row,'role':'complete-compilation-source-input'}
  for name in ('sdk.mjs','evidence.mjs'):
   r=next(r for r in binding['runtime']['files'] if r['file']==name);selected['cmd/'+name]={**r,'role':'source-wrapper','file':'cmd/'+name}
 else:
  for row in binding['runtime']['files']:selected['dist/'+row['file']]={**row,'role':'published-portable-runtime','file':'dist/'+row['file']}
 expected_archive=release['expected'][kind];assert hashed_file(path)=={'bytes':expected_archive['bytes'],'sha256':expected_archive['sha256']}
 rows=[]
 count=directory_bound(path)
 with zipfile.ZipFile(path) as z:
  assert len(z.infolist())==count,'Central-directory count mismatch'
  members,inventory,total=scan_zip(z,root)
  if kind=='source':
   listed={n[len(root)+1:] for n in members if n.startswith(root+'/src/') and (n.endswith('.mbt') or n.endswith('/moon.pkg'))}
   expected={r['file'] for r in binding['source']['files'] if r['file'].startswith('src/') and (r['file'].endswith('.mbt') or r['file'].endswith('/moon.pkg'))}
   assert listed==expected,'Source ZIP compilation-input inventory differs from frozen complete source'
  assert sum(row['bytes'] for row in selected.values())<=MAX_SELECTED_BYTES
  for relative,row in selected.items():
   full=root+'/'+relative;assert full in members;info=members[full];assert not info.is_dir() and info.file_size==row['bytes']
   target=safe(destination,relative);target.parent.mkdir(parents=True,exist_ok=True);h=hashlib.sha256();count=0
   with z.open(info,'r') as source,target.open('xb') as out:
    for block in iter(lambda:source.read(CHUNK),b''):
     count+=len(block);assert count<=row['bytes'] and count<=MAX_SELECTED_BYTES;h.update(block);out.write(block)
   assert count==row['bytes'] and h.hexdigest()==row['sha256'],'Selected member differs from frozen source/runtime'
   rows.append({'member':full,'extractedAs':relative,'bytes':count,'sha256':h.hexdigest(),'role':row['role'],'originArchiveSha256':expected_archive['sha256'],'payloadCrcVerifiedByZipReader':True})
 inventory_path=destination.parent/(kind+'-central-directory.json');dump(inventory_path,{'version':release['version'],'variant':kind,'members':inventory,'wholeArchiveSha256':expected_archive['sha256'],'allMemberPayloadsDecompressed':False})
 return {'version':release['version'],'variant':kind,'rootPrefix':root,'archiveSha256':expected_archive['sha256'],'allCentralDirectoryEntriesValidated':True,'centralDirectoryEntries':len(inventory),'declaredUncompressedBytes':total,'selectedCount':len(rows),'selectedBytes':sum(r['bytes'] for r in rows),'allPayloadCrcVerified':False,'selectedPayloadCrcVerified':True,'compilationSourceComplete':kind=='source','members':rows}

def get_release(release,work,binding,receipt):
 work.mkdir();proof=work/'receipts';proof.mkdir()
 for k,r in release['receipts'].items():(proof/(k+'.json')).write_bytes(r['raw'])
 chain=tag_anchor(release,work,receipt)
 sums=work/'SHA256SUMS.txt';download(REPO+'/releases/download/v'+release['version']+'/MoonTxnWitness-v'+release['version']+'-SHA256SUMS.txt',sums,receipt,MAX_MANIFEST_BYTES)
 entries={}
 for line in sums.read_text(encoding='utf-8').splitlines():
  match=re.fullmatch(r'([0-9a-f]{64})  ([^/\\]+)',line);assert match and match[2] not in entries;entries[match[2]]=match[1]
 assert entries=={r['name']:r['sha256'] for r in release['expected'].values()},'Public SHA256SUMS differs from both external publisher receipts'
 extractions={}
 for kind in ('source','portable'):
  asset=release['expected'][kind];p=work/asset['name'];download(asset['url'],p,receipt,MAX_ARCHIVE_BYTES,asset)
  dest=work/('extracted-'+kind);dest.mkdir();extractions[kind]=extract_selected(p,release,kind,binding,dest,receipt)
 record={'version':release['version'],'tagCommit':release['commit'],'anonymousTagChain':chain,'publicationReceiptSha256':release['receipts']['publicationReceipt']['sha256'],'publisherPackageReceiptSha256':release['receipts']['publisherPackageReceipt']['sha256'],'publisherFreshConsumerChecksReferenced':release['publisherFreshConsumerChecks'],'publisherSourceRebuiltReferenced':True,'publisherChecksReexecutedHere':False,'archives':extractions,'publicSumsSha256':SHA(sums.read_bytes())};dump(work/'release-binding.json',record)
 return {'source':work/'extracted-source','runtime':work/'extracted-portable/dist','binding':record}

def validate_closure(path,lock):
 raw=check_bound(path/'public-closure.json',lock['reviewClosureManifestSha256']);m=strict(raw)
 for row in m['files']:
  b=safe(path,row['file']).read_bytes();assert len(b)==row['bytes'] and SHA(b)==row['sha256'],row['file']
 check_bound(path/'review/preparation-manifest.json',lock['reviewPreparationManifestSha256'])
 check_bound(path/'review/execution-checks.mjs',lock['frozenExecutionModuleSha256']);check_bound(path/'review/run-tests.mjs',lock['frozen105WorkerSha256'])
 return m

def safe_env():
 env=dict(os.environ)
 for k in list(env):
  if k.upper() in ('NODE_OPTIONS','NODE_PATH','PYTHONSTARTUP','PYTHONPATH','PYTHONHOME','PYTHONOPTIMIZE'):env.pop(k)
 env['PYTHONDONTWRITEBYTECODE']='1';return env

def run_variant(kind,work,closure,lock,downloaded,config,outer):
 variant=work/('consumer-'+kind);variant.mkdir();test=variant/'review';test.mkdir();pm=strict((closure/'review/preparation-manifest.json').read_bytes())
 for row in pm['files']:
  raw=safe(closure/'review',row['file']).read_bytes();assert len(raw)==row['bytes'] and SHA(raw)==row['sha256'];p=safe(test,row['file']);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
 (test/'preparation-manifest.json').write_bytes((closure/'review/preparation-manifest.json').read_bytes());check_bound(test/'run-tests.mjs',lock['frozen105WorkerSha256'])
 runtime=downloaded['0.2.0']['runtime'];origins=[]
 if kind=='source':
  runtime=variant/'assembled-runtime';runtime.mkdir()
  for row in lock['versions']['0.2.0']['runtime']['files']:
   wrapper=row['file'] in ('sdk.mjs','evidence.mjs');from_path=(downloaded['0.2.0']['source']/'cmd'/row['file']) if wrapper else (downloaded['0.2.0']['runtime']/row['file']);raw=from_path.read_bytes();assert len(raw)==row['bytes'] and SHA(raw)==row['sha256'];(runtime/row['file']).write_bytes(raw);origins.append({'runtimeFile':row['file'],'archiveVariant':'source' if wrapper else 'portable','member':('cmd/' if wrapper else 'dist/')+row['file'],'sha256':row['sha256']})
 else:
  origins=[{'runtimeFile':r['file'],'archiveVariant':'portable','member':'dist/'+r['file'],'sha256':r['sha256']} for r in lock['versions']['0.2.0']['runtime']['files']]
 frozen=strict((closure/'public-root-freeze.json').read_bytes());frozen['source']['root']=str(downloaded['0.2.0']['source']);frozen['runtime']['root']=str(runtime)
 frozen['baseline']={'sourceRoot':str(downloaded['0.1.7']['source']),'runtimeRoot':str(downloaded['0.1.7']['runtime'])};frozen['additionalBaseline18']={'sourceRoot':str(downloaded['0.1.8']['source']),'runtimeRoot':str(downloaded['0.1.8']['runtime']),'sourceFingerprint':lock['versions']['0.1.8']['source']['sourceFingerprint']};frozen['nodeExecutable']=config['nodeExecutable'];frozen['downloadedPublishedPackageOrigin']=True;frozen['sourceRebuiltHere']=False
 launch=variant/'downloaded-package-freeze.private.json';dump(launch,frozen);raw_launch=launch.read_bytes();env=safe_env();before=set((test/'runs').glob('*')) if (test/'runs').exists() else set()
 outer['runtimeExecutionAttempted']=True;outer['runtimeConsumerAttempts']+=1
 try:
  child=subprocess.run([sys.executable,'-B',str(test/'run-review.py'),'--freeze',str(launch),'--freeze-sha256',SHA(raw_launch),'--preparation-sha256',lock['reviewPreparationManifestSha256']],cwd=variant,env=env,capture_output=True,timeout=1800)
 except subprocess.TimeoutExpired as error:
  for name,raw in [('stdout.private.log',error.stdout),('stderr.private.log',error.stderr)]:
   raw=raw or b'';(variant/name).write_bytes(raw.encode('utf-8') if isinstance(raw,str) else raw)
  raise
 (variant/'stdout.private.log').write_bytes(child.stdout);(variant/'stderr.private.log').write_bytes(child.stderr);after=set((test/'runs').glob('*')) if (test/'runs').exists() else set();assert len(after-before)==1;result=next(iter(after-before));r=strict((result/'receipt.json').read_bytes());post=strict((result/'post-preservation.json').read_bytes())
 assert child.returncode==0 and r['passed'] is True and r['checkCount']==105 and r['failedCount']==0 and post['passed'] is True
 assert [c['name'] for c in r['checks']]==lock['expectedCheckNames'] and all(c['passed'] is True for c in r['checks'])
 assert r['version']=='0.2.0' and r['sourceSha256']==lock['versions']['0.2.0']['source']['sourceFingerprint']
 runtime_map={row['file']:row for row in lock['versions']['0.2.0']['runtime']['files']};assert r['coreSha256']==runtime_map['core.mjs']['sha256'] and r['captureCoreSha256']==runtime_map['capture-core.mjs']['sha256']
 assert r['actual20RuntimeExecuted'] is True and r['packagesExecuted'] is False and r['formalPerformanceMeasurement'] is False
 check_bound(test/'run-tests.mjs',lock['frozen105WorkerSha256']);validate_closure(closure,lock)
 rows=[]
 for row in lock['versions']['0.2.0']['runtime']['files']:
  raw=(result/'runtime'/row['file']).read_bytes();assert len(raw)==row['bytes'] and SHA(raw)==row['sha256'];rows.append({'file':row['file'],'bytes':len(raw),'sha256':SHA(raw),'loadedFrom':(result/'runtime'/row['file']).relative_to(work).as_posix()})
 record={'variant':kind,'runtimeExecutionConfirmed':True,'executionScope':'source-wrapper+public-portable-core' if kind=='source' else 'portable-sdk+portable-core','passed':True,'checkCount':105,'failedCount':0,'skippedChecks':0,'allOriginal105CheckIdsPreserved':True,'sourceIdentityFromSameVersionPublicSourceArchive':True,'runtimeOrigins':origins,'loadedRuntimeFiles':rows,'semanticReceipt':{'file':(result/'receipt.json').relative_to(work).as_posix(),**hashed_file(result/'receipt.json')},'postPreservation':{'file':(result/'post-preservation.json').relative_to(work).as_posix(),**hashed_file(result/'post-preservation.json')},'privateLaunchSha256':SHA(raw_launch),'sourceRebuilt':False,'newCoreBuild':False,'frozenWorkerPackageFlagRemainsSemanticOnly':True,'outerReceiptSignsAnonymousDownloadedPackageExecution':True};dump(variant/'package-consumer-receipt.json',record);return record

def main():
 if not __debug__:raise RuntimeError('Optimized Python disables required guards; use ordinary python -B')
 parser=argparse.ArgumentParser();parser.add_argument('--preparation-sha256',required=True);parser.add_argument('--configuration',type=Path);parser.add_argument('--configuration-sha256');parser.add_argument('--check-preparation',action='store_true');args=parser.parse_args();prepared(args.preparation_sha256)
 if args.check_preparation:print(json.dumps({'passed':True,'networkExecuted':False,'SDKImported':False}));return 0
 assert args.configuration and args.configuration_sha256;config_raw=check_bound(args.configuration,args.configuration_sha256);config=strict(config_raw);lock=strict((HERE/'dependency-lock.json').read_bytes())
 assert config['schema']==1 and config['kind']=='root-authorized-anonymous-package-independent-review' and config['executePublishedPackageReview'] is True
 assert config['authorizationSignal']=='root-provided-actual20-publication-bindings-complete' and set(config['releases'])==set(VERSIONS)
 releases={v:receipts_for(config,v,args.configuration.resolve().parent) for v in VERSIONS}
 closure=Path(config['reviewClosure']).resolve();validate_closure(closure,lock)
 node=Path(config['nodeExecutable']).resolve();assert node.is_file();config['nodeExecutable']=str(node)
 parent=Path(config['outputParent']).resolve();assert parent.is_dir() and parent.drive.lower()=='d:','New review outputs must stay on D'
 work=Path(tempfile.mkdtemp(prefix='MoonTxnWitness-anonymous-published020-review-',dir=parent));(work/'configuration.private.json').write_bytes(config_raw)
 receipt={'schema':1,'kind':'anonymous-published-package-independent-semantic-review','version':'0.2.0','passed':False,'createdAt':datetime.now(timezone.utc).isoformat(),'configurationSha256':args.configuration_sha256,'runnerPreparationSha256':args.preparation_sha256,'dependencyLockSha256':SHA((HERE/'dependency-lock.json').read_bytes()),'original105WorkerSha256':lock['frozen105WorkerSha256'],'originalIndependent105ReceiptSha256':lock['originalIndependentReceiptSha256'],'reviewClosureManifestSha256':lock['reviewClosureManifestSha256'],'networkExecuted':False,'runtimeExecutionAttempted':False,'runtimeConsumerAttempts':0,'downloads':[],'releaseBindings':[],'consumers':[],'plannedConsumers':2,'expectedGroupsPerConsumer':105,'sourceRebuilt':False,'newCoreBuild':False,'actualDatabaseExecution':False,'fullProductSuiteExecutedHere':False,'formalPerformanceMeasurement':False,'mooncakesDownloadReexecuted':False,'allArchivePayloadsDecompressed':False,'native18CapsuleOrigin':'prepublication-regression','native18ProducerPublicBuildIdentityMapped':False,'native18CapsulesGeneratedAfterPublication':False,'sourceWrapperUsesPublicPortableCore':True,'authorDistRead':False}
 try:
  ver=subprocess.run([str(node),'--version'],capture_output=True,text=True,check=True,env=safe_env()).stdout.strip();assert re.fullmatch(r'v24\.[0-9]+\.[0-9]+',ver);receipt['node']={'version':ver,**hashed_file(node)}
  downloaded={}
  for version in VERSIONS:
   downloaded[version]=get_release(releases[version],work/('release-'+version),lock['versions'][version],receipt);receipt['releaseBindings'].append(downloaded[version]['binding'])
  receipt['baselines17And18FromOwnAnonymousSourceAndPortablePackages']=True;receipt['native18ProducerPublicBuildIdentityMapped']=True
  for kind in ('source','portable'):
   before_attempts=receipt['runtimeConsumerAttempts']
   try:receipt['consumers'].append(run_variant(kind,work,closure,lock,downloaded,config,receipt))
   except Exception:
    detail=work/('consumer-'+kind+'-first-failure.private.log');detail.write_text(traceback.format_exc(),encoding='utf-8');partial=[]
    for p in (work/('consumer-'+kind)/'review/runs').glob('*/receipt.json'):
     observed=strict(p.read_bytes());partial.append({'file':p.relative_to(work).as_posix(),**hashed_file(p),'observedCheckCount':observed.get('checkCount'),'observedFailedCount':observed.get('failedCount'),'observedPassed':observed.get('passed'),'runtimeExecutionConfirmed':observed.get('actual20RuntimeExecuted') is True and observed.get('checkCount',0)>0})
    receipt['consumers'].append({'variant':kind,'passed':False,'runtimeExecutionAttempted':receipt['runtimeConsumerAttempts']>before_attempts,'runtimeExecutionConfirmed':any(r['runtimeExecutionConfirmed'] for r in partial),'firstFailureFile':detail.name,'firstFailureSha256':SHA(detail.read_bytes()),'retainedSemanticReceipts':partial,'noExpectationsModified':True})
  # Recheck all six original ZIP byte hashes and every selected member after both consumers.
  for version,data in downloaded.items():
   for variant,ext in data['binding']['archives'].items():
    asset=releases[version]['expected'][variant];assert hashed_file(work/('release-'+version)/asset['name'])=={'bytes':asset['bytes'],'sha256':asset['sha256']}
    root=work/('release-'+version)/('extracted-'+variant)
    for row in ext['members']:assert hashed_file(safe(root,row['extractedAs']))=={'bytes':row['bytes'],'sha256':row['sha256']}
  receipt['allSixOriginalArchivesAndSelectedMembersUnchangedAfterConsumers']=True
  validate_closure(closure,lock);prepared(args.preparation_sha256)
  receipt['passed']=len(receipt['consumers'])==2 and all(r['passed'] for r in receipt['consumers']);receipt['allOriginalPreparedInputsUnchanged']=True
 except Exception:
  detail=work/'first-failure.private.log';detail.write_text(traceback.format_exc(),encoding='utf-8');receipt['failure']={'privateDetailFile':detail.name,'sha256':SHA(detail.read_bytes()),'noAutomaticRetryOrPolling':True}
 finally:
  receipt['allConsumersPassed']=len(receipt['consumers'])==2 and all(r['passed'] for r in receipt['consumers'])
  receipt['runtimeConsumersExecuted']=sum(r.get('runtimeExecutionConfirmed',False) is True for r in receipt['consumers']);receipt['bothDownloadedPackageRuntimesExecuted']=receipt['runtimeConsumersExecuted']==2
  receipt['checkCount']=sum(r.get('checkCount',max([p.get('observedCheckCount') or 0 for p in r.get('retainedSemanticReceipts',[])] or [0])) for r in receipt['consumers'])
  receipt['finishedAt']=datetime.now(timezone.utc).isoformat();dump(work/'receipt.json',receipt)
 print(json.dumps({'passed':receipt['passed'],'receipt':str(work/'receipt.json'),'receiptSha256':SHA((work/'receipt.json').read_bytes()),'checkCount':receipt.get('checkCount',0)}));return 0 if receipt['passed'] else 1
def entry():
 try:return main()
 except Exception:
  # Preserve pre-work configuration/receipt failures too; never overwrite attempts.
  parent=HERE/'attempt-failures';parent.mkdir(exist_ok=True);d=Path(tempfile.mkdtemp(prefix='first-',dir=parent));detail=d/'failure.private.log';detail.write_text(traceback.format_exc(),encoding='utf-8');record={'schema':1,'kind':'public-package-entry-first-failure','passed':False,'privateDetailFile':detail.name,'privateDetailSha256':SHA(detail.read_bytes()),'executionState':'No success claimed; inspect retained phase detail','automaticRetryOrPolling':False};dump(d/'receipt.json',record);print(json.dumps({'passed':False,'entryFailure':str(d/'receipt.json')}));return 1
if __name__=='__main__':raise SystemExit(entry())
