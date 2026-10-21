"""Stream fixed results; no Node, oracle import/execution, database or build.

The witness replay below independently checks the literal abstract-execution
axioms. It neither imports the reference implementation nor uses graph cycles to
validate a positive witness. Existing graph results are read, never rerun.
"""
from pathlib import Path
from datetime import datetime, timezone
import collections
import gzip
import hashlib
import json
import traceback

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'abstract-si-v3-independent-draft'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(65536):
            h.update(block)
    return h.hexdigest()


def demand(condition, message):
    if not condition:
        raise AssertionError(message)


def replay_witness(history, witness, model):
    demand(type(witness) is dict, 'witness object')
    demand(set(witness) == {'kind', 'arbitration', 'visibility'}, 'witness fields')
    demand(witness['kind'] == 'existential-abstract-execution', 'witness kind')
    txs = history['transactions']
    by_id = {tx['id']: tx for tx in txs}
    order = witness['arbitration']
    demand(type(order) is list and len(order) == len(txs), 'CO length')
    demand(len(set(order)) == len(order) and set(order) == set(by_id), 'CO permutation')
    position = {tx: i for i, tx in enumerate(order)}
    finals, producers = {}, {}
    for tx in txs:
        cells = {}
        for i, op in enumerate(tx['ops']):
            if op['type'] == 'write':
                cells[op['key']] = op['version']
                producers[op['key'], op['version']] = tx['id']
        finals[tx['id']] = cells
    for key, versions in history['versionOrders'].items():
        owners = [producers[key, v] for v in versions[1:]]
        demand(all(position[a] < position[b] for a, b in zip(owners, owners[1:])), 'CO factual order')
    visibility = witness['visibility']
    demand(type(visibility) is list and len(visibility) == len(txs), 'visibility length')
    seen = set()
    for entry in visibility:
        demand(type(entry) is dict and set(entry) == {'tx', 'prefixLength', 'initializationVisible'}, 'visibility fields')
        tx_id, cut = entry['tx'], entry['prefixLength']
        demand(tx_id in position and tx_id not in seen, 'visibility tx')
        seen.add(tx_id)
        demand(entry['initializationVisible'] is True, 'initializer visible')
        demand(type(cut) is int and 0 <= cut <= position[tx_id], 'strict CO prefix')
        if model == 'serial':
            demand(cut == position[tx_id], 'serial TOTALVIS')
        own_writes = finals[tx_id]
        for before in order[:position[tx_id]]:
            if set(finals[before]) & set(own_writes):
                demand(position[before] < cut, 'NoConflict earlier writer visible')
        state = dict(history['initial'])
        for visible in order[:cut]:
            state.update(finals[visible])
        for op in by_id[tx_id]['ops']:
            if op['type'] == 'write':
                state[op['key']] = op['version']
            else:
                demand(state[op['key']] == op['version'], 'INT/EXT literal snapshot replay')
    return True


def read_lines(path):
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rb') as stream:
        for line in stream:
            yield json.loads(line)


