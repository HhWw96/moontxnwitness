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
REPRO_FORMAT = 'moontxnwitness-ci-reproduction/v1'
FULL_FORMAT = 'moontxnwitness-postgres-ci-import/v2'
CONFIGURED_FORMAT = 'moontxnwitness-postgres-ci-import/v3'
CONFIGURED_PROFILE = 'moontxnwitness-configured-compiled-slots/v1'
CONFIGURED_ALGORITHM = 'exact-source-bridge-and-observed-output-sha256/v1'
CONFIGURED_SLOTS = {
    'configured-session-core.mjs':'configured_session_bridge',
    'source-components-core.mjs':'source_components_bridge',
    'sql-projection-core.mjs':'sql_projection_bridge',
    'sql-fetch-core.mjs':'sql_fetch_bridge',
}
ATTEMPT = re.compile(r'attempt-(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}-\d{3}Z)\.json\Z')
IMPLEMENTATION = {'moontxnwitness_capture/'+name for name in ('__init__.py','capture.py','_provenance.py','_column_profile.py','_initialization_guard.py','_source_inventory.py','presence.py')}
PRESENCE_BINDINGS = {'trace','coverage','audit','history','report','capsule','tamperChecks','reduction','protocol'}
PRESENCE_EXTRAS = {'crud-absence-reinsert-rollback':{'tamperChecks'},'negative-point-write-skew':{'reduction'},'read-committed-delete-source':{'protocol'}}

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

def configured_required(version):
    require(isinstance(version,str) and re.fullmatch(r'\d+\.\d+\.\d+',version), 'Invalid runtime profile version')
    return tuple(map(int,version.split('.'))) >= (0,3,7)

def full_format(version):
    return CONFIGURED_FORMAT if configured_required(version) else FULL_FORMAT

def configured_source_binding(root, tested):
    """Read the exact build declaration and bridge files, not a report assertion."""
    name = 'scripts/build.mjs'; raw = no_links(root,name).read_bytes()
    require(len(raw) <= 1024*1024 and tested.get(name) == digest(raw), 'Actual build declaration differs from current executed inputs')
    matches = list(re.finditer(r'\bconst\s+configuredCores\s*=\s*\{([^{}]*)\}\s*;',raw.decode('utf8')))
    require(len(matches) == 1, 'Exactly one literal configured build declaration is required')
    body = matches[0][1]; pairs = list(re.finditer(r"(['\"])([^'\"]+)\1\s*:\s*(['\"])([^'\"]+)\3",body))
    mapping = {m[2]:m[4] for m in pairs}
    remaining = body
    for match in reversed(pairs): remaining = remaining[:match.start()]+remaining[match.end():]
    require(len(pairs) == 4 and mapping == CONFIGURED_SLOTS and re.fullmatch(r'[\s,]*',remaining), 'Configured build slots/bridge mapping differs from the exact four declarations')
    files = {name:{'bytes':len(raw),'sha256':digest(raw)}}
    for bridge in CONFIGURED_SLOTS.values():
        for leaf in ('moon.pkg','bridge.mbt'):
            name = 'src/'+bridge+'/'+leaf; raw = no_links(root,name).read_bytes()
            require(0 < len(raw) <= 1024*1024 and tested.get(name) == digest(raw), 'Actual configured bridge differs from executed inputs: '+name)
            files[name] = {'bytes':len(raw),'sha256':digest(raw)}
    return {'format':CONFIGURED_PROFILE,'algorithm':CONFIGURED_ALGORITHM,'slots':dict(CONFIGURED_SLOTS),'sourceFiles':files}

