"""Import one exact-source PostgreSQL CI packet; never execute SQL or rewrite evidence."""
from __future__ import annotations
import argparse, datetime, hashlib, json, os, re, stat, subprocess, tempfile, time, urllib.error, urllib.parse, urllib.request, zipfile
from pathlib import Path, PurePosixPath

FORMAT = 'moontxnwitness-postgres-ci-import/v1'
ARTIFACT = 'actual-postgresql-evidence'
MAX_ZIP = 256 * 1024 * 1024
MAX_TOTAL = 1024 * 1024 * 1024
MAX_MEMBER = 128 * 1024 * 1024
MAX_PACKET = 32 * 1024 * 1024
SHA = re.compile(r'[0-9a-f]{64}\Z')
COMMIT = re.compile(r'[0-9a-f]{40}\Z')
MANDATORY = {'receipt.json', 'capture.json', 'rr.capsule.json', 'serial.capsule.json', 'mini.capsule.json'}

class ImportFailure(RuntimeError): pass

def require(ok, message):
    if not ok: raise ImportFailure(message)

def digest(raw): return hashlib.sha256(raw).hexdigest()

def json_bytes(raw, maximum=8*1024*1024):
    require(len(raw) <= maximum, 'JSON budget exceeded')
    def pairs(rows):
        value = {}
        for key, item in rows:
            require(key not in value, 'Duplicate JSON member')
            value[key] = item
        return value
    try: return json.loads(raw.decode('utf8'), object_pairs_hook=pairs)
    except (ValueError, UnicodeError) as exc: raise ImportFailure('Invalid JSON') from exc

def safe_name(value):
    require(isinstance(value, str) and value and chr(92) not in value and ':' not in value and chr(0) not in value, 'Unsafe evidence path')
    path = PurePosixPath(value)
    require(not path.is_absolute() and all(x not in ('', '.', '..') for x in value.split('/')), 'Unsafe evidence path')
    require(all(not x.endswith((' ', '.')) and not re.match(r'(?i)^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)', x) for x in path.parts), 'Unsafe Windows evidence path')
    return value

def no_links(root, relative):
    target = root
    for part in PurePosixPath(safe_name(relative)).parts:
        target = target / part
        if target.exists() or target.is_symlink():
            info = target.lstat()
            require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400, 'Linked evidence destination')
    require(target.resolve().is_relative_to(root.resolve()), 'Evidence escapes checkout')
    return target

def source_fingerprint(root):
    names = ['moon.mod']
    for base, dirs, files in os.walk(root/'src'):
        for name in dirs:
            require(not (Path(base)/name).is_symlink(), 'Linked source directory')
        for name in files:
            if name.endswith('.mbt') or name == 'moon.pkg': names.append((Path(base)/name).relative_to(root).as_posix())
    require(len(names) <= 2500, 'Source inventory budget exceeded')
    h = hashlib.sha256(); total = 0
    for name in sorted(names):
        path = no_links(root, name); raw = path.read_bytes(); total += len(raw)
        require(total <= 64*1024*1024, 'Source byte budget exceeded')
        h.update(name.encode()); h.update(bytes([0])); h.update(raw); h.update(bytes([0]))
    return h.hexdigest()

def checkout_identity(root):
    root = Path(root).resolve()
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    require(bool(COMMIT.fullmatch(commit)), 'Invalid checked-out source commit')
    version = json_bytes((root/'package.json').read_bytes())['version']
    require(bool(re.fullmatch(r'\d+\.\d+\.\d+', version)), 'Invalid current version')
    manifest = json_bytes((root/'dist/build-manifest.json').read_bytes())
    require(manifest.get('version') == version and manifest.get('sourceSha256') == source_fingerprint(root), 'Current build/source mismatch')
    for name, field in [('core.mjs','coreSha256'), ('capture-core.mjs','captureCoreSha256')]:
        require(digest((root/'dist'/name).read_bytes()) == manifest.get(field), 'Current runtime digest mismatch')
    node = os.environ.get('MTW_NODE', 'node')
    raw = subprocess.check_output([node, '--input-type=module', '-e',
        "import{verificationFingerprint}from'./scripts/verification-fingerprint.mjs';console.log(JSON.stringify(verificationFingerprint(process.cwd())))"],
        cwd=root)
    tested = json_bytes(raw)
    require(isinstance(tested,dict) and 0<len(tested)<=50000, 'Invalid current executable fingerprint')
    return {'commit':commit, 'version':version, 'buildManifest':manifest, 'testedFileSha256':tested}

