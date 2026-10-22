"""CI-only staging. Copies current run evidence, never edits originals.

Intended for a clean checkout on a GitHub hosted runner; unchanged historical
evidence remains available at HEAD.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def git(*args, cwd=None):
    return subprocess.check_output(['git', *args], cwd=ROOT if cwd is None else cwd).decode('utf8')


def stage(root=ROOT):
    root = Path(root).resolve()
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('CI evidence staging requires a clean GitHub Actions checkout; local release uses its existing flow')
    version = json.loads((root / 'package.json').read_text(encoding='utf8'))['version']
    destination = root / 'artifacts/ci-evidence'
    # Fail instead of mixing evidence from an older attempt into this run.
    destination.mkdir(parents=True, exist_ok=False)
    public = set(filter(None, git('ls-files', '--cached', '--others', '--exclude-standard', '-z', cwd=root).split('\0')))
    changed = set(filter(None, git('diff', '--name-only', '-z', 'HEAD', '--', 'verification/', cwd=root).split('\0')))
    changed.update(filter(None, git('ls-files', '--others', '--exclude-standard', '-z', '--', 'verification/', cwd=root).split('\0')))
    selected = {n for n in changed & public if (root / n).is_file()}
    # Small current summary receipts may be byte-identical to the committed copy.
    selected.update(p.relative_to(root).as_posix() for p in (root / 'verification').glob('*')
                    if p.is_file() and p.relative_to(root).as_posix() in public)
    for folder in ('dist', 'cmd', 'integrations/python/moontxnwitness_capture'):
        for p in (root / folder).rglob('*'):
            name = p.relative_to(root).as_posix()
            if (p.is_file() and '__pycache__' not in p.parts and not p.is_symlink()
                    and (folder == 'dist' or name in public)):
                selected.add(name)
    name = 'MoonTxnWitness-v' + version
    for filename in (name + '-source.zip', name + '-portable.zip', name + '-SHA256SUMS.txt', name + '-release.json', 'release-index.json'):
        if (root / 'artifacts' / filename).is_file():
            selected.add('artifacts/' + filename)
    rows = []
    for name in sorted(selected):
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise AssertionError('Unsafe CI evidence item: ' + name)
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        digest = hashlib.sha256()
        with target.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        rows.append({'file': name, 'bytes': target.stat().st_size, 'sha256': digest.hexdigest()})
    (destination / 'current-run-index.json').write_text(json.dumps({
        'schema': 1, 'version': version, 'sourceCommit': git('rev-parse', 'HEAD', cwd=root).strip(),
        'runId': os.environ.get('GITHUB_RUN_ID'), 'runAttempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
        'selection': 'New/modified public verification outputs against clean HEAD, current receipts, actual runtimes and exact current-version archives',
        'unchangedHistoricalEvidence': 'Retained in Git at sourceCommit; not deleted or reclassified',
        'files': rows}, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'staged': len(rows), 'bytes': sum(r['bytes'] for r in rows)}))


if __name__ == '__main__':
    stage()
