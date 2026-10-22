"""Independent, read-only audit of published ORM database evidence.

Uses only the Python standard library. It never connects to PostgreSQL, installs
dependencies, imports a collector or changes source expectations. Optional Node
checks reuse the existing built CLI. Each invocation retains its first result.
"""
from __future__ import annotations
import argparse
import ast
import base64
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import traceback
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
MODULES = ('orm.py', '_orm_policy.py', '_orm_async.py', '_orm_raw_async.py', '_orm_source_sink.py')
FIELDS = ('id', 'email', 'hashed_password', 'is_active', 'is_superuser', 'is_verified')
IDS = tuple('00000000-0000-4000-8000-00000000000' + str(i) for i in (1, 2, 3))
EXPECTED_CANDIDATE = 'b5f7e88396931f0051f205cb845ff05c83224e622ea02ddf06115ab4b6fd38f5'

def binding(path):
    data = path.read_bytes()
    return {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}

def load(path):
    return json.loads(path.read_text(encoding='utf8'))

def public_text(value):
    # Transport paths do not contribute to evidence semantics. Keep their raw
    # byte digest, but never publish a personal workspace prefix in a log.
    for text in (str(ROOT), ROOT.as_posix(), json.dumps(str(ROOT), ensure_ascii=False)[1:-1]):
        value = value.replace(text, '<repository>')
    return value

def plain(value):
    if isinstance(value, list): return [plain(item) for item in value]
    if isinstance(value, dict):
        if value.get('captureType') == 'bytes':
            assert set(value) == {'captureType', 'base64'}
            return base64.b64decode(value['base64'], validate=True)
        if value.get('captureType') == 'UUID':
            assert str(uuid.UUID(value['value'])) == value['value']
            return value['value']
        return {key: plain(item) for key, item in value.items()}
    return value

def read_sources(path):
    lines = path.read_bytes().splitlines(keepends=True)
    assert lines and len(lines) <= 16384
    digest = hashlib.sha256()
    records = []
    for index, raw in enumerate(lines, 1):
        assert raw.endswith(b'\n') and len(raw) <= 128 * 1024
        row = json.loads(raw)
        assert row['sourceSeq'] == index
        if row['kind'] == 'seal':
            assert index == len(lines) and row['sourceRecords'] == index - 1
            assert row['prefixSha256'] == digest.hexdigest()
        digest.update(raw)
        records.append(row)
    assert records[0]['kind'] == 'header' and records[0]['coreProofAccepted'] is False
    assert records[-1]['kind'] == 'seal'
    assert len(b''.join(lines)) <= 16 * 1024 * 1024
    return records

def image(raw, key):
    value = None if raw is None else json.loads(raw)
    if value is not None:
        assert set(value) == set(FIELDS) and value['id'] == key
        assert type(value['email']) is str and len(value['email']) <= 320
        assert type(value['hashed_password']) is str and len(value['hashed_password']) <= 1024
        assert all(type(value[name]) is bool for name in FIELDS[3:])
    return value

