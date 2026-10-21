"""Explicit repository-Actions fetch -> tokenless fixed ORM runtime audit."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import base64
import hashlib
import json
import os
from transport import (guard_environment, child_environment, Transport, immutable,
                       safe_extract, file_binding, file_sha, read_bounded, run_bounded)

HERE = Path(__file__).resolve().parent
PROFILE_SHA = 'c3ad9858cfb46c39bae50d47b5a57a3138c7bd9467d429faa04514a4c4287746'
CONTRACT_SHA = '2e30dcccb17920312a50f88048ffcd4049a99fb9e2818d6d6d9c92feb4017051'


def load(path):
    return json.loads(read_bounded(path))


def profile():
    assert file_sha(HERE / 'profile.json') == PROFILE_SHA
    assert file_sha(HERE / 'contract-v1.json') == CONTRACT_SHA
    return load(HERE / 'profile.json')


def fetch(work, p):
    guard_environment(need_token=True)
    work.mkdir(parents=True, exist_ok=False)
    client = Transport(os.environ['GITHUB_TOKEN'], work)
    route = '/repos/HhWw96/moontxnwitness/'
    record = {'schema': 1, 'complete': False, 'sourceCommit': p['sourceCommit'],
              'run': p['run'], 'downloads': [], 'tokenPersisted': False, 'signedUrlPersisted': False}
    try:
        run, _ = client.json(route + 'actions/runs/' + str(p['run']), 'run.json')
        assert run['head_sha'] == p['sourceCommit'] and run['status'] == 'completed' and run['conclusion'] == 'success'
        assert run['path'] == '.github/workflows/experimental-orm-source.yml'
        job, _ = client.json(route + 'actions/jobs/' + str(p['job']), 'job.json')
        assert job['run_id'] == p['run'] and job['conclusion'] == 'success'
        artifacts, _ = client.json(route + 'actions/runs/' + str(p['run']) + '/artifacts?per_page=100', 'artifacts.json')
        assert len(artifacts['artifacts']) == artifacts['total_count'] == 1
        artifact = artifacts['artifacts'][0]
        assert artifact['id'] == p['artifactId'] and artifact['name'] == p['artifactName'] and not artifact['expired']
        assert artifact['digest'] == 'sha256:' + p['artifactSha256'] and artifact['size_in_bytes'] == p['artifactBytes']
        assert artifact['workflow_run']['head_sha'] == p['sourceCommit']
        record['downloads'].append(client.download(route + 'actions/artifacts/' + str(p['artifactId']) + '/zip',
                                                  'actual-module-artifact.zip', 4 * 1024 * 1024,
                                                  artifact['digest'], artifact['size_in_bytes']))
        safe_extract(work / 'actual-module-artifact.zip', work / 'artifact')
        assert file_binding(work / 'artifact/experimental-capture-core.mjs') == {
            'bytes': p['moduleBytes'], 'sha256': p['moduleSha256']}
        names = {'candidate-manifest-static-v1.json': {'sha256': p['candidateManifestSha256']}, **p['inputs']}
        for index, (name, expected) in enumerate(names.items()):
            value, _ = client.json(route + 'contents/' + p['publicCandidatePrefix'] + name
                                   + '?ref=' + p['sourceCommit'], 'public-input-' + str(index) + '.json')
            assert value['encoding'] == 'base64'
            raw = base64.b64decode(value['content'], validate=False)
            assert len(raw) == value['size'] and hashlib.sha256(raw).hexdigest() == expected['sha256']
            assert hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == value['sha']
            if 'bytes' in expected:
                assert len(raw) == expected['bytes']
            immutable(work / 'inputs' / name, raw)
        record['requests'] = client.requests
        record['complete'] = True
        immutable(work / 'fetch-complete.json', record)
    except Exception as error:
        record['errorClass'] = type(error).__name__
        record['laterRuntimeChecks'] = 'not-executed'
        record['requests'] = client.requests
        immutable(work / 'fetch-failed.json', record)
        raise


def audit(work, p):
    assert not os.environ.get('GITHUB_TOKEN'), 'Runtime step must not receive GITHUB_TOKEN'
    result = {'schema': 1, 'kind': 'independent-orm-r3-downloaded-runtime-audit', 'passed': False,
              'complete': False, 'executionComplete': False, 'sourceCommit': p['sourceCommit'],
              'originalRun': p['run'], 'independentRun': os.environ.get('GITHUB_RUN_ID'),
              'auditScriptSha256': file_sha(__file__), 'profileSha256': PROFILE_SHA,
              'contractSha256': CONTRACT_SHA, 'driverSha256': file_sha(HERE / 'runtime.mjs'),
              'authorHarnessImported': False, 'compilation': False, 'databaseExecution': False,
              'formalPerformance': False, 'productionModelCoverageAccepted': False,
              'fullApplicationAccepted': False, 'stableReleaseAccepted': False, 'humanAcceptance': False,
              'stages': {'downloadPreflight': 'not-executed', 'independentRuntime': 'not-executed'}}
    try:
        assert load(work / 'fetch-complete.json')['complete']
        assert file_binding(work / 'actual-module-artifact.zip') == {'bytes': p['artifactBytes'], 'sha256': p['artifactSha256']}
        assert file_binding(work / 'artifact/experimental-capture-core.mjs') == {'bytes': p['moduleBytes'], 'sha256': p['moduleSha256']}
        execution = load(work / 'artifact/execution-receipt.json')
        authored = load(work / 'artifact/source2-functional-first.json')
        assert execution['passed'] and execution['workflowCommit'] == p['sourceCommit']
        assert execution['baselineSourceSha256'] == p['baselineSourceSha256']
        assert execution['experimentalSourceSha256'] == p['experimentalSourceSha256']
        assert execution['candidateIndexSha256'] == p['candidateManifestSha256']
        assert execution['actualRuntimeBinding'] == {'bytes': p['moduleBytes'], 'sha256': p['moduleSha256']}
        assert all(s['status'] == 'passed' and s['exitCode'] == 0 for s in execution['stages'])
        tests = [s for s in execution['stages'] if s['name'].startswith('test-')]
        assert len(tests) == 4 and all(s['actualCoreTestsPassed'] == 616 for s in tests)
        assert authored['passed'] and len(authored['checks']) == 74 and all(c['passed'] for c in authored['checks'])
        assert authored['module']['sha256'] == p['moduleSha256']
        for name, expected in p['inputs'].items():
            assert file_binding(work / 'inputs' / name) == expected
            assert authored['originalBindings'][Path(name).name] == expected['sha256']
        result['stages']['downloadPreflight'] = 'passed'
        for name in ('profile.json', 'contract-v1.json', 'runtime.mjs'):
            immutable(work / name, read_bounded(HERE / name))
        result['stages']['independentRuntime'] = 'running'
        process = run_bounded(['node', str(work / 'runtime.mjs'), str(work), str(work / 'result')],
                              cwd=work, env=child_environment(), output_prefix=work / 'runtime-process', timeout=240)
        immutable(work / 'runtime-process.json', {'exitCode': process.returncode, 'stdout': process.stdout, 'stderr': process.stderr})
        runtime = load(work / 'result/independent-result.json')
        result['runtime'] = runtime
        result['executionComplete'] = runtime['complete']
        assert process.returncode == 0 and runtime['passed'] and runtime['complete'] and runtime['checks'] == 24
        assert runtime['actualModuleSha256'] == p['moduleSha256'] and not runtime['authorHarnessImported']
        assert runtime['node'] == 'v24.13.0' and runtime['platform'] == 'linux'
        result['stages']['independentRuntime'] = 'passed'
        result['complete'] = result['passed'] = True
    except Exception as error:
        name = 'independentRuntime' if result['stages']['downloadPreflight'] == 'passed' else 'downloadPreflight'
        result['stages'][name] = 'failed'
        result['errorClass'] = type(error).__name__
        result['error'] = str(error).replace(str(work), '<fresh>').replace(str(HERE), '<audit-tool>')
    result['finishedAt'] = datetime.now(timezone.utc).isoformat()
    immutable(work / 'independent-audit.json', result)
    print(json.dumps({'passed': result['passed'], 'complete': result['complete'], 'executionComplete': result['executionComplete'],
                      'checks': result.get('runtime', {}).get('checks', 0), 'stages': result['stages'],
                      'receiptSha256': file_sha(work / 'independent-audit.json')}), flush=True)
    return 0 if result['passed'] else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=['fetch', 'audit'], required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    guard_environment(need_token=args.phase == 'fetch')
    p = profile()
    if args.phase == 'fetch':
        fetch(args.work, p)
        print(json.dumps({'passed': True, 'phase': 'fetch', 'runtimeChecks': 'not-executed'}), flush=True)
        return 0
    return audit(args.work, p)


if __name__ == '__main__':
    raise SystemExit(main())
