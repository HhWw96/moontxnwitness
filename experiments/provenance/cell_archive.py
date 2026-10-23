"""Lossless cell retention after the child exits and all measured tails finish.

This is byte preservation, not a semantic or model-coverage verifier. It never
touches PostgreSQL data, previous runs, active source logs or arbitrary paths.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import re
import stat
import zipfile
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"integrations/python"))
from moontxnwitness_capture._experimental_budget import PROFILE,LIMITS,profile,authorize

FORMAT='moontxnwitness-cost-cell-archive/v1'
MANIFEST='archive-manifest.json'
CHUNK=1024*1024
MAX_TOTAL=8*1024**3
MAX_MEMBERS=10000
_DEFAULT_BYTE_LIMIT=object()

def digest(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as file:
        for block in iter(lambda:file.read(CHUNK),b''):value.update(block)
    return value.hexdigest()

def _unsafe(path):
    return path.is_symlink() or bool(getattr(path,'is_junction',lambda:False)())

def _name(value):
    if not isinstance(value,str) or not value or '\\' in value or ':' in value or '\x00' in value:raise ValueError('Unsafe archive member')
    path=PurePosixPath(value)
    if path.is_absolute() or any(part in ('','.','..') for part in value.split('/')):raise ValueError('Unsafe archive member')
    return value

def _cell(run_root,cell_root):
    root=Path(run_root).resolve();candidate=Path(cell_root)
    if _unsafe(candidate):raise ValueError('Unsafe cell root')
    cell=candidate.resolve()
    if cell.parent!=root or not re.fullmatch(r'cell-[0-9]+',cell.name) or not cell.is_dir():raise ValueError('Only a direct new run cell may be archived')
    return root,cell

def _files(cell, *, experimental_budget=None):
    selected=profile(experimental_budget)
    maximum=LIMITS["archiveExpandedBytes"] if selected else MAX_TOTAL
    result={}
    for path in sorted(cell.rglob('*')):
        if _unsafe(path) or not path.resolve().is_relative_to(cell):raise ValueError('Unsafe cell member')
        if path.is_dir():continue
        if not path.is_file():raise ValueError('Not a regular cell file')
        name=_name(path.relative_to(cell).as_posix())
        if name in (MANIFEST,'archive-pointer.json'):raise ValueError('Cell was already archived or uses a reserved name')
        result[name]={'bytes':path.stat().st_size,'sha256':digest(path)}
    if not result or len(result)>MAX_MEMBERS or sum(x['bytes'] for x in result.values())>maximum:raise ValueError('Cell retention budget')
    return result

def verify_archive(path,*,expected_sha256=None,max_total_bytes=_DEFAULT_BYTE_LIMIT,experimental_budget=None):
    profile(experimental_budget)
    path=Path(path)
    if _unsafe(path) or not path.is_file():raise ValueError('Unsafe archive file')
    archive_sha=digest(path)
    if expected_sha256 is not None and archive_sha!=expected_sha256:raise ValueError('Archive SHA mismatch')
    with zipfile.ZipFile(path,'r') as archive:
        infos=archive.infolist();names=[_name(item.filename) for item in infos]
        if len(names)>MAX_MEMBERS+1 or len(names)!=len(set(names)) or MANIFEST not in names:raise ValueError('Archive member set')
        if any(item.is_dir() or stat.S_ISLNK(item.external_attr>>16) for item in infos):raise ValueError('Archive contains non-file member')
        info=archive.getinfo(MANIFEST)
        if info.file_size>4*1024*1024:raise ValueError('Archive manifest budget')
        manifest_raw=archive.read(MANIFEST);manifest=json.loads(manifest_raw)
        if manifest.get('format')!=FORMAT or not isinstance(manifest.get('files'),dict):raise ValueError('Archive manifest format')
        selected=authorize(manifest.get('experimentalBudget'),experimental_budget)
        maximum=LIMITS['archiveExpandedBytes'] if selected else MAX_TOTAL
        if selected and manifest.get('maximumExpandedBytes')!=maximum:raise ValueError('Experimental archive limit binding')
        expanded_limit=maximum if max_total_bytes is _DEFAULT_BYTE_LIMIT else max_total_bytes
        if type(expanded_limit) is not int or expanded_limit<0 or selected and expanded_limit>maximum:raise ValueError('Archive reader byte budget')
        files=manifest['files']
        if set(names)!={MANIFEST,*files}:raise ValueError('Archive files differ from manifest')
        total=0
        for name,expected in files.items():
            _name(name)
            if not isinstance(expected,dict) or type(expected.get('bytes')) is not int or expected['bytes']<0 or not re.fullmatch('[0-9a-f]{64}',str(expected.get('sha256'))):raise ValueError('Archive file binding')
            member=archive.getinfo(name);total+=member.file_size
            if member.file_size!=expected['bytes'] or total>expanded_limit:raise ValueError('Archive expanded-size budget')
            value=hashlib.sha256();size=0
            with archive.open(member) as file:
                for block in iter(lambda:file.read(CHUNK),b''):
                    size+=len(block)
                    if size>expected['bytes']:raise ValueError('Archive member grew')
                    value.update(block)
            if size!=expected['bytes'] or value.hexdigest()!=expected['sha256']:raise ValueError('Archived original bytes differ')
    return {'verified':True,'archiveSha256':archive_sha,'manifestSha256':hashlib.sha256(manifest_raw).hexdigest(),
            'originalBytes':total,'archiveBytes':path.stat().st_size,'files':files,'manifest':manifest}

def archive_cell(run_root,cell_root,*,experimental_budget=None):
    selected=profile(experimental_budget)
    root,cell=_cell(run_root,cell_root);files=_files(cell,experimental_budget=selected)
    receipt=cell/'receipt.json'
    if not receipt.is_file():raise ValueError('No terminal child receipt; retain raw partial cell')
    value=json.loads(receipt.read_text(encoding='utf8'))
    if value.get('status') not in ('passed','smoke-passed','failed','not-executed'):raise ValueError('Child receipt is not terminal')
    directory=root/'archives';directory.mkdir(exist_ok=True)
    if _unsafe(directory):raise ValueError('Unsafe archive destination')
    destination=directory/(cell.name+'.zip');temporary=directory/(cell.name+'.zip.partial')
    if destination.exists() or temporary.exists():raise FileExistsError(destination)
    manifest={'format':FORMAT,'cell':cell.name,'files':files,'receiptSha256':files['receipt.json']['sha256'],
              'cellStatus':value['status'],'formalProtocolCompleted':bool(value.get('formalProtocolCompleted')),
              'scope':'Exact cell bytes only; no semantic coverage or complete multi-cell protocol assertion'}
    if selected:manifest.update(experimentalBudget=selected,maximumExpandedBytes=LIMITS['archiveExpandedBytes'])
    raw=(json.dumps(manifest,sort_keys=True,separators=(',',':'))+'\n').encode()
    with zipfile.ZipFile(temporary,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as archive:
        for name in files:
            path=cell/name
            if _unsafe(path):raise ValueError('Cell member changed to unsafe type')
            with path.open('rb') as source,archive.open(name,'w',force_zip64=True) as target:
                while block:=source.read(CHUNK):target.write(block)
        archive.writestr(MANIFEST,raw)
    # Windows CRT _commit requires a writable descriptor.
    with temporary.open('r+b') as file:file.flush();os.fsync(file.fileno())
    verified=verify_archive(temporary,experimental_budget=selected)
    if verified['files']!=files:raise ValueError('Archive binding changed')
    temporary.rename(destination)
    pointer={'format':FORMAT,'archive':destination.relative_to(root).as_posix(),
             'archiveSha256':verified['archiveSha256'],'manifestSha256':verified['manifestSha256'],
             'originalBytes':verified['originalBytes'],'archiveBytes':verified['archiveBytes'],
             'originalReceiptSha256':files['receipt.json']['sha256'],'cellStatus':value['status'],
             'archivalOutsideMeasurement':True,'rawReleased':False}
    if selected:pointer.update(experimentalBudget=selected,maximumExpandedBytes=LIMITS['archiveExpandedBytes'])
    with (directory/(cell.name+'.archive.json')).open('x',encoding='utf8',newline='\n') as file:json.dump(pointer,file,indent=2);file.write('\n');file.flush();os.fsync(file.fileno())
    return pointer

def release_cell(run_root,cell_root,pointer,*,experimental_budget=None):
    selected=profile(experimental_budget)
    root,cell=_cell(run_root,cell_root)
    expected=root/'archives'/(cell.name+'.zip')
    if pointer.get('archive')!=expected.relative_to(root).as_posix():raise ValueError('Pointer is outside the owned cell archive')
    verified=verify_archive(expected,expected_sha256=pointer.get('archiveSha256'),experimental_budget=selected)
    if verified['manifestSha256']!=pointer.get('manifestSha256') or verified['manifest']['cell']!=cell.name:raise ValueError('Archive pointer mismatch')
    # Verify the complete set before any deletion. Do not follow shell/glob paths.
    if _files(cell,experimental_budget=selected)!=verified['files']:raise ValueError('Original cell changed; all raw files retained')
    for name in verified['files']:
        target=cell/name
        if _unsafe(target) or not target.resolve().is_relative_to(cell):raise ValueError('Unsafe release target')
    for name in verified['files']:(cell/name).unlink()
    for directory in sorted((p for p in cell.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True):directory.rmdir()
    result={**pointer,'rawReleased':True}
    for path in [cell/'archive-pointer.json',root/'archives'/(cell.name+'.archive.json')]:
        with path.open('w',encoding='utf8',newline='\n') as file:json.dump(result,file,indent=2);file.write('\n');file.flush();os.fsync(file.fileno())
    return result

def restore_archive(path,destination,*,expected_sha256=None,experimental_budget=None):
    verified=verify_archive(path,expected_sha256=expected_sha256,experimental_budget=experimental_budget)
    destination=Path(destination)
    destination.mkdir(parents=True,exist_ok=False);root=destination.resolve()
    with zipfile.ZipFile(path) as archive:
        for name in verified['files']:
            target=root/name
            if not target.resolve().is_relative_to(root):raise ValueError('Unsafe restore path')
            target.parent.mkdir(parents=True,exist_ok=True)
            with archive.open(name) as source,target.open('xb') as output:
                while block:=source.read(CHUNK):output.write(block)
                output.flush();os.fsync(output.fileno())
            if digest(target)!=verified['files'][name]['sha256']:raise ValueError('Restored bytes differ')
    return {k:v for k,v in verified.items() if k not in ('files','manifest')}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('archive');parser.add_argument('--sha256');parser.add_argument('--restore')
    parser.add_argument("--experimental-budget",choices=[PROFILE])
    args=parser.parse_args()
    result=restore_archive(args.archive,args.restore,expected_sha256=args.sha256,experimental_budget=args.experimental_budget) if args.restore else verify_archive(args.archive,expected_sha256=args.sha256,experimental_budget=args.experimental_budget)
    print(json.dumps({k:v for k,v in result.items() if k not in ('files','manifest')},indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