def configured_runtime_binding(payload, expected, pg, tested):
    """Only these exact, independently source-bound and raw-checked slots vary."""
    current = expected['buildManifest']; current_tested = expected['testedFileSha256']
    source = expected.get('configuredRuntimeSource'); current_files = expected.get('configuredRuntimeFiles')
    require(isinstance(source,dict) and source.get('format') == CONFIGURED_PROFILE and source.get('algorithm') == CONFIGURED_ALGORITHM and source.get('slots') == CONFIGURED_SLOTS, 'Missing/unknown actual configured source binding')
    names = {'scripts/build.mjs'} | {'src/'+bridge+'/'+leaf for bridge in CONFIGURED_SLOTS.values() for leaf in ('moon.pkg','bridge.mbt')}
    rows = source.get('sourceFiles'); require(isinstance(rows,dict) and set(rows) == names, 'Incomplete/extra configured source bridge inventory')
    for name, row in rows.items():
        require(isinstance(row,dict) and type(row.get('bytes')) is int and 0 < row['bytes'] <= 1024*1024 and isinstance(row.get('sha256'),str) and SHA.fullmatch(row['sha256']) and row['sha256'] == current_tested.get(name) == tested.get(name), 'Configured source bridge/build input differs: '+name)
    current_hashes = current.get('configuredCoreSha256'); pg_hashes = pg.get('configuredCoreSha256')
    require(isinstance(current_hashes,dict) and isinstance(pg_hashes,dict) and set(current_hashes) == set(pg_hashes) == set(CONFIGURED_SLOTS), 'Manifest requires exactly four configured runtime slots')
    require(isinstance(current_files,dict) and set(current_files) == set(CONFIGURED_SLOTS), 'Actual current configured runtime file inventory is incomplete/extra')
    manifest_raw = payload.get('dist/build-manifest.json')
    require(isinstance(manifest_raw,bytes) and len(manifest_raw) <= 1024*1024 and digest(manifest_raw) == tested.get('dist/build-manifest.json') and json_bytes(manifest_raw) == pg, 'Actual PostgreSQL configured build manifest differs from executed inputs')
    observed = {}
    for name in CONFIGURED_SLOTS:
        path = 'dist/'+name; row = current_files[name]
        require(isinstance(row,dict) and type(row.get('bytes')) is int and 0 < row['bytes'] <= MAX_MEMBER and isinstance(row.get('sha256'),str) and SHA.fullmatch(row['sha256']) and row['sha256'] == current_hashes[name] == current_tested.get(path), 'Current configured runtime/manifest/execution digest differs: '+name)
        require(isinstance(pg_hashes[name],str) and SHA.fullmatch(pg_hashes[name]) and pg_hashes[name] == tested.get(path), 'PostgreSQL configured manifest/execution digest differs: '+name)
        require(path in payload and isinstance(payload[path],bytes) and 0 < len(payload[path]) <= MAX_MEMBER and digest(payload[path]) == pg_hashes[name], 'Actual PostgreSQL configured runtime bytes differ: '+name)
        observed[name] = {'bytes':len(payload[path]),'sha256':digest(payload[path])}
    return {'format':CONFIGURED_PROFILE,'algorithm':CONFIGURED_ALGORITHM,'slots':dict(CONFIGURED_SLOTS),'sourceFiles':rows,'consumerFiles':current_files,'postgresFiles':observed,'postgresManifestFile':{'bytes':len(manifest_raw),'sha256':digest(manifest_raw)},'actualPostgresBytesVerified':True,'compiledBytesEqual':{name:observed[name]['sha256'] == current_files[name]['sha256'] for name in CONFIGURED_SLOTS}}