def validate_run(run, repository, expected, pr_head=None):
    require(run.get('repository',{}).get('full_name','').lower() == repository.lower(), 'Wrong workflow repository')
    require(run.get('path') == '.github/workflows/postgres.yml', 'Wrong PostgreSQL workflow')
    require(run.get('status') == 'completed' and run.get('conclusion') == 'success', 'PostgreSQL run is not successful')
    require(type(run.get('id')) is int and run['id'] > 0 and type(run.get('run_attempt')) is int and run['run_attempt'] > 0, 'Invalid run identity')
    same = run.get('head_sha') == expected
    pr = pr_head is not None and run.get('event') == 'pull_request' and run.get('head_sha') == pr_head
    require(same or pr, 'Workflow source is neither exact HEAD nor this PR head')

def validate_payload(payload, run, artifact, expected, *, require_runtime_bytes=True):
    version, commit = expected['version'], expected['commit']; prefix = f'verification/releases/{version}/postgres/'
    source_name = 'verification/postgres-ci-source.json'
    bindings = f"verification/postgres-ci-runtime/{run['id']}-{run['run_attempt']}/"
    before_name, after_name = bindings+'postgres-ci-runtime-before.json', bindings+'postgres-ci-runtime-after.json'
    require(all(n in payload for n in [source_name,before_name,after_name,prefix+'receipt.json']), 'Missing source/runtime/packet receipt')
    source, before, after = [json_bytes(payload[n]) for n in [source_name,before_name,after_name]]
    require(source.get('sourceCommit') == before.get('sourceCommit') == after.get('sourceCommit') == commit, 'Artifact is not the exact checked-out source')
    require(before.get('phase') == 'before' and after.get('phase') == 'after', 'Wrong runtime observation phases')
    pg = before.get('buildManifest'); current = expected['buildManifest']
    require(isinstance(pg,dict) and pg == after.get('buildManifest'), 'PostgreSQL runtime changed during execution')
    require(pg.get('version') == version and pg.get('sourceSha256') == current.get('sourceSha256'), 'PostgreSQL source/version differs')
    require(pg.get('toolchain',{}).get('compiler') == current.get('toolchain',{}).get('compiler') and isinstance(pg.get('toolchain',{}).get('compiler'), str), 'PostgreSQL compiler differs')
    tested = before.get('testedFileSha256')
    require(isinstance(tested,dict) and tested == after.get('testedFileSha256') and tested, 'PostgreSQL executable inputs changed')
    for name, value in tested.items(): require(safe_name(name) and isinstance(value,str) and SHA.fullmatch(value), 'Invalid tested source digest')
    current_tested = expected.get('testedFileSha256')
    require(isinstance(current_tested,dict) and current_tested, 'Missing current executable fingerprint')
    platform_members = {'dist/core.mjs','dist/capture-core.mjs','dist/build-manifest.json'}
    shared = {k:v for k,v in tested.items() if k not in platform_members}
    current_shared = {k:v for k,v in current_tested.items() if k not in platform_members}
    require(shared == current_shared, 'PostgreSQL SQL/adapter/fixture executable fingerprints differ')

    for name, field in [('dist/core.mjs','coreSha256'),('dist/capture-core.mjs','captureCoreSha256')]:
        require(pg.get(field) == tested.get(name) and isinstance(pg.get(field), str) and SHA.fullmatch(pg[field]), 'Artifact runtime digest disagrees with execution bindings')
        if require_runtime_bytes:
            require(name in payload and digest(payload[name]) == pg[field], 'Artifact runtime bytes disagree with execution bindings')
    receipt = json_bytes(payload[prefix+'receipt.json'])
    require(receipt.get('version') == version and receipt.get('passed') is True and receipt.get('actualDatabaseExecution') is True and receipt.get('status') == 'passed', 'Actual PostgreSQL receipt did not pass')
    files = receipt.get('files'); require(isinstance(files,dict) and 4 <= len(files) <= 128, 'Invalid PostgreSQL receipt closure')
    names = {'receipt.json'}
    for name, value in files.items():
        safe_name(name); require('/' not in name and name != 'receipt.json' and isinstance(value,str) and SHA.fullmatch(value), 'Unsafe packet reference')
        require(prefix+name in payload and digest(payload[prefix+name]) == value, 'PostgreSQL referenced file differs: '+name); names.add(name)
    require(MANDATORY <= names, 'Mandatory PostgreSQL evidence is absent')
    require({n[len(prefix):] for n in payload if n.startswith(prefix)} == names, 'Unreferenced or nested PostgreSQL packet member')
    capture = json_bytes(payload[prefix+'capture.json'])
    require(capture.get('passed') is True and capture.get('actualDatabaseExecution') is True, 'Actual PostgreSQL capture did not pass')
    selected = {prefix+n:payload[prefix+n] for n in sorted(names)}
    imported_bindings = {'source.json':payload[source_name], 'runtime-before.json':payload[before_name], 'runtime-after.json':payload[after_name]}
    for name, raw in imported_bindings.items(): selected[f'verification/releases/{version}/postgres-ci-import/{name}'] = raw
    require(sum(map(len,selected.values())) <= MAX_PACKET, 'Imported packet budget exceeded')
    comparison = {'sourceVersionCompilerMatch':True,
                  'sharedExecutableInputsSha256':digest(json.dumps(shared,sort_keys=True,separators=(',',':')).encode()),
                  'sharedExecutableInputCount':len(shared),'platformRuntimeExceptions':sorted(platform_members),
                  'runtimeBinaryIdentityClaimed':pg == current,
                  'postgresBuildManifest':pg,'consumerBuildManifest':current,
                  'coreBytesEqual':pg.get('coreSha256') == current.get('coreSha256'),
                  'captureBytesEqual':pg.get('captureCoreSha256') == current.get('captureCoreSha256'),
                  'toolchainsEqual':pg.get('toolchain') == current.get('toolchain')}
    return selected, comparison