def decode_batch(batch, events):
    statement, rows = events[batch['statement']], events[batch['businessRowsEvent']]
    assert statement['kind'] == 'statement' and rows['kind'] == 'rows'
    assert batch['tx'] == statement['tx'] == rows['tx']
    assert rows['statement'] == statement['seq'] and rows['complete'] is True
    assert batch['originalSql'] == statement['sql']
    assert batch['executedSql'] == statement['executedSql']
    assert batch['parameters'] == statement['parameters']
    assert batch['mappingId'] == statement['mappingId']
    result = plain(batch['actualPGresult'])
    assert result['status'] == 2 and result['ntuples'] == result['commandTuples'] == 1
    assert len(result['fields']) == 8 and all(field['format'] == 0 for field in result['fields'])
    values = [field['raw'] for field in result['fields']]
    observation = plain(batch['observation'])
    assert observation['proposedWireOnly'] is True and observation['coverageGap']
    assert observation['mappingId'] == batch['mappingId']
    operation = batch['operation']
    if operation == 'get':
        assert [field['oid'] for field in result['fields']] == [2950, 1043, 1043, 16, 16, 16, 25, 16]
        assert result['fields'][1]['typmod'] == 324 and result['fields'][2]['typmod'] == 1028
        assert all(value is None or type(value) is bytes for value in values)
        assert values[7] in (b't', b'f')
        present = values[7] == b't'
        version = values[6].decode('ascii')
        assert str(uuid.UUID(version)) == version
        row = [None if value is None else value.decode('utf8') for value in values[:3]]
        row += [None if value is None else {b't': True, b'f': False}[value] for value in values[3:6]]
        key = next(iter(batch['parameters'].values()))
        assert key in IDS
        assert observation['source'] == {'key': key, 'version': version, 'present': present}
        assert observation['rows'] == ([row] if present else [])
        assert plain(rows['rows']) == ([row] if present else [])
        assert observation['serverRows' if present else 'presenceRows'] == [row + [version, present]]
        assert result['commandTag'] == b'SELECT 1'
        assert batch['businessCommand']['tag'] == 'SELECT ' + str(int(present))
        assert batch['businessCommand']['rowcount'] == int(present)
        if present: assert row[0] == key
        else: assert row == [None] * 6
        return None
    assert operation in ('create', 'update', 'delete')
    assert [field['oid'] for field in result['fields']] == [25, 25, 25, 16, 16, 1043, 1043, 25]
    assert result['fields'][5]['typmod'] == result['fields'][6]['typmod'] == 12292
    key, predecessor, version = [value.decode('ascii') for value in values[:3]]
    assert key in IDS and str(uuid.UUID(predecessor)) == predecessor and str(uuid.UUID(version)) == version
    assert predecessor != version and values[3] in (b't', b'f') and values[4] in (b't', b'f')
    old_present, new_present = values[3] == b't', values[4] == b't'
    old_image, new_image = image(values[5], key), image(values[6], key)
    action = values[7].decode('ascii')
    assert action == {'create': 'INSERT', 'update': 'UPDATE', 'delete': 'DELETE'}[operation]
    assert old_present == (old_image is not None) and new_present == (new_image is not None)
    assert observation['effectRows'] == [[key, predecessor, version, old_present, new_present, old_image, new_image, action]]
    assert rows['rows'] == [] and observation['rows'] == []
    expected_tag = 'INSERT 0 1' if operation == 'create' else action + ' 1'
    assert result['commandTag'] == expected_tag.encode()
    assert batch['businessCommand']['tag'] == expected_tag
    assert batch['businessCommand']['description'] is None and batch['businessCommand']['rownumber'] is None
    return {'key': key, 'predecessor': predecessor, 'version': version,
        'oldPresent': old_present, 'newPresent': new_present, 'oldImage': old_image, 'newImage': new_image, 'action': action}