def checkout_identity(root):
    root = Path(root).resolve()
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    require(bool(COMMIT.fullmatch(commit)), 'Invalid checked-out source commit')
    version = json_bytes((root/'package.json').read_bytes())['version']
    require(bool(re.fullmatch(r'\d+\.\d+\.\d+', version)), 'Invalid current version')
    manifest_raw = (root/'dist/build-manifest.json').read_bytes()
    manifest = json_bytes(manifest_raw)
    require(manifest.get('version') == version and manifest.get('sourceSha256') == source_fingerprint(root), 'Current build/source mismatch')
    for name, field in [('core.mjs','coreSha256'), ('capture-core.mjs','captureCoreSha256')]:
        require(digest((root/'dist'/name).read_bytes()) == manifest.get(field), 'Current runtime digest mismatch')
    node = os.environ.get('MTW_NODE', 'node')
    raw = subprocess.check_output([node, '--input-type=module', '-e',
        "import{verificationFingerprint}from'./scripts/verification-fingerprint.mjs';console.log(JSON.stringify(verificationFingerprint(process.cwd())))"],
        cwd=root)
    tested = json_bytes(raw)
    require(isinstance(tested,dict) and 0<len(tested)<=50000, 'Invalid current executable fingerprint')
    identity = {'commit':commit, 'version':version, 'buildManifest':manifest, 'testedFileSha256':tested}
    if configured_required(version):
        require(tested.get('dist/build-manifest.json') == digest(manifest_raw), 'Actual current build manifest differs from executed inputs')
        identity['configuredRuntimeSource'] = configured_source_binding(root,tested)
        files = {}
        for name in CONFIGURED_SLOTS:
            raw = no_links(root,'dist/'+name).read_bytes(); files[name] = {'bytes':len(raw),'sha256':digest(raw)}
        identity['configuredRuntimeFiles'] = files
        configured_runtime_binding({**{'dist/'+name:no_links(root,'dist/'+name).read_bytes() for name in CONFIGURED_SLOTS},'dist/build-manifest.json':manifest_raw},identity,manifest,tested)
    return identity

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
    configured = None
    if configured_required(version):
        configured = configured_runtime_binding(payload,expected,pg,tested)
        platform_members.update('dist/'+name for name in CONFIGURED_SLOTS)
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
    attempts = []
    for member in sorted(n[len(prefix):] for n in payload if n.startswith(prefix) and n[len(prefix):] not in names):
        match = ATTEMPT.fullmatch(member)
        require(match is not None, 'Unreferenced or nested PostgreSQL packet member')
        try: datetime.datetime.strptime(match[1], '%Y-%m-%dT%H-%M-%S-%fZ')
        except ValueError as exc: raise ImportFailure('Invalid PostgreSQL attempt timestamp') from exc
        value = json_bytes(payload[prefix+member]); require(isinstance(value,dict), 'PostgreSQL attempt must be an object')
        require(value.get('tool') == 'MoonTxnWitness' and value.get('version') == version, 'Wrong PostgreSQL attempt tool/version')
        require(type(value.get('passed')) is bool and type(value.get('actualDatabaseExecution')) is bool, 'Invalid PostgreSQL attempt flags')
        status = value.get('status')
        require(status in ('passed', 'failed', 'not-executed'), 'Invalid PostgreSQL attempt status')
        require((status == 'passed') == value['passed'] and (not value['passed'] or value['actualDatabaseExecution']), 'Inconsistent PostgreSQL attempt success')
        same = payload[prefix+member] == payload[prefix+'receipt.json']
        attempts.append({'path':prefix+member, 'bytes':len(payload[prefix+member]), 'sha256':digest(payload[prefix+member]), 'status':status, 'passed':value['passed'], 'matchesCurrentReceipt':same, 'role':'current-success' if same else 'historical-attempt', 'historicalReferencedPayloadVerified':False})
        names.add(member)
    if attempts:
        require(any(x['matchesCurrentReceipt'] for x in attempts), 'No PostgreSQL attempt matches the current receipt bytes')
    require({n[len(prefix):] for n in payload if n.startswith(prefix)} == names, 'Unreferenced or nested PostgreSQL packet member')
    capture = json_bytes(payload[prefix+'capture.json'])
    require(capture.get('passed') is True and capture.get('actualDatabaseExecution') is True, 'Actual PostgreSQL capture did not pass')
    selected = {prefix+n:payload[prefix+n] for n in sorted(names)}
    imported_bindings = {'source.json':payload[source_name], 'runtime-before.json':payload[before_name], 'runtime-after.json':payload[after_name]}
    for name, raw in imported_bindings.items(): selected[f'verification/releases/{version}/postgres-ci-import/{name}'] = raw
    if configured is not None:
        for name in CONFIGURED_SLOTS:
            selected[f'verification/releases/{version}/postgres-ci-import/bound-runtimes/'+name] = payload['dist/'+name]
        selected[f'verification/releases/{version}/postgres-ci-import/bound-runtimes/build-manifest.json'] = payload['dist/build-manifest.json']
    require(sum(map(len,selected.values())) <= MAX_PACKET, 'Imported packet budget exceeded')
    comparison = {'sourceVersionCompilerMatch':True,
                  'sharedExecutableInputsSha256':digest(json.dumps(shared,sort_keys=True,separators=(',',':')).encode()),
                  'sharedExecutableInputCount':len(shared),'platformRuntimeExceptions':sorted(platform_members),
                  'runtimeBinaryIdentityClaimed':pg == current,
                  'postgresBuildManifest':pg,'consumerBuildManifest':current,
                  'coreBytesEqual':pg.get('coreSha256') == current.get('coreSha256'),
                  'captureBytesEqual':pg.get('captureCoreSha256') == current.get('captureCoreSha256'),
                  'toolchainsEqual':pg.get('toolchain') == current.get('toolchain')}
    if attempts: comparison['attempts'] = attempts
    if configured is not None: comparison['configuredRuntimeBinding'] = configured
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

def validate_archive(path, run, artifact, expected, repository, pr_head=None, *, reproduction=False):
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
            if configured_required(expected['version']) and name in {'dist/'+x for x in CONFIGURED_SLOTS}|{'dist/build-manifest.json'}: keep = True
            if reproduction:
                keep = keep or name.startswith(f"verification/provenance-presence/ci-{run['id']}-{run['run_attempt']}/") or name.startswith(f"verification/releases/{expected['version']}/capture/") or name in ('verification/postgres.json','verification/capture-postgres.json')
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
    files,comparison=(validate_reproduction_payload if reproduction else validate_payload)(selected,run,artifact,expected)
    return files,comparison

