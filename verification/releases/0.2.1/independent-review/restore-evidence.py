#!/usr/bin/env python3
"""Restore exact review evidence into a new directory; never overwrite evidence."""
from pathlib import Path
import argparse,gzip,hashlib,json

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('destination',type=Path)
    ap.add_argument('--mode',choices=['replay','strict106'],default='replay')
    args=ap.parse_args();base=Path(__file__).resolve().parent
    manifest=json.loads((base/'manifest.json').read_text(encoding='utf-8'))
    destination=args.destination.resolve()
    if destination.exists():raise SystemExit('Destination must not exist; use a fresh directory.')
    destination.mkdir(parents=True)
    sha=lambda b:hashlib.sha256(b).hexdigest()
    selected=[]
    for entry in manifest['files']:
        name=entry['path']
        if args.mode=='strict106' and not (name in ['preparation.json','review.mjs','assess.mjs'] or name.startswith(('baseline/','candidate/','original-inputs/'))):continue
        compressed=(base/entry['payload']).read_bytes()
        if len(compressed)!=entry['payloadBytes'] or sha(compressed)!=entry['payloadSha256']:raise SystemExit('Compressed evidence mismatch: '+name)
        raw=gzip.decompress(compressed)
        if len(raw)!=entry['bytes'] or sha(raw)!=entry['sha256']:raise SystemExit('Original evidence mismatch: '+name)
        target=(destination/name).resolve()
        if destination not in target.parents:raise SystemExit('Unsafe evidence path')
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as stream:stream.write(raw)
        selected.append(name)
    print(json.dumps({'restored':len(selected),'mode':args.mode,'evidenceBytes':sum(e['bytes'] for e in manifest['files'] if e['path'] in selected)}))
if __name__=='__main__':main()
