"""Publish already-tested packages under the explicitly bound repository owner."""
import json
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION = json.loads((ROOT / 'package.json').read_text(encoding='utf-8'))['version']
MODULE = 'HhWw96/moontxnwitness'
ENV = dict(os.environ)


def run(args, timeout=300, capture=True):
    result = subprocess.run(args, cwd=ROOT, env=ENV, capture_output=capture, text=True,
                            encoding='utf-8', errors='replace', timeout=timeout)
    if result.returncode:
        if capture:
            print(result.stdout, result.stderr)
        raise RuntimeError('Release operation failed: ' + args[0])
    return result.stdout.strip() if capture else ''


def wait_for_ci(sha):
    workflows = ['ci.yml'] + (['postgres.yml'] if tuple(map(int, VERSION.split('.'))) >= (0, 0, 11) else [])
    for workflow in workflows:
        deadline = time.monotonic() + 1800
        while time.monotonic() < deadline:
            runs = json.loads(run(['gh', 'run', 'list', '--repo', MODULE, '--commit', sha, '--workflow', workflow, '--json', 'databaseId,status,conclusion', '--limit', '10']))
            if any(r['conclusion'] == 'success' for r in runs):
                print('Exact-commit CI passed: ' + workflow, flush=True)
                break
            if runs and all(r['status'] == 'completed' for r in runs):
                raise RuntimeError('Public CI failed: ' + workflow + '; preserve the failed run and repair')
            time.sleep(15)
        else:
            raise TimeoutError('CI did not finish within the observation window: ' + workflow)


def publish():
    # The account can be switched by other desktop tasks; never use its implicit selection.
    token = run(['gh', 'auth', 'token', '--hostname', 'github.com', '--user', 'HhWw96'])
    ENV['GH_TOKEN'] = token
    assert run(['gh', 'api', 'user', '--jq', '.login']) == 'HhWw96'
    assert not run(['git', 'status', '--porcelain']), 'Commit the tested release first'
    for name in ('summary', 'package'):
        receipt = json.loads((ROOT / ('verification/' + name + '.json')).read_text(encoding='utf-8'))
        assert receipt['passed'] and receipt['version'] == VERSION
    prefix = 'MoonTxnWitness-v' + VERSION + '/'
    with zipfile.ZipFile(ROOT / ('artifacts/MoonTxnWitness-v' + VERSION + '-source.zip')) as source:
        for member in source.infolist():
            assert member.filename.startswith(prefix)
            relative = Path(member.filename[len(prefix):])
            assert (ROOT / relative).resolve().is_relative_to(ROOT.resolve())
            assert source.read(member) == (ROOT / relative).read_bytes(), 'Source archive is stale: ' + relative.as_posix()
    if tuple(map(int, VERSION.split('.'))) >= (0, 1, 0):
        acceptance = json.loads((ROOT / 'verification/releases' / VERSION / 'acceptance.json').read_text(encoding='utf-8'))
        performance = json.loads((ROOT / 'verification/releases' / VERSION / acceptance['performanceReceipt']).read_text(encoding='utf-8'))
        manifest = json.loads((ROOT / 'dist/build-manifest.json').read_text(encoding='utf-8'))
        assert acceptance['passed'] and performance['performanceTargetsMet']
        assert performance['sourceSha256'] == manifest['sourceSha256'] and performance['currentSha256'] == manifest['coreSha256']
        postgres = json.loads((ROOT / 'verification/postgres.json').read_text(encoding='utf-8'))
        assert postgres['version'] == VERSION and postgres['passed'] and postgres['actualDatabaseExecution']
    sha = run(['git', 'rev-parse', 'HEAD'])
    tag = 'v' + VERSION
    assert run(['git', 'rev-list', '-n', '1', tag]) == sha
    run(['git', '-c', 'credential.helper=', '-c', 'credential.helper=!gh auth git-credential', 'push', 'origin', 'main'])
    print('Release candidate pushed; waiting for actual CI before package publication: ' + tag, flush=True)
    wait_for_ci(sha)
    assert run(['git', 'rev-parse', 'HEAD']) == sha and not run(['git', 'status', '--porcelain'])
    # Publishing reads the current source, so finish this step before another version is edited.
    assert run(['node', 'scripts/moon.mjs', 'whoami']).endswith('HhWw96')
    run(['node', 'scripts/moon.mjs', 'publish'], capture=False)
    print('Mooncakes upload completed: ' + VERSION, flush=True)
    run(['git', '-c', 'credential.helper=', '-c', 'credential.helper=!gh auth git-credential', 'push', 'origin', tag])
    notes = ROOT / ('artifacts/release-notes-v' + VERSION + '.md')
    notes.write_text('MoonTxnWitness v' + VERSION + '\n\n'
                     'Balanced analysis/reduction and schema-2 replay are recommended; legacy API defaults remain available.\n\n'
                     'See CHANGELOG.md and verification/releases/' + VERSION + '/ for implementation and evidence.\n'
                     'Core JS/Wasm/Linux Native CI, independent serial replay, actual SQLite and fresh ZIP consumers passed before package publication.\n'
                     'Public download/registry verification is recorded after publishing; no organizer acceptance is claimed.\n'
                     'Portable runtime requires Node.js >=20. PostgreSQL capture additionally requires its documented optional driver.\n', encoding='utf-8')
    performance_path = ROOT / 'verification/releases' / VERSION / 'release-gate-v1.json'
    if performance_path.exists():
        groups = json.loads(performance_path.read_text(encoding='utf-8'))['groups']
        with notes.open('a', encoding='utf-8') as output:
            output.write('\nFull-report local comparison with v0.0.6: graph %.2fx, bounded search %.2fx, reduction %.2fx; graph peak RSS %.2f%% lower (group geometric means).\n' % (groups['graph']['geometricMeanSpeedup'], groups['search']['geometricMeanSpeedup'], groups['reduction']['geometricMeanSpeedup'], (1-groups['graph']['geometricMeanPeakMemoryRatio'])*100))
            output.write('Actual PostgreSQL 18: 20 RR write-skew rounds + 20 Serializable abort/fresh-retry rounds on Windows and independent Linux CI, with 2-transaction reduction and three replay capsules.\n')
            output.write('See docs/performance.md, docs/project-brief.md and docs/human-acceptance.md. Participant explanation/registration and organizer acceptance remain separate.\n')
    assets = [str(ROOT / ('artifacts/MoonTxnWitness-v' + VERSION + suffix)) for suffix in ('-source.zip', '-portable.zip', '-SHA256SUMS.txt')]
    run(['gh', 'release', 'create', tag, '--repo', MODULE, '--target', sha, '--title', 'MoonTxnWitness ' + tag, '--notes-file', str(notes), *assets])
    print('Public GitHub Release created: ' + tag, flush=True)
    run([sys.executable, 'scripts/verify_publication.py', VERSION], timeout=900, capture=False)
    print('Public download, exact-commit CI and registry-only consumers passed: ' + tag, flush=True)


if __name__ == '__main__':
    publish()
