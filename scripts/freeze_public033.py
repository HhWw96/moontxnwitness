"""Freeze verified 0.3.3 runtime bytes into a bounded reusable component."""
import argparse,hashlib,json,os,re,stat,tempfile,unicodedata,zipfile
from pathlib import Path,PurePosixPath
from input_cache import directory,regular,immutable_publish

ROOT=Path(__file__).resolve().parents[1]
VERSION='0.3.3'
PREFIX='MoonTxnWitness-v0.3.3/'
NAME='MoonTxnWitness-v0.3.3-runtime-component.zip'
def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def existing_directories(path):
 for p in [*reversed(Path(path).parents),Path(path)]:
  s=p.lstat()
  if not stat.S_ISDIR(s.st_mode) or getattr(s,'st_file_attributes',0)&0x400:raise ValueError('Linked or non-directory source ancestor')
def safe(name):
 if not isinstance(name,str) or not name or len(name.encode('utf8'))>1024 or '\\' in name or ':' in name or PurePosixPath(name).is_absolute():raise ValueError('Unsafe runtime member')
 parts=name.split('/')
 if len(parts)>32 or any(p in ('','.','..') or p.endswith((' ','.')) or re.search(r'[\x00-\x1f<>:"|?*]',p) or re.match(r'^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)',p,re.I) for p in parts):raise ValueError('Unsafe runtime member')
 return name
