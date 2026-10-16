"""Publish already-tested packages under the explicitly bound repository owner."""
import json
import os
import subprocess
import sys
import time
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


def publish():
    # The account can be switched by other desktop tasks; never use its implicit selection.
    token = run(['gh', 'auth', 'token', '--hostname', 'github.com', '--user', 'HhWw96'])
    ENV['GH_TOKEN'] = token
    assert run(['gh', 'api', 'user', '--jq', '.login']) == 'HhWw96'
    assert not run(['git', 'status', '--porcelain']), 'Commit the tested release first'
    sha = run(['git', 'rev-parse', 'HEAD'])
    tag = 'v' + VERSION
    assert run(['git', 'rev-list', '-n', '1', tag]) == sha
    run(['git', '-c', 'credential.helper=', '-c', 'credential.helper=!gh auth git-credential', 'push', 'origin', 'main', tag])
    print('Exact release commit and tag pushed: ' + tag, flush=True)
    # Publishing reads the current source, so finish this step before another version is edited.
    assert run(['node', 'scripts/moon.mjs', 'whoami']).endswith('HhWw96')
    run(['node', 'scripts/moon.mjs', 'publish'], capture=False)
    print('Mooncakes upload completed: ' + VERSION, flush=True)
    notes = ROOT / ('artifacts/release-notes-v' + VERSION + '.md')
    notes.write_text('MoonTxnWitness v' + VERSION + '\n\n'
                     'See CHANGELOG.md and verification/releases/' + VERSION + '/ for implementation and evidence.\n'
                     'Core JS/Wasm tests, independent serial replay, actual SQLite and fresh ZIP consumers passed.\n'
                     'Public download/registry verification is recorded after publishing; no organizer acceptance is claimed.\n'
                     'Portable runtime requires Node.js >=20. PostgreSQL capture additionally requires its documented optional driver.\n', encoding='utf-8')
    assets = [str(ROOT / ('artifacts/MoonTxnWitness-v' + VERSION + suffix)) for suffix in ('-source.zip', '-portable.zip', '-SHA256SUMS.txt')]
    run(['gh', 'release', 'create', tag, '--repo', MODULE, '--target', sha, '--title', 'MoonTxnWitness ' + tag, '--notes-file', str(notes), *assets])
    print('Public GitHub Release created: ' + tag, flush=True)
    deadline = time.monotonic() + 1800
    while time.monotonic() < deadline:
        runs = json.loads(run(['gh', 'run', 'list', '--repo', MODULE, '--commit', sha, '--workflow', 'ci.yml', '--json', 'databaseId,status,conclusion', '--limit', '10']))
        if any(r['conclusion'] == 'success' for r in runs):
            break
        if runs and all(r['status'] == 'completed' for r in runs):
            raise RuntimeError('Public CI failed; preserve this release and repair with a new commit')
        time.sleep(15)
    else:
        raise TimeoutError('CI did not finish within the observation window')
    run([sys.executable, 'scripts/verify_publication.py', VERSION], timeout=900, capture=False)
    print('Public download, exact-commit CI and registry-only consumers passed: ' + tag, flush=True)


if __name__ == '__main__':
    publish()