def _object(payload, name):
    require(name in payload, 'Missing reproduction evidence: '+name)
    value = json_bytes(payload[name]); require(isinstance(value,dict), 'Evidence must be an object: '+name)
    return value

def _bound_file(payload, prefix, row):
    require(isinstance(row,dict), 'Invalid artifact binding')
    name = prefix + safe_name(row.get('path'))
    require(name in payload and type(row.get('bytes')) is int and row['bytes'] >= 0 and isinstance(row.get('sha256'),str) and SHA.fullmatch(row['sha256']), 'Missing/invalid bound evidence: '+name)
    require(len(payload[name]) == row['bytes'] and digest(payload[name]) == row['sha256'], 'Bound evidence changed: '+name)
    return name

def _source_map(rows, tested):
    require(isinstance(rows,dict) and 0 < len(rows) <= 128, 'Missing source bindings')
    for name, value in rows.items():
        safe_name(name)
        require(isinstance(value,str) and SHA.fullmatch(value) and tested.get(name) == value, 'Reproduction source differs: '+name)

def _implementation(receipt, tested):
    rows = receipt.get('implementationSources')
    require(isinstance(rows,dict) and rows.get('unchanged') is True and rows.get('before') == rows.get('after'), 'Implementation changed during database execution')
    before = rows.get('before'); require(isinstance(before,dict) and 0 < len(before) <= 128, 'Missing implementation inventory')
    require(set(before) == IMPLEMENTATION, 'Incomplete actual presence implementation inventory')
    for name, row in before.items():
        require(safe_name(name).startswith('moontxnwitness_capture/') and isinstance(row,dict) and type(row.get('bytes')) is int and row['bytes'] >= 0, 'Invalid implementation source row')
        _source_map({'integrations/python/'+name:row.get('sha256')}, tested)