def audit_mode(path):
    receipt = load(path / 'database-receipt.json')
    assert receipt['passed'] is True and receipt['actualDatabaseExecution'] is True and receipt['failure'] is None
    assert receipt['serverVersion'] in range(180000, 190000)
    assert receipt['coreProofAccepted'] is False and receipt['completeCapture'] is False
    trace = load(path / 'diagnostic-trace.json')
    assert binding(path / 'diagnostic-trace.json') == {k: receipt['diagnostic'][k] for k in ('sha256', 'bytes')}
    assert receipt['diagnostic']['complete'] is False and trace['traceSchema'] == 3
    assert len(trace['events']) == 92 and trace['scope']['exclusiveWriters'] is True
    events = {event['seq']: event for event in trace['events']}
    assert list(events) == list(range(1, 93))
    records = read_sources(path / 'source-observations.jsonl')
    assert len(records) == receipt['sourceObservations']['records'] == 147
    assert binding(path / 'source-observations.jsonl') == {k: receipt['sourceObservations'][k] for k in ('sha256', 'bytes')}
    installation = next(record for record in records if record['kind'] == 'installation')
    final = next(record for record in records if record['kind'] == 'final-effect-ledger')
    assert installation['knownIds'] == list(IDS)
    assert installation['metadata'] == load(path / 'installation.json')
    controls = {record['sourceSeq']: record for record in records if record['kind'] == 'control-query'}
    for window in (installation['metadata']['initializationWindow'], final['finalizationWindow']):
        ack = window[-1]
        actual = controls[ack['querySeq']]
        assert ack['kind'] == 'commit' and ack['commandTag'] == actual['sql'] == 'COMMIT'
        assert actual['transactionStatusBefore'] == 'INTRANS' and actual['transactionStatusAfter'] == 'IDLE'
        assert actual['result']['status'] == 1 and actual['result']['commandTag'] == 'COMMIT'
        assert plain(actual['result']['actualPGresult']['commandTag']) == b'COMMIT'
    batches = [record for record in records if record['kind'] == 'source-batch']
    assert len(batches) == 21
    effects = {}
    for batch in batches:
        effect = decode_batch(batch, events)
        if effect is not None: effects[batch['businessRowsEvent']] = effect
    active, committed, snapshots = {}, [], {}
    for event in trace['events']:
        kind, tx = event['kind'], event.get('tx')
        if kind == 'begin':
            assert tx not in active
            active[tx], snapshots[tx] = [], []
        elif event['seq'] in effects:
            active[tx].append(effects[event['seq']])
        elif kind == 'savepoint': snapshots[tx].append((event['instance'], len(active[tx])))
        elif kind == 'rollback_to':
            position = next(i for i in range(len(snapshots[tx]) - 1, -1, -1) if snapshots[tx][i][0] == event['instance'])
            active[tx] = active[tx][:snapshots[tx][position][1]]
            snapshots[tx] = snapshots[tx][:position + 1]
        elif kind == 'commit_ok': committed.extend(active.pop(tx)); snapshots.pop(tx)
        elif kind == 'rollback_ok': active.pop(tx); snapshots.pop(tx)
    assert not active
    assert sorted(committed, key=lambda x: x['version']) == sorted(final['ledger'], key=lambda x: x['version'])
    assert final['ledger'] == load(path / 'effect-ledger.json') and len(committed) == receipt['ledgerCount'] == 7
    state = deepcopy(installation['metadata']['initialState'])
    for effect in committed:
        before = state[effect['key']]
        assert before == {'version': effect['predecessor'], 'present': effect['oldPresent'], 'image': effect['oldImage']}
        state[effect['key']] = {'version': effect['version'], 'present': effect['newPresent'], 'image': effect['newImage']}
    assert state == final['state']
    assert all(effect['key'] != IDS[1] for effect in committed)
    assert all(effect['newImage'] is None or effect['newImage']['email'] != 'discarded@example.invalid' for effect in committed)
    assert any(effect['oldImage'] == effect['newImage'] and effect['oldPresent'] for effect in committed)
    assert any(effect['action'] == 'DELETE' for effect in committed)
    semantic = sorted([{key: effect[key] for key in ('key','action','oldPresent','newPresent','oldImage','newImage')} for effect in committed], key=lambda x: json.dumps(x, sort_keys=True))
    assert semantic == receipt['semanticLedger']
    assert {key: {'present': row['present'], 'image': row['image']} for key, row in state.items()} == receipt['semanticState']
    errors = [event for event in trace['events'] if 'error' in event]
    assert {(event['error']['class'], event['error']['sqlstate']) for event in errors} == {('UniqueViolation', '23505'), ('NotNullViolation', '23502')}
    for event in errors:
        assert event['complete'] is False and event['rows'] == []
        later = [row for row in trace['events'] if row['seq'] > event['seq'] and row.get('tx') == event['tx']]
        assert any(row['kind'] == 'rollback_ok' for row in later) and not any(row['kind'] == 'commit_ok' for row in later)
    gaps = {gap['code'] for gap in receipt['coverageGaps']}
    assert 'orm_core_source_proof_unavailable' in gaps and 'orm_sql_unmapped' in gaps
    assert receipt['journal']['complete'] is False and receipt['journal']['sourceClosed'] is False
    index = load(path / 'journal/journal-index.json')
    assert binding(path / 'journal/journal-index.json')['sha256'] == receipt['journal']['indexSha256']
    index_digest = index.pop('indexSha256')
    assert hashlib.sha256(json.dumps(index, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest() == index_digest
    journal_events = []
    for segment in index['segments']:
        segment_path = path / 'journal' / segment['name']
        assert binding(segment_path) == {k: segment[k] for k in ('sha256', 'bytes')}
        entries = [json.loads(line) for line in segment_path.read_bytes().splitlines()]
        assert len(entries) == segment['eventCount']
        journal_events.extend(entries)
    assert journal_events == trace['events'] and index['eventCount'] == index['durableSeq'] == 92
    replies = [row for connection in receipt['nativeBusinessReplies'] for row in connection['replies']]
    assert not receipt['nativeReplyCoverageGap'] and not receipt['controlCoverageGaps']
    counts = Counter()
    for row in replies:
        assert row['acknowledged'] is True and row['resultStatus'] == 1 and row['after'] == 0
        assert row['commandTag'] == row['request'] and row['request'] in ('COMMIT', 'ROLLBACK')
        counts[row['request']] += 1
    assert dict(counts) == {'COMMIT': 11, 'ROLLBACK': 14}
    assert receipt['nativeAckBoundary']['commitConfirmed'] == 11 and receipt['nativeAckBoundary']['rollbackConfirmed'] == 14
    assert receipt['nativeAckBoundary']['unknownReplies'] == 0
    return {'receipt': receipt, 'facts': len(batches), 'committedEffects': len(committed), 'rawEffectFacts': len(effects),
        'traceEvents': len(events), 'sourceRecords': len(records), 'controlQueries': len(controls), 'nativeReplies': dict(counts)}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, default=HERE.parent / 'orm-database')
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--original-run', type=Path)
    parser.add_argument('--run-core', action='store_true')
    args = parser.parse_args()
    evidence = args.evidence.resolve()
    run = HERE / ('run-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    run.mkdir(parents=True, exist_ok=False)
    receipt = {'schema': 1, 'kind': 'independent-ai-orm-raw-database-evidence-review', 'passed': False,
        'reviewerRole': 'Independent AI technical reviewer; not collector or database-harness author',
        'databaseReexecuted': False, 'dependencyInstallationExecuted': False, 'buildExecuted': False,
        'formalPerformanceMeasured': False, 'humanAcceptance': False, 'contestApproval': False,
        'analysisCoverageAccepted': False, 'completeCapture': False, 'history': None, 'checks': []}
    try:
        manifest_path = evidence / args.manifest
        assert binding(manifest_path)['sha256'] == args.manifest_sha256
        public_manifest = load(manifest_path)
        rows = public_manifest['copiedFiles']
        assert isinstance(rows, list)
        names = set()
        for entry in rows:
            name = entry['path']
            assert name not in names and 'private' not in Path(name).parts
            names.add(name)
            actual_path = (evidence / name).resolve()
            assert actual_path.is_relative_to(evidence)
            assert binding(actual_path) == {k: entry[k] for k in ('sha256', 'bytes')}, name
        receipt['checks'].append({'group': 'public-file-manifest', 'passed': True, 'files': len(rows), 'sha256': args.manifest_sha256})
        # Layout-specific verification is filled only after the public closure is frozen.
        details = audit_public_closure(evidence, public_manifest, args, run)
        receipt.update(details)
        assert binding(manifest_path)['sha256'] == args.manifest_sha256
        for entry in rows:
            assert binding(evidence / entry['path']) == {k: entry[k] for k in ('sha256', 'bytes')}
        receipt['evidenceUnchanged'] = True
        receipt['passed'] = True
    except BaseException as error:
        receipt['failure'] = {'class': type(error).__name__, 'message': public_text(str(error)),
            'frames': [{'file': Path(frame.filename).name, 'line': frame.lineno, 'function': frame.name} for frame in traceback.extract_tb(error.__traceback__)]}
    receipt['auditImplementation'] = {'path': 'verification/releases/0.1.3/orm-independent/check.py', **binding(Path(__file__))}
    (run / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'passed': receipt['passed'], 'receipt': (run / 'receipt.json').relative_to(ROOT).as_posix(), 'groups': len(receipt['checks'])}))
    return 0 if receipt['passed'] else 1

