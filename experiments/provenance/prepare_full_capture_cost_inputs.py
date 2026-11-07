"""Restore only the frozen small legacy workflow required by cost-unit checks.

Downloads, if needed, happen during CI setup and use the existing verified
public provider implementation. No compatibility runtime or whole test corpus
is materialized. Corrupt existing files/cache are refused, never overwritten.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import input_cache as cache

NAME='verification/formal-harness-fix/reproduction/original-full-capture-cost.yml.gz'
EXPECTED={'bytes':2490,'sha256':'048b14d0bf8e5a0800668491e8778de9534edeff4f4224535dcf8d7137add823'}

def prepare(root=ROOT,cache_dir=None,offline=False):
    root=Path(root)
    manifest,entries=cache.load_index(root)
    entry=entries[NAME]
    if entry['bytes']!=EXPECTED['bytes'] or entry['sha256']!=EXPECTED['sha256'] or entry['group']!='tests':
        raise ValueError('Cost fixture no longer matches its frozen input identity')
    target=root/NAME
    cache.directory(target.parent)
    if target.exists() or target.is_symlink():
        cache.verify_file(target,entry)
        return {'format':'full-capture-cost-offline-fixture/v1','passed':True,'materializedFiles':1,
                'logicalBytes':entry['bytes'],'sha256':entry['sha256'],'indexSha256':manifest['indexSha256'],
                'state':'verified-existing','networkUsed':False}
    directory=cache.directory(Path(cache_dir or os.environ.get('MTW_INPUT_CACHE',str(root/'artifacts/input-cache'))))
    with cache.preparation_lock(directory):
        blob=directory/'blobs'/entry['sha256'][:2]/entry['sha256']
        archive_used=False
        if blob.exists() or blob.is_symlink():
            cache.verify_file(blob,entry)
        else:
            archive=cache.archive_file(root,directory,manifest['providers'][entry['provider']],offline)
            with zipfile.ZipFile(archive) as zipped:blob=cache.ensure_blob(directory,zipped,entry)
            archive_used=True
        state=cache.materialize(root,NAME,blob,entry)
        cache.verify_file(target,entry)
    return {'format':'full-capture-cost-offline-fixture/v1','passed':True,'materializedFiles':1,
            'logicalBytes':entry['bytes'],'sha256':entry['sha256'],'indexSha256':manifest['indexSha256'],
            'state':state,'archiveProviderUsed':archive_used,'offline':offline,
            'fixtureBytesVerifiedAgainstPinnedIndex':True,'providerHashVerifiedIfOpened':True,
            'noRuntimeOrFullCorpusMaterialized':True}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline',action='store_true')
    parser.add_argument('--cache')
    args=parser.parse_args()
    print(json.dumps(prepare(cache_dir=args.cache,offline=args.offline)))
    return 0

if __name__=='__main__':raise SystemExit(main())
