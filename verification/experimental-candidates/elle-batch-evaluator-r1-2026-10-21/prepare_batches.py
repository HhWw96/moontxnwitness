"""Prepare fixed raw inputs for bounded upstream batches, without either checker."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json

DATA_SHA = '4b7ef85eb4a2f4a74020d6e6c65f5345f7c4c3b576afbe02b3f7a0cfc6033507'
AUDIT_SHA = '0ba43192283deb2cb9ac4934ee31928a93ac46813daf0b460ff2e2a370eb5d40'


def file_hash(path, maximum):
    digest, size = hashlib.sha256(), 0
    with path.open('rb') as stream:
        while block := stream.read(65536):
            size += len(block)
            if size > maximum:
                raise ValueError('Bounded original input required')
            digest.update(block)
    return size, digest.hexdigest()


def read_json(path, maximum):
    with path.open('rb') as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError('JSON bound exceeded')
    return raw, json.loads(raw)


def prepare(root, output):
    freeze = root / 'verification/experimental-candidates/elle-expansion-generation-v2-2026-10-21/actual-ci-39606834359'
    data = freeze / 'inputs.jsonl'
    audit_raw, audit = read_json(freeze / 'independent-root/receipt.json', 1048576)
    if hashlib.sha256(audit_raw).hexdigest() != AUDIT_SHA or not (
        audit['passed'] is True and audit['records'] == 2000 and audit['exactUnique'] == 2000
        and audit['firstOccurrenceProgramShapeUnique'] == 2000
        and audit['actualCheckerExecuted'] is False and audit['datasetSha256'] == DATA_SHA
    ):
        raise ValueError('Exact independent frozen-input prerequisite required')
    if file_hash(data, 33554432) != (5940749, DATA_SHA):
        raise ValueError('Original dataset bytes differ')
    adapter_root = root / 'verification/experimental-candidates/elle-smoke-r2-2026-10-21'
    index_raw, index = read_json(adapter_root / 'candidate-index-static-v2.json', 1048576)
    if hashlib.sha256(index_raw).hexdigest() != '79181c62e4499b14a420810758d68c31df70d93bd3f950692f71c9b1ca0acf80':
        raise ValueError('Frozen raw-fact adapter index differs')
    adapter_path = adapter_root / 'prepare.py'
    expected = index['files']['prepare.py']
    if file_hash(adapter_path, 1048576) != (expected['bytes'], expected['sha256']):
        raise ValueError('Frozen adapter changed')
    spec = importlib.util.spec_from_file_location('fixed_raw_fact_adapter', adapter_path)
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    output.mkdir(parents=True, exist_ok=False)
    receipt = {'schema': 1, 'passed': False, 'datasetSha256': DATA_SHA,
               'independentInputReceiptSha256': AUDIT_SHA, 'adapterSourceSha256': expected['sha256'],
               'actualCheckerExecuted': False, 'localGeneratorExecuted': False,
               'batches': [], 'counts': {'eligible': 0, 'outside': 0, 'invalid': 0}, 'errors': []}
    writer, batch, count, seen = None, None, 0, set()
    try:
        with data.open('rb') as source, (output / 'dispositions.jsonl').open('xb') as dispositions:
            while True:
                raw = source.readline(1048577)
                if not raw:
                    break
                if len(raw) > 1048576 or not raw.endswith(b'\n'):
                    raise ValueError('Raw record exceeds framing budget')
                adapter.wire_budget(raw)
                row = json.loads(raw, object_pairs_hook=adapter.unique)
                if row['id'] in seen:
                    raise ValueError('Duplicate original case ID')
                seen.add(row['id'])
                original = json.dumps(row['input'], sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode()
                if hashlib.sha256(original).hexdigest() != row['inputSha256']:
                    raise ValueError('Original per-case digest changed')
                try:
                    converted, status, reason = adapter.adapt(row['input']), 'eligible', None
                except adapter.Outside as error:
                    converted, status, reason = None, 'outside', str(error)
                except (adapter.Invalid, KeyError, TypeError, UnicodeError) as error:
                    converted, status, reason = None, 'invalid', str(error)
                receipt['counts'][status] += 1
                disposition = {'id': row['id'], 'inputSha256': row['inputSha256'], 'disposition': status,
                               'reason': reason, 'originalOrdinal': count, 'batch': None}
                if converted is not None:
                    if batch is None or batch['cases'] == 50:
                        if writer:
                            writer.close()
                        name = 'batch-' + str(len(receipt['batches'])).zfill(3) + '.edn'
                        writer = (output / name).open('x', encoding='utf8', newline='\n')
                        batch = {'file': name, 'cases': 0, 'ids': []}
                        receipt['batches'].append(batch)
                    # No expected validity, inferred version order or synthetic
                    # initialization transaction is passed to either checker.
                    request = {'id': row['id'], 'inputSha256': row['inputSha256'], **converted}
                    writer.write(adapter.edn(request) + '\n')
                    writer.flush()
                    batch['cases'] += 1
                    batch['ids'].append(row['id'])
                    disposition['batch'] = batch['file']
                dispositions.write(json.dumps(disposition, sort_keys=True).encode() + b'\n')
                dispositions.flush()
                count += 1
        receipt['passed'] = count == 2000 and receipt['counts'] == {'eligible': 2000, 'outside': 0, 'invalid': 0}
    except Exception as error:
        receipt['errors'].append({'class': type(error).__name__, 'message': str(error)})
    finally:
        if writer:
            writer.close()
        receipt['originalInputsAccounted'] = count
        for batch in receipt['batches']:
            size, sha = file_hash(output / batch['file'], 8388608)
            batch.update(bytes=size, sha256=sha)
        if file_hash(data, 33554432) != (5940749, DATA_SHA):
            receipt['passed'] = False
            receipt['errors'].append({'message': 'Original input changed during preparation'})
        with (output / 'preparation-receipt.json').open('x', encoding='utf8') as stream:
            json.dump(receipt, stream, indent=2)
            stream.write('\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.root.resolve(), args.output.resolve())
    print(json.dumps({k: result[k] for k in ['passed', 'counts', 'originalInputsAccounted']}))
    raise SystemExit(0 if result['passed'] else 1)