def validate_artifact_metadata(run, artifact):
    require(artifact.get('name') == ARTIFACT and artifact.get('expired') is False, 'Wrong or expired artifact')
    require(artifact.get('workflow_run',{}).get('id') == run['id'] and artifact['workflow_run'].get('head_sha') == run.get('head_sha'), 'Artifact belongs to another run')
    require(type(artifact.get('id')) is int and artifact['id'] > 0, 'Invalid artifact identity')
    try:
        created = datetime.datetime.fromisoformat(artifact['created_at'].replace('Z','+00:00'))
        started = datetime.datetime.fromisoformat(run['run_started_at'].replace('Z','+00:00'))
        require(created.tzinfo is not None and started.tzinfo is not None and created >= started, 'Artifact predates this run attempt')
    except (KeyError, ValueError, TypeError) as exc: raise ImportFailure('Invalid run/artifact timestamps') from exc

    require(type(artifact.get('size_in_bytes')) is int and 0 < artifact['size_in_bytes'] <= MAX_ZIP, 'Artifact size budget exceeded')
    require(isinstance(artifact.get('digest'),str) and re.fullmatch(r'sha256:[0-9a-f]{64}',artifact['digest']), 'Missing artifact API digest')

def validate_archive(path, run, artifact, expected, repository, pr_head=None):
    validate_run(run,repository,expected['commit'],pr_head)
    validate_artifact_metadata(run,artifact)
    require(Path(path).stat().st_size == artifact['size_in_bytes'], 'Artifact API length differs')
    with Path(path).open('rb') as stream:
        actual_digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    require(artifact.get('digest') == 'sha256:'+actual_digest, 'Artifact API ZIP digest differs')
    prefix=f"verification/releases/{expected['version']}/postgres/"; binding=f"verification/postgres-ci-runtime/{run['id']}-{run['run_attempt']}/"
    selected={}; seen=set(); total=0
    with zipfile.ZipFile(path) as z:
        require(len(z.infolist()) <= 20000, 'Artifact member budget exceeded')
        for member in z.infolist():
            require(member.orig_filename == member.filename, 'Artifact member path was normalized by this platform')
            name=safe_name(member.filename[:-1] if member.is_dir() else member.filename); folded=name.casefold()
            require(folded not in seen, 'Duplicate/case-colliding artifact path'); seen.add(folded)
            mode=member.external_attr>>16
            require(stat.S_IFMT(mode) in (0,stat.S_IFREG,stat.S_IFDIR) and not member.flag_bits&1, 'Special/encrypted artifact member')
            require(0 <= member.file_size <= MAX_MEMBER, 'Artifact member size exceeded');total+=member.file_size;require(total<=MAX_TOTAL,'Artifact expansion budget exceeded')
            if member.is_dir():continue
            keep=name.startswith(prefix) or name in ['verification/postgres-ci-source.json',binding+'postgres-ci-runtime-before.json',binding+'postgres-ci-runtime-after.json','dist/core.mjs','dist/capture-core.mjs']
            raw=bytearray() if keep else None;read=0
            with z.open(member) as stream:
                while True:
                    chunk=stream.read(65536)
                    if not chunk:break
                    read+=len(chunk);require(read<=member.file_size,'Artifact member exceeded declared length')
                    if keep:raw.extend(chunk)
            require(read==member.file_size,'Truncated artifact member')
            if keep:
                require(sum(map(len,selected.values()))+len(raw)<=MAX_PACKET+64*1024*1024, 'Selected artifact byte budget exceeded')
                selected[name]=bytes(raw)
    files,comparison=validate_payload(selected,run,artifact,expected)
    return files,comparison