def new_bytes(path,data):
 directory(path.parent)
 fd,tmp=tempfile.mkstemp(prefix='component-',dir=path.parent)
 try:
  with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
  immutable_publish(tmp,path,{'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
 finally:Path(tmp).unlink(missing_ok=True)
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--portable',required=True,type=Path)
 p.add_argument('--sha256',required=True)
 p.add_argument('--commit',required=True,help='Full tag commit independently verified against the public release')
 p.add_argument('--pool-root',type=Path,default=ROOT/'dist')
 p.add_argument('--output',type=Path,default=ROOT/'artifacts'/NAME)
 p.add_argument('--bind',action='store_true',help='Write fixed binding after public release verification')
 a=p.parse_args();assert re.fullmatch('[0-9a-f]{64}',a.sha256) and re.fullmatch('[0-9a-f]{40}',a.commit)
 a.portable=Path(os.path.abspath(a.portable));a.pool_root=Path(os.path.abspath(a.pool_root));a.output=Path(os.path.abspath(a.output))
 assert a.output.is_relative_to(ROOT/'artifacts'),'Component output must be under this worktree artifacts'
 existing_directories(a.portable.parent);assert regular(a.portable).st_size<=128*1024*1024
 existing_directories(a.pool_root);assert digest(a.portable)==a.sha256,'Verified portable checksum differs'
 inventory={};top={};folded=set();total=0;top_total=0;selected=[]
 with zipfile.ZipFile(a.portable) as packed:
  assert len(packed.infolist())==len(set(packed.namelist())) and len(packed.infolist())<=20000
  # Bound the declared inventory before allocating any uncompressed member.
  for info in packed.infolist():
   name=info.filename
   if name==PREFIX+'LICENSE':rel='LICENSE'
   elif name.startswith(PREFIX+'dist/'):rel=name[len(PREFIX+'dist/'):]
   else:continue
   safe(rel);alias=unicodedata.normalize('NFC',rel).casefold();assert alias not in folded;folded.add(alias)
   assert not info.is_dir() and stat.S_IFMT(info.external_attr>>16) in (0,stat.S_IFREG) and 0<=info.file_size<=16*1024*1024
   if not rel.startswith(('legacy/','legacy-components/')):
    assert '/' not in rel,'Unexpected active runtime subdirectory';top_total+=info.file_size
   total+=info.file_size;selected.append((rel,info))
   assert len(selected)<=10000 and total<=1024**3 and top_total<=32*1024*1024,'Runtime expansion budget'
  for rel,info in selected:
   raw=packed.read(info);assert len(raw)==info.file_size
   row={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
   if rel.startswith(('legacy/','legacy-components/')):
    target=a.pool_root/rel;existing_directories(target.parent)
    assert regular(target).st_size==len(raw) and digest(target)==row['sha256'],'Immutable pool differs: '+rel
    row['source']=rel
   else:row['source']='legacy-components/v033/'+rel;top[rel]=raw
   inventory[rel]=row
  manifest=json.loads(top['build-manifest.json']);assert manifest['version']==VERSION
  assert {'sdk.mjs','core.mjs','capture-core.mjs','legacy-v031.mjs','legacy-v031-binding.mjs','v4.mjs','LICENSE'}.issubset(top)
  assert 'legacy/v031/core.mjs' in inventory
 assert digest(a.portable)==a.sha256,'Portable changed while freezing'
 # Every candidate source was verified against its exact original archive member.
 # Reuse only those sources; do not scan or trust unrelated installed files.
 by_content={}
 for row in inventory.values():
  key=(row['bytes'],row['sha256'])
  chosen=by_content.get(key)
  source=row['source']
  if chosen is None or (not source.startswith(('legacy/','legacy-components/v032/')),source)<(not chosen.startswith(('legacy/','legacy-components/v032/')),chosen):by_content[key]=source
 for row in inventory.values():row['source']=by_content[(row['bytes'],row['sha256'])]
 original_top_files=len(top);original_top_bytes=top_total
 referenced_components={row['source'] for row in inventory.values() if row['source'].startswith('legacy-components/v033/')}
 # The separately downloadable component always carries the verified original
 # project LICENSE, even when its logical runtime binding reuses an old pool file.
 compliance_members={'LICENSE'}
 top={rel:raw for rel,raw in top.items() if 'legacy-components/v033/'+rel in referenced_components or rel in compliance_members}
 source_members={rel for rel in top if 'legacy-components/v033/'+rel in referenced_components}
 compliance_only_members=compliance_members-source_members
 component_total=sum(len(raw) for raw in top.values())
 unique_sources={row['source']:row for row in inventory.values()}
 directory(a.output.parent)
 fd,tmp=tempfile.mkstemp(prefix='runtime-component-',dir=a.output.parent)
 try:
  with os.fdopen(fd,'w+b') as rawzip:
   with zipfile.ZipFile(rawzip,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as out:
    for rel,raw in sorted(top.items()):
     info=zipfile.ZipInfo('PublicRuntime-v0.3.3/'+rel,date_time=(2026,10,31,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info._compresslevel=9;info.external_attr=0o100644<<16
     out.writestr(info,raw)
   rawzip.flush();os.fsync(rawzip.fileno())
  with zipfile.ZipFile(tmp) as checked:
   assert checked.testzip() is None
   for rel,raw in top.items():assert checked.read('PublicRuntime-v0.3.3/'+rel)==raw
  checksum=digest(Path(tmp));length=Path(tmp).stat().st_size
  immutable_publish(tmp,a.output,{'bytes':length,'sha256':checksum})
 finally:Path(tmp).unlink(missing_ok=True)
 binding={'version':VERSION,'sourceCommit':a.commit,'archiveSha256':a.sha256,'componentSha256':checksum,'files':inventory}
 result={'passed':True,'version':VERSION,'sourceCommit':a.commit,'originalPortableSha256':a.sha256,'fullRuntimeFiles':len(inventory),'fullRuntimeBytes':total,'componentFiles':len(top),'componentSourceFiles':len(source_members),'componentComplianceMembers':sorted(compliance_members),'componentComplianceOnlyMembers':sorted(compliance_only_members),'componentLogicalBytes':component_total,'originalTopFiles':original_top_files,'originalTopBytes':original_top_bytes,'uniqueSourceFiles':len(unique_sources),'uniqueSourceBytes':sum(row['bytes'] for row in unique_sources.values()),'uniqueContents':len(by_content),'uniqueContentBytes':sum(key[0] for key in by_content),'componentArchive':{'file':a.output.name,'bytes':length,'sha256':checksum},'publishedComponent':False}
 new_bytes(a.output.with_suffix('.json'),(json.dumps({'binding':binding,'receipt':result},sort_keys=True,indent=2)+'\n').encode('utf8'))
 if a.bind:new_bytes(ROOT/'cmd/legacy-v033-binding.mjs',('export const PUBLIC033=Object.freeze('+json.dumps(binding,sort_keys=True,separators=(',',':'))+');\nfor(const e of Object.values(PUBLIC033.files))Object.freeze(e);\nObject.freeze(PUBLIC033.files);\n').encode('utf8'))
 print(json.dumps(result),flush=True)
if __name__=='__main__':main()