def validate_reproduction_payload(payload, run, artifact, expected, *, require_runtime_bytes=True):
    """Validate exact-run reproduction inputs, without granting release acceptance."""
    selected, comparison = validate_payload(payload,run,artifact,expected,require_runtime_bytes=require_runtime_bytes)
    version = expected['version']; release = f'verification/releases/{version}/'
    attempts = comparison.get('attempts',[])
    require(attempts and any(x['matchesCurrentReceipt'] for x in attempts), 'Reproduction requires the matching original PostgreSQL attempt')
    require(_object(payload,release+'postgres/receipt.json').get('tool') == 'MoonTxnWitness', 'Wrong current PostgreSQL tool')
    runtime = f"verification/postgres-ci-runtime/{run['id']}-{run['run_attempt']}/"
    before = _object(payload,runtime+'postgres-ci-runtime-before.json'); after = _object(payload,runtime+'postgres-ci-runtime-after.json')
    tested = before['testedFileSha256']; pg = before['buildManifest']
    presence = f"verification/provenance-presence/ci-{run['id']}-{run['run_attempt']}/"
    presence_receipt = _object(payload,presence+'presence-receipt.json')
    require(presence_receipt.get('status') == 'passed' and presence_receipt.get('passed') is True and presence_receipt.get('actualDatabaseExecution') is True and presence_receipt.get('coreVersion') == version, 'Actual presence receipt did not pass')
    source = presence_receipt.get('captureSource'); require(isinstance(source,dict), 'Missing presence capture source')
    _source_map(source.get('files'),tested); _source_map(source.get('implementationFiles'),tested)
    require(source.get('buildManifestSourceSha256') == pg['sourceSha256'], 'Presence build/source differs')
    _implementation(presence_receipt,tested)
    require(source['implementationFiles'] == {'integrations/python/'+name:row['sha256'] for name,row in presence_receipt['implementationSources']['before'].items()}, 'Presence implementation inventories differ')
    scenarios = presence_receipt.get('scenarios'); require(isinstance(scenarios,list) and 3 <= len(scenarios) <= 128, 'Invalid presence scenario inventory')
    ready = []; seen = set()
    for scenario in scenarios:
        require(isinstance(scenario,dict) and isinstance(scenario.get('name'),str) and scenario['name'] not in seen, 'Duplicate/invalid presence scenario')
        seen.add(scenario['name']); trace = safe_name(scenario.get('trace')); require(presence+trace in payload,'Missing actual presence trace')
        status = scenario.get('expectedStatus'); require(status in ('ready','inconclusive','invalid'), 'Unknown presence scenario status')
        bindings = scenario.get('artifactBindings')
        require(isinstance(bindings,dict) and {'trace','coverage','audit'} <= set(bindings) <= PRESENCE_BINDINGS, 'Incomplete/unknown presence artifact bindings')
        for row in bindings.values(): _bound_file(payload,presence,row)
        require(bindings['trace']['path'] == trace, 'Presence trace binding differs')
        if status != 'ready': continue
        ready.append(scenario)
        require(all(scenario.get(k) is True for k in ('committedAuditExactlyMatchesCapturedWrites','initialPresenceMatchedLockedAudit','uninstallPreservedBusinessRows')), 'Presence source/audit assertion did not pass')
        required = {'trace','coverage','audit','history','report','capsule'} | PRESENCE_EXTRAS.get(scenario['name'],set())
        require(required <= set(bindings), 'Incomplete scenario-specific presence artifact bindings')
        history = _object(payload,presence+bindings['history']['path'])
        capsule = _object(payload,presence+bindings['capsule']['path'])
        require(isinstance(capsule.get('historyText'),str) and json_bytes(capsule['historyText'].encode()) == history, 'Presence capsule/history differ')
        require(bindings['capsule']['path'] == scenario['name']+'.capsule.json', 'Presence consumer capsule differs')
    require(len(ready) == 3 and type(presence_receipt.get('replayedCapsules')) is int and presence_receipt['replayedCapsules'] == 3, 'Exactly three ready presence capsules are required')
    init_name = presence+'initialization/initialization-receipt.json'; init = _object(payload,init_name)
    require(type(init.get('schema')) is int and init['schema'] == 1 and init.get('passed') is True and init.get('actualDatabaseExecution') is True and init.get('packageVersion') == version, 'Actual initialization receipt did not pass')
    for key in ('analyzerExecuted','releaseAcceptance','coreProofImplemented','sourceClosureVerified','formalPerformanceMeasured'):
        require(init.get(key) is False, 'Initialization receipt overstates its scope: '+key)
    _implementation(init,tested)
    fixture = init.get('fixtureSources'); require(isinstance(fixture,dict) and fixture.get('unchanged') is True and fixture.get('before') == fixture.get('after'), 'Initialization fixture changed')
    _source_map({'experiments/provenance/initialization_postgres.py':fixture.get('after')},tested)
    cases = init.get('cases'); require(isinstance(cases,list) and len(cases) >= 4 and all(isinstance(x,dict) and x.get('passed') is True for x in cases), 'Initialization controls did not pass')
    confirmed = [x for x in cases if x.get('name') == 'actual-confirmed-commit-and-crud']; require(len(confirmed) == 1 and confirmed[0].get('initializationAck',{}).get('actualCommitConfirmed') is True and confirmed[0]['initializationAck'].get('commandTag') == 'COMMIT', 'Missing actual initialization COMMIT confirmation')
    for row in cases:
        if 'trace' in row: require(presence+'initialization/'+safe_name(row['trace']) in payload,'Missing initialization trace')
    top_pg = _object(payload,'verification/postgres.json')
    require(top_pg == _object(payload,release+'postgres/receipt.json'), 'Top-level PostgreSQL receipt differs')
    top_capture = _object(payload,'verification/capture-postgres.json'); capture_path = safe_name(top_capture.get('path'))
    capture_prefix = 'verification/'+capture_path+'/'
    require(capture_path.startswith(f'releases/{version}/capture/') and len(capture_path.split('/')) == 4, 'Capture reference is not current-version single-run evidence')
    capture = _object(payload,capture_prefix+'receipt.json')
    require({k:v for k,v in top_capture.items() if k != 'path'} == capture, 'Capture pointer/receipt differ')
    require(capture.get('passed') is True and capture.get('actualDatabaseExecution') is True and capture.get('version') == version, 'Actual capture receipt did not pass')
    capture_source = capture.get('captureSource'); require(isinstance(capture_source,dict),'Missing actual capture source')
    for field, name in [('adapterSha256','integrations/python/moontxnwitness_capture/capture.py'),('fixtureSha256','scripts/capture-postgres-test.py'),('e2eSha256','scripts/capture-postgres-e2e.mjs')]:
        _source_map({name:capture_source.get(field)},tested)
    require(capture_source.get('captureCoreSha256') == pg['captureCoreSha256'] and capture_source.get('analysisCoreSha256') == pg['coreSha256'], 'Capture runtime differs from executed PostgreSQL runtime')
    capture_scenarios = capture.get('scenarios'); require(isinstance(capture_scenarios,list) and capture_scenarios, 'Missing capture scenarios')
    capsule_count = 0
    for row in capture_scenarios:
        require(isinstance(row,dict) and isinstance(row.get('name'),str) and row.get('expectedStatus') in ('ready','inconclusive','invalid'), 'Invalid capture scenario')
        require(capture_prefix+safe_name(row.get('trace')) in payload,'Missing actual capture trace')
        if row['expectedStatus'] == 'ready':
            capsule_count += 1
            for suffix in ('coverage.json','report.json','capsule.json'):
                require(capture_prefix+safe_name(row['name']+'.'+suffix) in payload,'Missing ready capture output')
    require(type(capture.get('replayedCapsules')) is int and capture['replayedCapsules'] == capsule_count and capsule_count > 0, 'Capture replay count differs')
    prefixes = (presence,capture_prefix)
    raw_names = [n for n in payload if n.startswith(prefixes) or n in ('verification/postgres.json','verification/capture-postgres.json')]
    require(len(raw_names) <= 2048, 'Reproduction tree member budget exceeded')
    for name in raw_names: safe_name(name); selected[name] = payload[name]
    require(sum(map(len,selected.values())) <= MAX_PACKET, 'Reproduction byte budget exceeded')
    receipts = {}
    for kind, prefix, leaf in [('presence',presence,'presence-receipt.json'),('initialization',presence+'initialization/','initialization-receipt.json'),('legacy',release+'postgres/','receipt.json'),('capture',capture_prefix,'receipt.json')]:
        receipts[kind] = {'path':prefix[len('verification/'):].rstrip('/'),'receiptFile':leaf,'sha256':digest(payload[prefix+leaf])}
    database = {'schema':1,'phase':'exact-run-ci-reproduction','version':version,'passed':True,'actualDatabaseExecution':True,'releaseReady':False,'sourceCommit':expected['commit'],'runId':run['id'],'runAttempt':run['run_attempt'],'artifactId':artifact['id'],'buildManifestBefore':pg,'buildManifestAfter':after['buildManifest'],'testedFileSha256Before':tested,'testedFileSha256After':after['testedFileSha256'],'receipts':receipts,'exitCode':0,'scope':'Original exact-source PostgreSQL CI reproduction; not final release acceptance; platform runtime bytes are recorded separately.'}
    encode = lambda value:(json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
    db_name = release+'database-ci.json'; selected[db_name] = encode(database)
    reproduction = {'format':REPRO_FORMAT,'version':version,'sourceCommit':expected['commit'],'releaseReady':False,'databaseEvidence':'database-ci.json','databaseEvidenceSha256':digest(selected[db_name]),'runId':run['id'],'runAttempt':run['run_attempt'],'artifactId':artifact['id'],'artifactDigest':artifact['digest'],'rawEvidence':{n:{'bytes':len(v),'sha256':digest(v)} for n,v in sorted(selected.items())},'scope':'Installation reproduction only; final acceptance is not synthesized.'}
    selected[release+'reproduction.json'] = encode(reproduction)
    comparison['reproduction'] = {'format':REPRO_FORMAT,'presenceReadyCapsules':3,'initializationReceiptSha256':digest(payload[init_name]),'presencePrefix':presence,'capturePrefix':capture_prefix,'releaseReady':False}
    return selected, comparison

def install(root, files, record):
    root=Path(root).resolve();version=record['version'];index=f'verification/releases/{version}/postgres-ci-import/receipt.json'
    require(not configured_required(version), 'Configured compiled slots require the full v3 reproduction importer')
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

def _reproduction_scope(name, version, run, comparison):
    safe_name(name); release = f'verification/releases/{version}/'
    detail = comparison.get('reproduction',{})
    presence = f"verification/provenance-presence/ci-{run['id']}-{run['run_attempt']}/"
    capture = detail.get('capturePrefix')
    require(detail.get('format') == REPRO_FORMAT and detail.get('presencePrefix') == presence and isinstance(capture,str) and capture.startswith(release+'capture/'), 'Invalid reproduction destination scope')
    return (name.startswith((release+'postgres/',release+'postgres-ci-import/',presence,capture)) or
            name in (release+'database-ci.json',release+'reproduction.json','verification/postgres.json','verification/capture-postgres.json'))

def _original_pointer(root, name):
    require(name in ('verification/postgres.json','verification/capture-postgres.json'), 'Not an approved rolling pointer')
    result = subprocess.run(['git','show','HEAD:'+name],cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    require(result.returncode == 0 and len(result.stdout) <= 8*1024*1024, 'Existing pointer is not an original tracked HEAD file')
    return result.stdout

def install_reproduction(root, files, record):
    root = Path(root).resolve(); version = record['version']
    require(isinstance(files,dict) and 20 <= len(files) <= 2200, 'Invalid reproduction install inventory')
    index = f'verification/releases/{version}/postgres-ci-import/receipt.json'
    require(index not in files, 'Import receipt cannot be supplied as raw evidence')
    files = dict(files); previous = []
    if configured_required(version):
        binding = record.get('comparison',{}).get('configuredRuntimeBinding',{})
        require(binding.get('format') == CONFIGURED_PROFILE and binding.get('algorithm') == CONFIGURED_ALGORITHM and binding.get('slots') == CONFIGURED_SLOTS and binding.get('actualPostgresBytesVerified') is True, 'Configured installation requires the new actual-byte runtime binding')
        for name in [*CONFIGURED_SLOTS,'build-manifest.json']:
            key = f'verification/releases/{version}/postgres-ci-import/bound-runtimes/'+name
            spec = binding.get('postgresManifestFile') if name == 'build-manifest.json' else binding.get('postgresFiles',{}).get(name)
            require(key in files and isinstance(spec,dict) and {'bytes':len(files[key]),'sha256':digest(files[key])} == spec, 'Configured installation lost a verified raw runtime/manifest')
    for name in files: require(_reproduction_scope(name,version,record['run'],record['comparison']), 'Reproduction destination outside verified scope')
    # Only producer-owned rolling pointers may differ from checkout bytes. Retain
    # their exact tracked originals before atomically installing current-run data.
    for name in ('verification/postgres.json','verification/capture-postgres.json'):
        path = no_links(root,name)
        backup = f'verification/releases/{version}/postgres-ci-import/previous-pointers/'+name.split('/')[-1]
        if path.exists() and path.read_bytes() != files[name]:
            original = _original_pointer(root,name); require(path.read_bytes() == original, 'Rolling pointer changed outside this importer')
            files[backup] = original; previous.append(backup)
        elif no_links(root,backup).exists():
            original = no_links(root,backup).read_bytes(); require(original == _original_pointer(root,name), 'Retained rolling pointer is not the original tracked file')
            files[backup] = original; previous.append(backup)
    origins = {name:{'sourcePath':'verification/'+name.split('/')[-1],'sourceCommit':record['sourceCommit'],'bytes':len(files[name]),'sha256':digest(files[name])} for name in previous}
    record = {**record,'format':full_format(version),'previousPointerFiles':previous,'previousPointerOrigins':origins,'files':{n:{'bytes':len(v),'sha256':digest(v)} for n,v in sorted(files.items())}}
    if configured_required(version): record['runtimeBindingAlgorithm'] = CONFIGURED_ALGORITHM
    encoded = (json.dumps(record,sort_keys=True,indent=2)+'\n').encode(); all_files = {**files,index:encoded}
    for name, raw in all_files.items():
        path = no_links(root,name)
        if path.exists():
            original_pointer = name in ('verification/postgres.json','verification/capture-postgres.json') and (f'verification/releases/{version}/postgres-ci-import/previous-pointers/'+name.split('/')[-1]) in previous
            require(path.is_file() and (path.read_bytes() == raw or original_pointer and path.read_bytes() == _original_pointer(root,name)), 'Refusing to replace existing reproduction evidence')
    for name, raw in sorted(all_files.items(),key=lambda row:(row[0] in ('verification/postgres.json','verification/capture-postgres.json'),row[0])):
        path = no_links(root,name); path.parent.mkdir(parents=True,exist_ok=True)
        try:
            with path.open('xb') as stream: stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        except FileExistsError:
            if path.read_bytes() == raw: continue
            backup = f'verification/releases/{version}/postgres-ci-import/previous-pointers/'+name.split('/')[-1]
            require(name in ('verification/postgres.json','verification/capture-postgres.json') and backup in previous and path.read_bytes() == files[backup], 'Conflicting reproduction import')
            require(no_links(root,backup).read_bytes() == files[backup], 'Original rolling pointer is not safely retained')
            temporary = path.with_name(path.name+'.ci-import-new')
            try:
                with temporary.open('xb') as stream: stream.write(raw); stream.flush(); os.fsync(stream.fileno())
                require(path.read_bytes() == files[backup], 'Rolling pointer changed during import')
                os.replace(temporary,path)
            finally:
                if temporary.exists(): temporary.unlink()
    return record

def validated_ci_reproduction_files(root, version):
    """Production allowlist: only a fully revalidated exact-run reproduction packet."""
    root = Path(root).resolve(); name = f'verification/releases/{version}/postgres-ci-import/receipt.json'; path = no_links(root,name)
    if not path.exists(): return {}
    record = json_bytes(path.read_bytes()); require(record.get('format') == full_format(version) and record.get('version') == version, 'A narrow/legacy import cannot authorize reproduction files')
    expected = checkout_identity(root); require(record.get('sourceCommit') == expected['commit'], 'Stale reproduction source')
    rows = record.get('files'); require(isinstance(rows,dict) and 20 <= len(rows) <= 2200, 'Invalid reproduction closure')
    run = record['run']; artifact = record['artifact']; repository = os.environ.get('GITHUB_REPOSITORY',record['repository'])
    require(record['repository'].lower() == repository.lower(), 'Imported repository differs from this job')
    trusted_pr = event_pr_head(repository,expected['commit']); require(record.get('prHead') == trusted_pr, 'Imported PR head differs from this event')
    validate_run(run,repository,expected['commit'],trusted_pr); validate_artifact_metadata(run,artifact)
    payload = {}; total = 0
    for member, spec in rows.items():
        require(member != name and _reproduction_scope(member,version,run,record['comparison']), 'Unapproved reproduction member')
        target = no_links(root,member); size = target.stat().st_size; total += size
        require(size <= MAX_PACKET and total <= MAX_PACKET, 'Reproduction size budget exceeded')
        raw = target.read_bytes(); require(isinstance(spec,dict) and type(spec.get('bytes')) is int and len(raw) == spec['bytes'] and digest(raw) == spec.get('sha256'), 'Imported reproduction file changed')
        payload[member] = raw
    base = f'verification/releases/{version}/postgres-ci-import/'; binding = f"verification/postgres-ci-runtime/{run['id']}-{run['run_attempt']}/"
    translated = {n:v for n,v in payload.items() if not n.startswith(base)}
    translated['verification/postgres-ci-source.json'] = payload[base+'source.json']
    translated[binding+'postgres-ci-runtime-before.json'] = payload[base+'runtime-before.json']
    translated[binding+'postgres-ci-runtime-after.json'] = payload[base+'runtime-after.json']
    if configured_required(version):
        for member in CONFIGURED_SLOTS: translated['dist/'+member] = payload[base+'bound-runtimes/'+member]
        translated['dist/build-manifest.json'] = payload[base+'bound-runtimes/build-manifest.json']
        require(record.get('runtimeBindingAlgorithm') == CONFIGURED_ALGORITHM, 'Configured import algorithm is unknown')
    rebuilt, comparison = validate_reproduction_payload(translated,run,artifact,expected,require_runtime_bytes=False)
    previous = record.get('previousPointerFiles',[]); require(isinstance(previous,list) and len(previous) <= 2 and len(set(previous)) == len(previous), 'Invalid previous-pointer inventory')
    for member in previous:
        allowed = {base+'previous-pointers/'+leaf:'verification/'+leaf for leaf in ('postgres.json','capture-postgres.json')}
        require(member in allowed and member in payload and payload[member] == _original_pointer(root,allowed[member]), 'Previous rolling pointer differs from tracked HEAD')
        rebuilt[member] = payload[member]
    origins = {member:{'sourcePath':'verification/'+member.split('/')[-1],'sourceCommit':expected['commit'],'bytes':len(payload[member]),'sha256':digest(payload[member])} for member in previous}
    require(record.get('previousPointerOrigins') == origins, 'Previous pointer source/hash metadata differs')
    require(rebuilt == payload and comparison == record.get('comparison'), 'Reproduction manifest/closure differs from original evidence')
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
        files,comparison=validate_archive(archive,run,artifact,expected,args.repository,pr,reproduction=True)
        record=install_reproduction(root,files,{'repository':args.repository,'version':expected['version'],'sourceCommit':expected['commit'],'run':{k:run[k] for k in ['id','run_attempt','head_sha','path','repository','status','conclusion','event','run_started_at']},'artifact':{k:artifact[k] for k in ['id','name','digest','size_in_bytes','expired','workflow_run','created_at']},'prHead':pr,'comparison':comparison,'sqlExecutedByImporter':False})
        validated_ci_reproduction_files(root,expected['version']);archive.unlink();work.rmdir()
        print(json.dumps({'passed':True,'sourceCommit':expected['commit'],'version':expected['version'],'runId':run['id'],'artifactId':artifact['id'],'packetFiles':sum(n.startswith(f"verification/releases/{expected['version']}/postgres/") for n in files),'evidenceFiles':len(files),'bindingFiles':3,'releaseReady':False,'runtimeBinaryIdentityClaimed':comparison['runtimeBinaryIdentityClaimed']}))
    except BaseException as exc:
        (work/'failure.json').write_text(json.dumps({'passed':False,'sourceCommit':expected['commit'],'runId':run['id'],'artifactId':artifact['id'],'errorType':type(exc).__name__,'error':str(exc)},indent=2)+'\n',encoding='utf8')
        # Retain the exact failed download privately for CI diagnosis.
        raise

if __name__=='__main__':
    try:main()
    except (ImportFailure,KeyError,ValueError,OSError,zipfile.BadZipFile,urllib.error.URLError) as exc:
        raise SystemExit('PostgreSQL CI import failed: '+str(exc))
