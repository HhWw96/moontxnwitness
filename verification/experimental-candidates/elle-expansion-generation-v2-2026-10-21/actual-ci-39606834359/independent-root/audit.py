"""Independent raw-input domain/shape audit. No generator or checker imports."""
from pathlib import Path
from collections import Counter
import json
import hashlib
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
AUTHOR = ROOT / 'artifacts/elle-expansion-generation-run-39606834359-author-support'
DATA = AUTHOR / 'extracted/generated-input-freeze/inputs.jsonl'
EXPECTED = '4b7ef85eb4a2f4a74020d6e6c65f5345f7c4c3b576afbe02b3f7a0cfc6033507'
SEED = 'MoonTxnWitness-Elle-common-raw-20261021-v1'
FAMILIES = {
    'point-register-v1': ('suffix-points', 'repeat-points', 'prefix-and-suffix', 'multi-key-owners', 'alternating-sources'),
    'append-list-v1': ('source-subsets', 'reversed-observations', 'repeated-observed-identity', 'prefix-and-suffix', 'mixed-list-orders'),
}
checks, failures = [], []


def require(condition, label):
    if not condition:
        raise ValueError(label)


def canon(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def load(path, limit=1048576):
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, 'bounded input')
    return json.loads(raw)


def identity(value):
    require(type(value) is str and 1 <= len(value.encode('utf-16-le')) // 2 <= 256, 'identity width')
    require(all(ord(c) >= 32 and ord(c) != 127 and not 0xd800 <= ord(c) <= 0xdfff for c in value), 'identity scalar/control')
    return value


def check_tree(value):
    todo, nodes = [(value, 0)], 0
    while todo:
        item, depth = todo.pop()
        nodes += 1
        require(nodes <= 65536 and depth <= 32, 'tree nodes/depth')
        if type(item) is dict:
            todo.extend((v, depth + 1) for v in item.values())
        elif type(item) is list:
            todo.extend((v, depth + 1) for v in item)


def inspect(trace):
    require(set(trace) == {'traceSchema', 'dataModel', 'clockDomain', 'scope', 'events', 'gaps'}, 'original facts only')
    require(type(trace['traceSchema']) is int and trace['traceSchema'] == 3, 'schema')
    model = trace['dataModel']
    require(model in FAMILIES and trace['scope'] == {'exclusiveWriters': True} and trace['gaps'] == [], 'model/scope')
    identity(trace['clockDomain'])
    events = trace['events']
    require(type(events) is list and 1 < len(events) <= 512, 'event bound')
    first = events[0]
    require(set(first) == {'seq', 'time', 'kind', 'initial', 'consistent'} and first['kind'] == 'snapshot' and first['consistent'] is True, 'actual snapshot')
    initial = first['initial']
    require(type(initial) is dict and 2 <= len(initial) <= 4, 'key scope')
    key_numbers = {identity(k): n for n, k in enumerate(initial)}
    source, payload_ids = {}, {}
    if model == 'point-register-v1':
        for key, value in initial.items():
            identity(value)
            require(value not in source, 'unique initial version')
            source[value] = (key, ['initial', key_numbers[key]], None)
    else:
        require(all(type(v) is list and v == [] for v in initial.values()), 'empty initial lists')
    tx, connections, programs, writes = {}, set(), [], set()
    operations = appends = duplicates = repeated_payload = 0
    previous_time, data_started, last_phase = -1, False, 'begin'
    for seq, event in enumerate(events, 1):
        require(type(event) is dict and type(event.get('seq')) is int and event['seq'] == seq, 'event seq')
        require(type(event.get('time')) is int and previous_time <= event['time'] <= 9007199254740991, 'event time')
        previous_time = event['time']
        if seq == 1:
            continue
        kind = event['kind']
        name = identity(event.get('tx'))
        if kind == 'begin':
            require(not data_started and set(event) == {'seq', 'time', 'kind', 'tx', 'connection'}, 'all begins precede data')
            connection = identity(event['connection'])
            require(name not in tx and connection not in connections, 'unique tx/connection')
            tx[name] = {'index': len(programs), 'phase': 'active'}
            programs.append([])
            connections.add(connection)
            continue
        require(name in tx, 'known transaction')
        transaction = tx[name]
        if kind in ('commit_request', 'commit_ok'):
            require(set(event) == {'seq', 'time', 'kind', 'tx'}, 'exact outcome fields')
            require(transaction['phase'] == ('active' if kind == 'commit_request' else 'committing'), 'confirmed lifecycle')
            transaction['phase'] = 'committing' if kind == 'commit_request' else 'committed'
            last_phase = 'outcomes'
            continue
        require(last_phase != 'outcomes' and transaction['phase'] == 'active', 'data before outcome')
        data_started = True
        operations += 1
        require(operations <= 128, 'operation bound')
        key = identity(event['key'])
        require(key in key_numbers, 'known key')
        program = programs[transaction['index']]
        if model == 'point-register-v1':
            require(kind in ('write', 'read'), 'register operations only')
            expected_fields = {'seq', 'time', 'kind', 'tx', 'key', 'version'}
            require(set(event) == (expected_fields | {'predecessor'} if kind == 'write' else expected_fields), 'exact register fields')
            version = identity(event['version'])
            if kind == 'write':
                require(key not in writes and version not in source and event['predecessor'] == initial[key], 'one authentic writer per key')
                pointer = ['write', transaction['index'], len(program)]
                program.append(['write', key_numbers[key], pointer, source[identity(event['predecessor'])][1]])
                source[version] = (key, pointer, None)
                writes.add(key)
            else:
                require(version in source and source[version][0] == key, 'read source already observed on same key')
                program.append(['read', key_numbers[key], source[version][1]])
        else:
            require(kind in ('append', 'list_read'), 'list operations only')
            if kind == 'append':
                require(set(event) == {'seq', 'time', 'kind', 'tx', 'key', 'id', 'value'}, 'append fields')
                producer = identity(event['id'])
                value = event['value']
                require(producer not in source and type(value) is str, 'unique append identity')
                repeated_payload += int(value in payload_ids)
                payload_ids.setdefault(value, len(payload_ids))
                pointer = ['append', transaction['index'], len(program)]
                program.append(['append', key_numbers[key], pointer, payload_ids[value]])
                source[producer] = (key, pointer, value)
                appends += 1
            else:
                require(set(event) == {'seq', 'time', 'kind', 'tx', 'key', 'items'} and type(event['items']) is list and len(event['items']) <= 128, 'list read fields/bound')
                refs, seen = [], set()
                for item in event['items']:
                    require(type(item) is dict and set(item) == {'id', 'value'}, 'observed list item fields')
                    producer = identity(item['id'])
                    require(type(item['value']) is str and producer in source and source[producer][0] == key and source[producer][2] == item['value'], 'observed item authentic source and payload')
                    duplicates += int(producer in seen)
                    seen.add(producer)
                    refs.append([source[producer][1], payload_ids[item['value']]])
                program.append(['list_read', key_numbers[key], refs])
    require(2 <= len(tx) <= 6 and all(t['phase'] == 'committed' for t in tx.values()), 'all bounded transactions acknowledged')
    require(writes == set(initial) if model == 'point-register-v1' else 2 <= appends <= 8, 'complete writer scope')
    shape = {'model': model, 'keyCount': len(initial), 'programs': programs}
    # A stricter additional diagnostic canonicalizes payload classes in final
    # program traversal order, without changing or replacing the frozen input.
    normalized = json.loads(canon(shape))
    classes = {}
    for program in normalized['programs']:
        for op in program:
            if op[0] == 'append':
                op[3] = classes.setdefault(op[3], len(classes))
            elif op[0] == 'list_read':
                for item in op[2]:
                    item[1] = classes.setdefault(item[1], len(classes))
    return shape, normalized, {'transactions': len(tx), 'keys': len(initial), 'ops': operations, 'appends': appends, 'duplicateObservedIds': duplicates, 'repeatedPayloadAppends': repeated_payload}


def main():
    run = load(HERE / 'run.json')
    require(run['id'] == 39606834359 and run['conclusion'] == 'success' and run['head_sha'] == '61d0785c100f5cc38646b09151ba616a3bda8f40' and run['event'] == 'workflow_dispatch', 'fresh live run identity')
    jobs = load(HERE / 'jobs.json')
    require(len(jobs['jobs']) == 1 and jobs['jobs'][0]['conclusion'] == 'success', 'fresh live job')
    artifacts = load(HERE / 'artifacts.json')['artifacts']
    require(len(artifacts) == 1 and artifacts[0]['size_in_bytes'] == 502565 and artifacts[0]['digest'] == 'sha256:895f6788225e957a6841bd087c2bbd9ea85fba04be407c15c441f66391070782', 'fresh live artifact')
    raw_zip = (AUTHOR / 'downloads-r2/artifact.zip').read_bytes()
    require(digest(raw_zip) == artifacts[0]['digest'][7:], 'full original zip digest')
    with zipfile.ZipFile(AUTHOR / 'downloads-r2/artifact.zip') as zipped:
        names = []
        for info in zipped.infolist():
            if info.is_dir():
                continue
            require(info.file_size <= 33554432 and not info.filename.startswith('/') and '..' not in Path(info.filename).parts, 'safe zip member')
            local = AUTHOR / 'extracted' / info.filename
            with local.open('rb') as stream:
                raw = stream.read(info.file_size + 1)
            require(raw == zipped.read(info), 'actual zip member original bytes')
            names.append(info.filename)
    original = load(AUTHOR / 'extracted/generation-ci-receipt.json')
    require(original['passed'] is True and original['generatorInvocations'] == 1 and original['actualElleExecuted'] is False and original['actualMoonBitExecuted'] is False and original['evaluatorMayRun'] is False, 'generation-only execution')
    for name, row in original['sourceInputs'].items():
        raw = (AUTHOR / 'extracted/frozen-input-sources' / name).read_bytes()
        require(len(raw) == row['bytes'] and digest(raw) == row['sha256'], 'frozen source binding')
        require(raw == (ROOT / 'verification/experimental-candidates/elle-expansion-generation-v2-2026-10-21' / name).read_bytes(), 'public source original bytes')
    require(len(original['sourceInputs']) == 11, 'eleven original prerequisite bindings')
    accepted = load(AUTHOR / 'extracted/frozen-input-sources/smoke/independent-smoke-receipt-r2.json')
    require(accepted['passed'] is True and accepted['checksCount'] == 95 and all(c['passed'] for c in accepted['checks']) and accepted['booleanAgreementCases'] == 6 and accepted['unknownCoverageDifferences'] == 2, 'prior independent smoke scope unchanged')
    exact, shapes, stricter, ids, count, models, families, metrics = set(), set(), set(), set(), 0, Counter(), Counter(), Counter()
    whole = hashlib.sha256()
    with DATA.open('rb') as stream:
        while True:
            line = stream.readline(1048577)
            if not line:
                break
            require(len(line) <= 1048576 and line.endswith(b'\n'), 'record bound and terminator')
            whole.update(line)
            row = json.loads(line)
            check_tree(row)
            require(line == canon(row) + b'\n' and set(row) == {'schema', 'id', 'family', 'candidate', 'inputSha256', 'programShapeSha256', 'input'} and type(row['schema']) is int and row['schema'] == 1, 'canonical raw record, no generated truth')
            require(row['id'] not in ids and type(row['candidate']) is int and 0 <= row['candidate'] < 20000, 'unique ID and bounded ordinal')
            model = row['input']['dataModel']
            require(model in FAMILIES and row['family'] in FAMILIES[model], 'preregistered family')
            raw = canon(row['input'])
            require(digest(raw) == row['inputSha256'] and raw not in exact, 'raw canonical hash and exact uniqueness')
            shape, strict_shape, coverage = inspect(row['input'])
            shape_bytes = canon(shape)
            require(digest(shape_bytes) == row['programShapeSha256'] and shape_bytes not in shapes, 'independent normalized shape hash and uniqueness')
            exact.add(raw)
            shapes.add(shape_bytes)
            stricter.add(canon(strict_shape))
            ids.add(row['id'])
            models[model] += 1
            families[(model, row['family'])] += 1
            metrics.update(coverage)
            checks.append({'id': row['id'], 'inputSha256': digest(raw), 'programShapeSha256': digest(shape_bytes), 'passed': True, **coverage})
            count += 1
    require(DATA.stat().st_size == 5940749 and whole.hexdigest() == EXPECTED, 'whole original dataset')
    require(count == 2000 and models == Counter({m: 1000 for m in FAMILIES}) and families == Counter({(m, f): 200 for m, fs in FAMILIES.items() for f in fs}), 'all models and family quotas accounted')
    result = {'schema': 1, 'kind': 'independent-AI-frozen-raw-input-domain-and-program-shape-review', 'passed': True, 'reviewer': '/root', 'reviewerAuthoredGenerator': False, 'humanAcceptance': False, 'organizerAcceptance': False, 'actualCheckerExecuted': False, 'localGeneratorExecuted': False, 'datasetSha256': EXPECTED, 'datasetBytes': DATA.stat().st_size, 'records': count, 'exactUnique': len(exact), 'firstOccurrenceProgramShapeUnique': len(shapes), 'additionalFinalProgramPayloadClassShapeUnique': len(stricter), 'fullGraphIsomorphismProved': False, 'families': [{'model': m, 'family': f, 'count': n} for (m, f), n in families.items()], 'coverage': dict(metrics), 'reusedAuthorZipWithFreshIndependentLiveApiAndFullByteAudit': True, 'zipMemberCount': len(names), 'originalFailuresAndInputsUnchanged': True, 'evaluationHasNotRun': True, 'nextGate': 'separately reviewed streaming batch evaluator; this is not result acceptance'}
    (HERE / 'per-input-checks.json').write_bytes(json.dumps(checks, indent=2).encode() + b'\n')
    result['auditorSha256'] = digest(Path(__file__).read_bytes())
    (HERE / 'receipt.json').write_bytes(json.dumps(result, indent=2).encode() + b'\n')
    print(json.dumps({k: result[k] for k in ['passed', 'records', 'exactUnique', 'firstOccurrenceProgramShapeUnique', 'additionalFinalProgramPayloadClassShapeUnique']}))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        (HERE / 'first-failure.json').write_bytes(json.dumps({'passed': False, 'error': type(error).__name__, 'reason': str(error), 'checksCompleted': len(checks), 'actualCheckerExecuted': False}, indent=2).encode() + b'\n')
        raise