def main():
    receipt = {
        'schema': 1, 'kind': 'independent-fixed-abstract-si-vs-graph-crosscheck',
        'experimental': True, 'stableClassifier': False, 'elleExecuted': False,
        'fullSixModelsAccepted': False, 'databaseAuthenticityVerified': False,
        'oracleImportedOrExecuted': False, 'nodeExecuted': False,
        'kernelRerun': False, 'localDatabaseExecution': False, 'localBuild': False,
        'complete': False, 'passed': False, 'differences': [], 'cases': [],
        'implementationSha256': digest(Path(__file__)),
    }
    counts = collections.Counter()
    try:
        pins = {
            'contract-v1.json': '7c799e3bc812747eb110c9e5a3cdc7f323af5328b0c6b5e28485111ed3f47193',
            'frozen-boundaries-v1.json': '7458e741068467c8042b529454ca4be5131b4d944ddecc9845557499b8b4a2e7',
            'generated-inputs-v1.jsonl': 'ffa93f0ce528a40aa9b9fb09d5491100c7320e0c857ea1a6e195bbef3429053e',
            'generated-evaluation-v1.jsonl': '05a351aca5908fd268f4935a7cbf04002570889a032bcfa2b7958147553494bd',
            'generated-evaluation-v1-receipt.json': '2093af217990ad9b1d584fc6f3ec12dc61ce47e68c6cb830fcf7b06de7d8c7f6',
            'oracle.py': '8ee8c6f5b25dffc22c417bcc2c4cce1ba23a3a4fb0d5014e5f1eb9580a150a0e',
        }
        for name, expected in pins.items():
            demand(digest(BASE / name) == expected, 'fixed input changed: ' + name)
        demand(digest(HERE / 'conversion-freeze.json') == 'd5cb7904ded675ab829e1f49896a7346c02b2fa17721e1ea9436e35e62915206', 'conversion changed')
        demand(digest(HERE / 'kernel-check-receipt-v1.json') == '6867520c191595a1def7c58cff4f2530003bba291fc2bbffedc8acd209146d18', 'kernel receipt changed')
        demand(digest(HERE / 'kernel-results-v1.jsonl.gz') == '68aabeaf4c1362a97868f4853f2acc2c0872383ff6d5536f154e7f3ee206439f', 'kernel outputs changed')
        boundaries = json.loads((BASE / 'frozen-boundaries-v1.json').read_bytes())['fixtures']
        boundary_by_id = {r['id']: r for r in boundaries}
        original = read_lines(BASE / 'generated-inputs-v1.jsonl')
        evaluated = read_lines(BASE / 'generated-evaluation-v1.jsonl')
        kernel = read_lines(HERE / 'kernel-results-v1.jsonl.gz')
        statuses, unknowns, exclusions = collections.Counter(), collections.Counter(), collections.Counter()
        with (HERE / 'comparison-cases-v1.jsonl.gz').open('xb') as raw:
            with gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as output:
                for item in read_lines(HERE / 'converted-inputs-v1.jsonl.gz'):
                    counts['inputRecords'] += 1
                    conversion = item['conversion']
                    row = {'id': item['id'], 'bundle': item['bundle'], 'inputSha256': item['inputSha256'],
                           'conversionReason': conversion['reason'], 'models': {}}
                    k = next(kernel) if conversion['eligible'] else None
                    if k is not None:
                        demand((k['id'], k['inputSha256']) == (item['id'], item['inputSha256']), 'kernel input alignment')
                        counts['kernelRecordsRead'] += 1
                    if item['bundle'] == 'boundary':
                        b = boundary_by_id[item['id']]
                        demand(b['inputSha256'] == item['inputSha256'], 'boundary input alignment')
                        for model, field in [('si', 'expectedSi'), ('serial', 'expectedSerial')]:
                            manual = b[field]
                            row['models'][model] = {'manualExpected': manual, 'oracleFullReportAvailable': False}
                            if k is not None:
                                demand(k['mapped'][model] == manual, 'boundary graph/manual difference: ' + item['id'] + '/' + model)
                                counts['boundaryCommonGraphManualComparisons'] += 1
                            elif conversion['directObligations']:
                                demand(manual == 'unsatisfiable', 'boundary direct/manual difference')
                                counts['boundaryDirectManualComparisons'] += 1
                            else:
                                exclusions['boundary:' + conversion['reason'] + ':' + manual] += 1
                        counts['boundaryManualCases'] += 1
                    else:
                        source, e = next(original), next(evaluated)
                        demand((source['id'], source['inputSha256']) == (item['id'], item['inputSha256']), 'original input alignment')
                        demand((e['id'], e['inputSha256']) == (item['id'], item['inputSha256']), 'evaluated input alignment')
                        history = json.loads(item['inputText'])
                        for model in ['si', 'serial']:
                            report = e['results'][model]['report']
                            status = report['status']
                            counts['generatedModelReports'] += 1
                            statuses[model + ':' + status] += 1
                            evidence = {'status': status, 'decisionBasis': report['execution']['decisionBasis'],
                                        'budgetExhausted': report['execution']['budgetExhausted'],
                                        'coverageComplete': report['coverage']['complete'],
                                        'witnessIndependentlyReplayed': False}
                            row['models'][model] = evidence
                            try:
                                demand(report['inputSha256'] == item['inputSha256'], 'report input hash')
                                demand(report['modelDefinition'] == ('cerone-no-session-si-register-v1' if model == 'si' else 'cerone-no-session-serial-register-v1'), 'report model definition')
                                demand(status in ('satisfiable', 'unsatisfiable', 'inconclusive', 'invalid'), 'report status')
                                execution = report['execution']
                                for field, maximum in [('states', 'maxStates'), ('semanticChecks', 'maxSemanticChecks')]:
                                    demand(type(execution[field]) is int and 0 <= execution[field] <= execution[maximum], 'effective budget bounds')
                                if status == 'satisfiable':
                                    replay_witness(history, report['witness'], model)
                                    counts['positiveWitnessesIndependentlyReplayed'] += 1
                                    evidence['witnessIndependentlyReplayed'] = True
                                else:
                                    demand(report['witness'] is None, 'nonpositive witness must be null')
                                if status == 'inconclusive':
                                    reason = 'budget' if execution['budgetExhausted'] else 'coverage-or-domain'
                                    unknowns[model + ':' + reason + ':' + conversion['reason']] += 1
                                    counts['unknownReportsRetained'] += 1
                                    demand(not execution['searchedAllCandidates'], 'unknown claimed complete exhaustion')
                                elif conversion['eligible']:
                                    demand(k['mapped'][model] == status, 'common graph/oracle status difference')
                                    truth = conversion['truth']['gsiRejected' if model == 'si' else 'serialRejected']
                                    demand((status == 'unsatisfiable') == truth, 'macro-truth/oracle status difference')
                                    counts['commonDefinitiveModelComparisons'] += 1
                                elif conversion['directObligations']:
                                    demand(status == 'unsatisfiable', 'direct semantic obligation accepted')
                                    counts['directRefutationsSeparatelyCompared'] += 1
                                else:
                                    exclusions['generated:' + conversion['reason'] + ':' + status] += 1
                                    demand(status in ('inconclusive', 'invalid'), 'out-of-domain complete verdict')
                            except MemoryError:
                                raise
                            except Exception as error:
                                receipt['differences'].append({'id': item['id'], 'model': model, 'inputSha256': item['inputSha256'],
                                                               'errorClass': type(error).__name__, 'error': str(error),
                                                               'oracleStatus': status, 'conversionReason': conversion['reason']})
                    output.write((json.dumps(row, ensure_ascii=True, separators=(',', ':')) + '\n').encode())
        for name, iterator in [('original', original), ('evaluated', evaluated), ('kernel', kernel)]:
            demand(next(iterator, None) is None, name + ' uncounted trailing records')
        demand(counts['inputRecords'] == 1052 and counts['generatedModelReports'] == 2000 and counts['kernelRecordsRead'] == 683, 'all-input accounting')
        receipt.update(complete=True, passed=not receipt['differences'], statusCounts=dict(statuses),
                       unknownReasons=dict(unknowns), excludedReasons=dict(exclusions),
                       inputBindings=pins, boundaryOracleFullReportsRead=0,
                       boundaryScope='52 frozen hand expectations only; original full per-case oracle reports were not retained. No such reports were fabricated or rerun.',
                       caseArtifact={'file': 'comparison-cases-v1.jsonl.gz', 'sha256': digest(HERE / 'comparison-cases-v1.jsonl.gz')})
        receipt['limitations'] = ['Only the explicitly complete committed unique-version point-register common range is compared.',
            'INT/self-future/external-intermediate refutations remain separate semantic obligations, not graph cycle labels.',
            'Unknown budgets/coverage and all unsupported inputs are counted without being converted to absence.',
            'No Elle execution, stable six-model classifier, database authentication or collected version-order proof is claimed.',
            'No constructionWitness metadata or author witnessVerified boolean is used to accept a reported model witness.']
    except MemoryError:
        receipt.update(errorClass='MemoryError', error='Resource failure retained; stopped without retry', complete=False, passed=False)
    except Exception as error:
        receipt.update(errorClass=type(error).__name__, error=str(error), traceback=traceback.format_exc(), complete=False, passed=False)
    receipt['counts'] = dict(counts)
    receipt['finishedAt'] = datetime.now(timezone.utc).isoformat()
    path = HERE / 'comparison-receipt-v1.json'
    raw = (json.dumps(receipt, indent=2) + '\n').encode()
    path.open('xb').write(raw)
    print(json.dumps({'passed': receipt['passed'], 'complete': receipt['complete'], 'counts': receipt['counts'],
                      'differences': len(receipt['differences']), 'receipt': str(path),
                      'sha256': hashlib.sha256(raw).hexdigest(), 'error': receipt.get('error')}))
    return 0 if receipt['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
