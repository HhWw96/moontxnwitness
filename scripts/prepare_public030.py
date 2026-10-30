"""Fetch the exact public v0.3.0 runtime into an ignored local cache."""
from pathlib import Path,PurePosixPath
from urllib.request import urlopen
import hashlib,json,zipfile,sys

root=Path(sys.argv[1]).resolve()
cache=root/'artifacts/compat-v030';cache.mkdir(parents=True,exist_ok=True)
archive=cache/'public-portable.zip'
expected='c6a65dc689d98576a4711e1d22414d7534b1f2d68d9e08147d539adb5326f0ee'
url='https://github.com/HhWw96/moontxnwitness/releases/download/v0.3.0/MoonTxnWitness-v0.3.0-portable.zip'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(1024*1024):h.update(b)
 return h.hexdigest()
if not archive.exists():
 with urlopen(url,timeout=120) as response,archive.open('xb') as out:
  while b:=response.read(1024*1024):out.write(b)
assert sha(archive)==expected,'Public v0.3.0 archive SHA-256 differs'
destination=cache/'runtime';destination.mkdir(exist_ok=True)
files={}
with zipfile.ZipFile(archive) as z:
 for entry in z.infolist():
  name=entry.filename;prefix='MoonTxnWitness-v0.3.0/dist/'
  if entry.is_dir() or not name.startswith(prefix):continue
  rel=name[len(prefix):];p=PurePosixPath(rel)
  assert not p.is_absolute() and '..' not in p.parts and ':' not in rel and '\\' not in rel
  assert ((entry.external_attr>>16)&0o170000)!=0o120000
  raw=z.read(entry);target=destination/rel
  assert target.resolve().is_relative_to(destination.resolve())
  target.parent.mkdir(parents=True,exist_ok=True)
  if target.exists():assert target.read_bytes()==raw
  else:target.write_bytes(raw)
  files[rel]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
 license_bytes=z.read('MoonTxnWitness-v0.3.0/LICENSE')
 (destination/'LICENSE').write_bytes(license_bytes)
 files['LICENSE']={'bytes':len(license_bytes),'sha256':hashlib.sha256(license_bytes).hexdigest()}
manifest={'version':'0.3.0','archiveSha256':expected,'files':files}
encoded=(json.dumps(manifest,sort_keys=True,separators=(',',':'))+'\n').encode()
(destination/'public-runtime-manifest.json').write_bytes(encoded)
print(json.dumps({'files':len(files),'bytes':sum(f['bytes'] for f in files.values()),'manifestSha256':hashlib.sha256(encoded).hexdigest(),'root':str(destination)},indent=2))