def install(root, files, record):
    root=Path(root).resolve();version=record['version'];index=f'verification/releases/{version}/postgres-ci-import/receipt.json'
    record={**record,'format':FORMAT,'files':{n:{'bytes':len(v),'sha256':digest(v)} for n,v in sorted(files.items())}}
    encoded=(json.dumps(record,sort_keys=True,indent=2)+'\n').encode();all_files={**files,index:encoded}
    for name,raw in all_files.items():
        require(name.startswith(f'verification/releases/{version}/postgres/') or name.startswith(f'verification/releases/{version}/postgres-ci-import/'), 'Import destination outside current version')
        path=no_links(root,name)
        if path.exists():require(path.is_file() and path.read_bytes()==raw,'Refusing to replace existing evidence')
    for name,raw in all_files.items():
        path=no_links(root,name);path.parent.mkdir(parents=True,exist_ok=True)
        try:
            with path.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        except FileExistsError:require(path.read_bytes()==raw,'Conflicting prior import record')
    return record

def validated_postgres_import_files(root, version):
    """Recheck only the narrow imported closure; never authorize arbitrary ignored files."""
    root=Path(root).resolve();name=f'verification/releases/{version}/postgres-ci-import/receipt.json';path=no_links(root,name)
    if not path.exists():return {}
    record=json_bytes(path.read_bytes());require(record.get('format')==FORMAT and record.get('version')==version,'Invalid import record')
    expected=checkout_identity(root);require(record.get('sourceCommit')==expected['commit'],'Stale imported PostgreSQL source')
    rows=record.get('files');require(isinstance(rows,dict) and 8<=len(rows)<=132,'Invalid imported closure')
    payload={};prefix=f'verification/releases/{version}/postgres/'
    for member,spec in rows.items():
        require(member.startswith(prefix) or member in [f'verification/releases/{version}/postgres-ci-import/'+x for x in ['source.json','runtime-before.json','runtime-after.json']],'Unapproved imported file')
        target=no_links(root,member);require(target.stat().st_size<=MAX_PACKET,'Imported file budget exceeded')
        raw=target.read_bytes();require(len(raw)==spec.get('bytes') and digest(raw)==spec.get('sha256'),'Imported file changed')
        payload[member]=raw
    run=record['run'];artifact=record['artifact']
    repository=os.environ.get('GITHUB_REPOSITORY',record['repository']);require(record['repository'].lower()==repository.lower(),'Imported repository differs from this job')
    trusted_pr=event_pr_head(repository,expected['commit'])
    require(record.get('prHead')==trusted_pr,'Imported PR head differs from this event')
    validate_run(run,repository,expected['commit'],trusted_pr);validate_artifact_metadata(run,artifact)
    base=f'verification/releases/{version}/postgres-ci-import/';bindings=f"verification/postgres-ci-runtime/{run['id']}-{run['run_attempt']}/"
    translated={n:v for n,v in payload.items() if n.startswith(prefix)}
    translated['verification/postgres-ci-source.json']=payload[base+'source.json']
    translated[bindings+'postgres-ci-runtime-before.json']=payload[base+'runtime-before.json'];translated[bindings+'postgres-ci-runtime-after.json']=payload[base+'runtime-after.json']
    # Recompute the same source/receipt checks from retained original bindings.
    _, comparison = validate_payload(translated,run,artifact,expected,require_runtime_bytes=False)
    require(record.get('comparison') == comparison, 'Imported platform/build comparison changed')
    return {**rows,name:{'bytes':path.stat().st_size,'sha256':digest(path.read_bytes())}}

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        require(urllib.parse.urlparse(newurl).scheme=='https','Insecure artifact redirect')
        result=super().redirect_request(request,fp,code,msg,headers,newurl)
        if urllib.parse.urlparse(newurl).hostname!='api.github.com':result.remove_header('Authorization')
        return result