def seal_sources(records):
    records = deepcopy(records)
    records = [row for row in records if row['kind'] != 'seal']
    raw = b''
    for index, row in enumerate(records, 1):
        row['sourceSeq'] = index
        raw += (json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode()
    footer = {'kind': 'seal', 'sourceSeq': len(records) + 1, 'sourceRecords': len(records),
        'prefixSha256': hashlib.sha256(raw).hexdigest()}
    return raw + (json.dumps(footer, sort_keys=True, separators=(',', ':')) + '\n').encode()

def audit_core(database, run):
    runtime = {path.name: binding(path) for path in (ROOT / 'dist').iterdir() if path.is_file()}
    build = load(ROOT / 'dist/build-manifest.json')
    assert build['version'] == '0.1.3'
    assert runtime['core.mjs']['sha256'] == build['coreSha256']
    assert runtime['capture-core.mjs']['sha256'] == build['captureCoreSha256']
    earlier = ROOT / 'verification/releases/0.1.3/orm-core/run-20261022T113857Z-7cfa76b8'
    earlier_receipt = load(earlier / 'receipt.json')
    assert earlier_receipt['passed'] is True and earlier_receipt['buildManifest'] == build
    output = run / 'core'
    output.mkdir()
    calls = []
    def invoke(trace, source, name):
        report_path = output / (name + '.json')
        command = ['node', 'dist/moontxnwitness.mjs', 'inspect-orm-source-v3',
            trace.relative_to(ROOT).as_posix(), source.relative_to(ROOT).as_posix(),
            '--output', report_path.relative_to(ROOT).as_posix()]
        result = subprocess.run(command, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=60, check=False)
        transport = result.stdout + result.stderr
        (output / (name + '-first.log')).write_text(public_text(transport.decode('utf8', errors='replace')), encoding='utf8')
        row = {'case': name, 'exitCode': result.returncode,
            'trace': binding(trace), 'sources': binding(source),
            'firstLog': binding(output / (name + '-first.log')),
            'transportOriginal': {'sha256': hashlib.sha256(transport).hexdigest(), 'bytes': len(transport)},
            'transportWorkspacePrefixRedacted': True}
        if report_path.is_file(): row['report'] = binding(report_path)
        calls.append(row)
        return result.returncode, load(report_path) if report_path.is_file() else None
    for mode in ('cache-disabled', 'cache-enabled'):
        source_path = database / mode / 'source-observations.jsonl'
        trace_path = database / mode / 'diagnostic-trace.json'
        code, report = invoke(trace_path, source_path, mode)
        assert code == 0 and report == load(earlier / (mode + '.json'))
        assert report['analysisCoverageAccepted'] is False and report['history'] is None
        assert report['controlProfileComplete'] is True
        assert len(report['provenStatements']) == len(report['provenFacts']) == 21
        assert report['traceSha256'] == binding(trace_path)['sha256'] and report['sourceJournalSha256'] == binding(source_path)['sha256']
    base = database / 'cache-enabled'
    original_trace = load(base / 'diagnostic-trace.json')
    original_sources = read_sources(base / 'source-observations.jsonl')
    canonical = output / 'canonical-sources.jsonl'
    canonical.write_bytes(seal_sources(original_sources))
    code, report = invoke(base / 'diagnostic-trace.json', canonical, 'canonical-reseal-control')
    assert code == 0 and report['analysisCoverageAccepted'] is False and len(report['provenFacts']) == 21
    def raw_version(trace, records):
        batch = next(row for row in records if row['kind'] == 'source-batch' and row['operation'] == 'update')
        batch['actualPGresult']['fields'][2]['raw']['base64'] = base64.b64encode(b'00000000-0000-4000-8000-000000000099').decode()
    def commit_tag(trace, records):
        row = next(row for row in records if row['kind'] == 'control-query' and row['sql'] == 'COMMIT')
        row['result']['commandTag'] = 'ROLLBACK'
        row['result']['actualPGresult']['commandTag']['base64'] = base64.b64encode(b'ROLLBACK').decode()
    def delivered_row(trace, records):
        batch = next(row for row in records if row['kind'] == 'source-batch' and row['operation'] == 'get' and row['observation']['rows'])
        batch['observation']['rows'][0][1] = 'forged@example.invalid'
        rows = next(row for row in trace['events'] if row['seq'] == batch['businessRowsEvent'])
        rows['rows'][0][1] = 'forged@example.invalid'
    def ledger_image(trace, records):
        final = next(row for row in records if row['kind'] == 'final-effect-ledger')
        effect = next(row for row in final['ledger'] if row['newImage'] is not None)
        effect['newImage']['email'] = 'forged@example.invalid'
    def commit_request(trace, records):
        next(row for row in trace['events'] if row['kind'] == 'commit_ok')['kind'] = 'commit_request'
    def writer_scope(trace, records): trace['scope']['exclusiveWriters'] = False
    for name, mutate in (('raw-version', raw_version), ('native-control-commit-tag', commit_tag),
            ('actual-delivered-row', delivered_row), ('surviving-ledger-image', ledger_image),
            ('commit-request-is-not-ack', commit_request), ('unproven-writer-scope', writer_scope)):
        trace, sources = deepcopy(original_trace), deepcopy(original_sources)
        mutate(trace, sources)
        trace_path, sources_path = output / (name + '-trace.json'), output / (name + '-sources.jsonl')
        trace_path.write_text(json.dumps(trace, ensure_ascii=False, separators=(',', ':')), encoding='utf8')
        sources_path.write_bytes(seal_sources(sources))
        read_sources(sources_path)  # The integrity frame is valid before semantic verification.
        code, result = invoke(trace_path, sources_path, name)
        assert code == 2, name
    assert runtime == {path.name: binding(path) for path in (ROOT / 'dist').iterdir() if path.is_file()}
    return {'group': 'current-core-and-resealed-semantic-tampering', 'passed': True,
        'originalReportsRecomputed': 2, 'canonicalResealControl': 1, 'semanticTamperRejections': 6,
        'buildManifest': build, 'runtimeBindings': runtime, 'calls': calls,
        'databaseExecutedByAudit': False, 'analysisCoverageAccepted': False}

def audit_public_closure(evidence, manifest, args, run):
    groups = []
    assert manifest['privateFilesExcluded'] is True and manifest['originalsModified'] is False
    assert binding(evidence / 'author-evidence-review.json') == manifest['authorEvidenceReview']
    author = load(evidence / 'author-evidence-review.json')
    assert author['reviewerIsCandidateAndHarnessAuthor'] is True and author['independentOfImplementation'] is False
    originals_compared = 0
    for entry in manifest['copiedFiles']:
        assert entry['byteIdentical'] is True and 'private' not in Path(entry['originalPath']).parts
        if args.original_run is not None:
            original = (ROOT / entry['originalPath']).resolve()
            assert original.is_relative_to(ROOT)
            assert binding(original) == binding(evidence / entry['path']), entry['path']
            originals_compared += 1
    if args.original_run is not None:
        assert args.original_run.resolve() == (ROOT / manifest['originalExecution']).resolve()
    groups.append({'group': 'public-copy-origin-and-role-boundary', 'passed': True,
        'originalFilesCompared': originals_compared, 'privateDirectoryRead': False})
    execution = load(evidence / 'execution/execution-receipt.json')
    for key in ('passed', 'actualDatabaseExecution', 'clusterStarted', 'ownedDatabaseStopped', 'sourceBindingsUnchanged'):
        assert execution[key] is True
    assert execution['exitCode'] == 0 and execution['completeCapture'] is False and execution['coreProofAccepted'] is False
    assert execution['sourceBindingsBefore'] == execution['sourceBindingsAfter']
    assert binding(evidence / 'execution/database/comparison-receipt.json') == {
        key: execution['databaseReceipt'][key] for key in ('sha256', 'bytes')}
    reproduction = evidence / 'reproduction/repository'
    candidate = reproduction / 'artifacts/v013-orm-candidate'
    harness = candidate / 'database-harness'
    paths = {'candidate-manifest.json': candidate / 'candidate-manifest.json',
        'execution-inputs.json': harness / 'execution-inputs.json'}
    candidate_manifest = load(paths['candidate-manifest.json'])
    assert binding(paths['candidate-manifest.json'])['sha256'] == EXPECTED_CANDIDATE
    for entry in candidate_manifest['files']:
        paths['candidate/' + entry['path']] = candidate / entry['path']
    for entry in load(paths['execution-inputs.json'])['files']:
        paths['harness/' + entry['path']] = harness / entry['path']
    assert set(paths) == set(execution['sourceBindingsBefore'])
    for name, path in paths.items(): assert binding(path) == execution['sourceBindingsBefore'][name], name
    for name, expected in load(candidate / 'source-inputs.json')['files'].items():
        assert binding(reproduction / name) == expected, name
    for name, expected in load(harness / 'original-source-bindings.json')['files'].items():
        assert binding(reproduction / name) == expected, name
    mainline = ROOT / 'integrations/python/moontxnwitness_capture'
    for name in MODULES:
        expected = binding(candidate / 'payload/integrations/python/moontxnwitness_capture' / name)
        assert binding(mainline / name) == expected, name
    groups.append({'group': 'actual-input-and-installed-mainline-bindings', 'passed': True,
        'executionInputFiles': len(paths), 'mainlineNewModules': {name: binding(mainline / name) for name in MODULES}})
    comparison = load(evidence / 'execution/database/comparison-receipt.json')
    assert comparison['passed'] is True and comparison['actualDatabaseExecution'] is True
    assert comparison['sourceBindingsBefore'] == comparison['sourceBindingsAfter'] == execution['sourceBindingsBefore']
    assert comparison['runtime'] == {'python': '3.12.5', 'sqlalchemy': '2.0.55', 'psycopg': '3.3.6'}
    def nodes(path):
        return {node.name: ast.dump(node, include_attributes=False) for node in ast.parse(path.read_text(encoding='utf8')).body
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))}
    original_tree = ast.parse((harness / 'frozen_run_postgres.py').read_text(encoding='utf8'))
    for node in original_tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in comparison['extractedOriginalWorkloadAstSha256']:
            assert hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest() == comparison['extractedOriginalWorkloadAstSha256'][node.name]
    assert set(comparison['extractedOriginalWorkloadAstSha256']) == {'RecordingCursor', 'models', 'work', 'surface'}
    assert (harness / 'frozen_run_postgres.py').read_bytes() == (reproduction / 'artifacts/orm-v3-draft/slice3/run_postgres.py').read_bytes()
    for name in ('install.py', 'control_log.py', 'relation_contract.py'):
        assert nodes(harness / 'support' / name) == nodes(reproduction / 'artifacts/orm-v3-draft/slice3' / name), name
    upstream = comparison['upstream']
    assert upstream['commit'] == '6397ace506d829a2ee12786da5d724c3f4c6b634' and upstream['license'] == 'MIT'
    upstream_root = reproduction / 'artifacts/orm-v3-draft'
    archive = upstream_root / 'upstream-6397ace.zip'
    assert binding(archive)['sha256'] == upstream['archiveSha256'] == '5cb6a7059b99ccb565970b75e76e7d291f4db4843337be8dde63eb20e7a40458'
    import zipfile
    source_files = {}
    with zipfile.ZipFile(archive) as package:
        for entry in package.infolist():
            if entry.is_dir(): continue
            parts = Path(entry.filename).parts
            assert parts[0] == 'fastapi-users-db-sqlalchemy-' + upstream['commit'] and '..' not in parts
            relative = Path(*parts[1:])
            data = package.read(entry)
            assert (upstream_root / 'upstream' / parts[0] / relative).read_bytes() == data
            source_files[relative.as_posix()] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
    assert source_files == upstream['sourceBindings'] and len(source_files) == 22
    for name, expected in comparison['actualCollectorFiles'].items():
        assert binding(mainline / name) == expected
    groups.append({'group': 'preserved-business-assertions-and-real-upstream', 'passed': True,
        'workloadDefinitions': 4, 'upstreamArchiveFiles': len(source_files), 'setupAstBodiesUnchanged': True})
    mode_results = []
    database = evidence / 'execution/database'
    for mode in comparison['modes']:
        assert binding(database / mode['receipt']) == {key: mode[key] for key in ('sha256', 'bytes')}
        result = audit_mode(database / mode['name'])
        actual = result.pop('receipt')
        assert actual['cache'] == mode['cache']
        expected_work = {name: True for name in ('getCreateUpdateDelete', 'commitRefreshNewTransaction',
            'nestedRollback', 'sameValueUpdate', 'deleteReinsert', 'preexistingRow', 'poolDisposeReconnect', 'UUIDReturn')}
        assert actual['plain'] == actual['observed'] == expected_work
        assert actual['plainDetails'] == actual['observedDetails'] == {
            'duplicateEmail': {'sqlstate': '23505', 'identity': True},
            'nullHash': {'sqlstate': '23502', 'column': 'hashed_password', 'identity': True}}
        assert actual['plainSurface'] == actual['observedSurface']
        surface = actual['observedSurface']
        assert len(surface) == 4 and surface[0]['fetchError']['identity'] is True
        assert surface[0]['fetchError']['class'] == surface[1]['fetchClass'] == 'ProgrammingError'
        assert surface[1]['identity'] is True and surface[1]['rowcount'] == 0
        assert [row['present'] for row in surface[2:]] == [True, False]
        assert [row['tag'] for row in surface[2:]] == ['SELECT 1', 'SELECT 0']
        assert actual['poolCounts']['connect'] >= 2 and actual['poolCounts']['checkout'] > actual['poolCounts']['connect']
        result.update(group=mode['name'] + '-raw-source-lifecycle-business-and-acks', passed=True)
        groups.append(result)
        mode_results.append(actual)
    fields = ('plain', 'observed', 'plainDetails', 'observedDetails', 'plainSurface',
        'observedSurface', 'semanticLedger', 'semanticState', 'ledgerCount')
    assert set(comparison['modeComparisons']) == set(fields)
    for field in fields:
        assert comparison['modeComparisons'][field] is True and mode_results[0][field] == mode_results[1][field]
    disabled, enabled = [row['cache'] for row in mode_results]
    assert disabled['enabled'] is False and disabled['retained'] == {'entries': 0, 'bytes': 0} and disabled['compilations'] == 59
    assert enabled['enabled'] is True and enabled['compilations'] == 35 and enabled['hits'] == 24
    assert enabled['retained']['entries'] == 35 and enabled['retained']['bytes'] <= 1048576
    groups.append({'group': 'independently-recomputed-cache-mode-parity', 'passed': True,
        'comparedBusinessFields': list(fields), 'disabledCompilations': 59, 'enabledCompilations': 35,
        'timingOrRssImprovementClaimed': False})
    if args.run_core: groups.append(audit_core(database, run))
    return {'checks': [{'group': 'public-file-manifest', 'passed': True,
        'files': len(manifest['copiedFiles']), 'sha256': args.manifest_sha256}] + groups,
        'actualDatabaseRunConfirmedFromEvidence': True, 'execution': binding(evidence / 'execution/execution-receipt.json'),
        'coreExecutedByReview': args.run_core, 'scope': 'Fixed-profile actual SQLAlchemy business parity and component-local source proof; no complete ORM history'}

if __name__ == '__main__': raise SystemExit(main())
