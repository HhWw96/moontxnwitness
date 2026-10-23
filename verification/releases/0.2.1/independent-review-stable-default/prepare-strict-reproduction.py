#!/usr/bin/env python3
"""Copy the frozen106 runner and stable runtime to a new reproduction directory; no product run."""
from pathlib import Path
import argparse,shutil,hashlib
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('restored_base',type=Path);ap.add_argument('fresh_destination',type=Path);args=ap.parse_args()
base=args.restored_base.resolve();dest=args.fresh_destination.resolve()
if dest.exists():raise SystemExit('Destination must not exist')
runner=base/'review.mjs'
if hashlib.sha256(runner.read_bytes()).hexdigest()!='0b055a0f770c5c3484b1e3f66796c7b02cc09e3f8f30ff15b52d7af8f662598b':raise SystemExit('Frozen106 runner differs')
dest.mkdir(parents=True);shutil.copyfile(runner,dest/'review.mjs');shutil.copyfile(base/'stable-default-strict106-c/preparation.json',dest/'preparation.json')
shutil.copytree(base/'baseline',dest/'baseline');shutil.copytree(base/'original-inputs',dest/'original-inputs');shutil.copytree(base/'stable-default-20261023-c',dest/'candidate')
print('Prepared exact immutable runner and inputs; enter destination and run: node review.mjs')