def api(path, token):
    require(path.startswith('/repos/'),'Unexpected API path')
    request=urllib.request.Request('https://api.github.com'+path,headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'})
    with urllib.request.build_opener(SafeRedirect()).open(request,timeout=30) as stream:
        raw=stream.read(8*1024*1024+1)
    return json_bytes(raw)

def download(path, target, token, expected):
    request=urllib.request.Request('https://api.github.com'+path,headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'})
    total=0;h=hashlib.sha256()
    with urllib.request.build_opener(SafeRedirect()).open(request,timeout=60) as stream, target.open('xb') as output:
        length=stream.headers.get('Content-Length')
        if length is not None:require(int(length)==expected['size_in_bytes'],'Artifact HTTP length differs')
        while True:
            raw=stream.read(65536)
            if not raw:break
            total+=len(raw);require(total<=expected['size_in_bytes']<=MAX_ZIP,'Artifact download budget exceeded');h.update(raw);output.write(raw)
    require(total==expected['size_in_bytes'] and 'sha256:'+h.hexdigest()==expected['digest'],'Artifact download identity differs')

def event_pr_head(repository, expected):
    if os.environ.get('GITHUB_EVENT_NAME')!='pull_request':return None
    require(os.environ.get('GITHUB_SHA')==expected,'PR checkout is not its event merge SHA')
    event=json_bytes(Path(os.environ['GITHUB_EVENT_PATH']).read_bytes())
    require(event.get('repository',{}).get('full_name','').lower()==repository.lower(),'Wrong PR event repository')
    value=event.get('pull_request',{}).get('head',{}).get('sha');require(isinstance(value,str) and COMMIT.fullmatch(value),'Invalid PR event head');return value

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',default=str(Path(__file__).resolve().parents[1]));parser.add_argument('--repository',default=os.environ.get('GITHUB_REPOSITORY'));parser.add_argument('--wait-seconds',type=int,default=900);args=parser.parse_args()
    require(isinstance(args.repository,str) and re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',args.repository) and all(x not in ('.','..') for x in args.repository.split('/')),'Missing/unsafe repository')
    require(0<=args.wait_seconds<=1800,'Invalid bounded workflow wait');root=Path(args.root).resolve();expected=checkout_identity(root);pr=event_pr_head(args.repository,expected['commit']);token=os.environ.get('GH_TOKEN');require(bool(token),'GH_TOKEN with actions:read is required')
    deadline=time.monotonic()+args.wait_seconds;chosen=None
    while True:
        runs=api(f'/repos/{args.repository}/actions/workflows/postgres.yml/runs?per_page=100',token).get('workflow_runs',[])
        relevant=[r for r in runs if r.get('head_sha') in [expected['commit'],pr] and r.get('path')=='.github/workflows/postgres.yml']
        for run in relevant:
            if run.get('status')!='completed' or run.get('conclusion')!='success':continue
            validate_run(run,args.repository,expected['commit'],pr)
            artifacts=api(f"/repos/{args.repository}/actions/runs/{run['id']}/artifacts?per_page=100",token).get('artifacts',[])
            matches=[]
            for item in artifacts:
                if item.get('name')!=ARTIFACT or item.get('expired') is not False:continue
                try:
                    created=datetime.datetime.fromisoformat(item['created_at'].replace('Z','+00:00'))
                    started=datetime.datetime.fromisoformat(run['run_started_at'].replace('Z','+00:00'))
                    if created < started:continue
                except (KeyError,ValueError,TypeError) as exc:raise ImportFailure('Invalid candidate artifact timestamps') from exc
                validate_artifact_metadata(run,item);matches.append(item)
            require(len(matches)<=1,'Ambiguous PostgreSQL artifacts for one run attempt')
            if matches:chosen=(run,matches[0]);break
        if chosen:break
        pending=any(r.get('status')!='completed' for r in relevant)
        if relevant and not pending:raise ImportFailure('Exact-source PostgreSQL run failed or lacks its artifact')
        if time.monotonic()>=deadline:raise ImportFailure('Exact-source PostgreSQL evidence is missing or pending')
        time.sleep(min(15,max(0,deadline-time.monotonic())))
    run,artifact=chosen;parent=root/'artifacts/postgres-ci-import';parent.mkdir(parents=True,exist_ok=True);work=Path(tempfile.mkdtemp(prefix='incoming-',dir=parent));archive=work/'artifact.zip'
    try:
        download(f"/repos/{args.repository}/actions/artifacts/{artifact['id']}/zip",archive,token,artifact)
        files,comparison=validate_archive(archive,run,artifact,expected,args.repository,pr)
        record=install(root,files,{'repository':args.repository,'version':expected['version'],'sourceCommit':expected['commit'],'run':{k:run[k] for k in ['id','run_attempt','head_sha','path','repository','status','conclusion','event','run_started_at']},'artifact':{k:artifact[k] for k in ['id','name','digest','size_in_bytes','expired','workflow_run','created_at']},'prHead':pr,'comparison':comparison,'sqlExecutedByImporter':False})
        validated_postgres_import_files(root,expected['version']);archive.unlink();work.rmdir()
        print(json.dumps({'passed':True,'sourceCommit':expected['commit'],'version':expected['version'],'runId':run['id'],'artifactId':artifact['id'],'packetFiles':len(files)-3,'bindingFiles':3,'runtimeBinaryIdentityClaimed':comparison['runtimeBinaryIdentityClaimed']}))
    except BaseException as exc:
        (work/'failure.json').write_text(json.dumps({'passed':False,'sourceCommit':expected['commit'],'runId':run['id'],'artifactId':artifact['id'],'errorType':type(exc).__name__,'error':str(exc)},indent=2)+'\n',encoding='utf8')
        # Retain the exact failed download privately for CI diagnosis.
        raise

if __name__=='__main__':
    try:main()
    except (ImportFailure,KeyError,ValueError,OSError,zipfile.BadZipFile,urllib.error.URLError) as exc:
        raise SystemExit('PostgreSQL CI import failed: '+str(exc))
