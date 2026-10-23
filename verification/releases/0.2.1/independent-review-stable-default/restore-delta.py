#!/usr/bin/env python3
"""Apply exact nonoverwriting delta to a restored base independent evidence directory."""
from pathlib import Path
import argparse,json,gzip,hashlib
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('destination',type=Path);args=ap.parse_args()
base=Path(__file__).resolve().parent;manifest=json.loads((base/'manifest.json').read_text());dest=args.destination.resolve();sha=lambda b:hashlib.sha256(b).hexdigest()
required={'receipt-first.json':'db943a78f42a0c40b38803287b667061b6fc63f523b90ec816a1399ea3683601','replay-regression.mjs':'8233bbfd19d7d598e5e9bec0321125c1b255ec050deca288d43dafdb426ef80f','model-replay-independent.mjs':'a72850541ee7ac69d97e669e0cc07d4a30516e84642f351ffd3d4aeb7e8d84e5'}
for name,h in required.items():
    if not (dest/name).is_file() or sha((dest/name).read_bytes())!=h:raise SystemExit('Restore the correct immutable base first: '+name)
for e in manifest['files']:
    target=(dest/e['path']).resolve()
    if dest not in target.parents or target.exists():raise SystemExit('Unsafe or existing delta destination: '+e['path'])
for e in manifest['files']:
    c=(base/e['payload']).read_bytes()
    if len(c)!=e['payloadBytes']or sha(c)!=e['payloadSha256']:raise SystemExit('Compressed evidence mismatch')
    raw=gzip.decompress(c)
    if len(raw)!=e['bytes']or sha(raw)!=e['sha256']:raise SystemExit('Original evidence mismatch')
    target=dest/e['path'];target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('xb')as stream:stream.write(raw)
print(json.dumps({'restored':len(manifest['files']),'overwritten':0,'productProgramsExecuted':False}))
