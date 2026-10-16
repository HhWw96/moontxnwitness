"""Check public working files and, optionally, all reachable historical blobs."""
import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def scan():
    parser = argparse.ArgumentParser()
    parser.add_argument('--history', action='store_true')
    args = parser.parse_args()
    findings = []
    checked = 0
    home = str(Path.home())
    private_paths = {home, home.replace('\\', '/'), home.replace('\\', '\\\\')}
    patterns = [re.compile(rb'gh[pousr]_[A-Za-z0-9]{20,}'), re.compile(rb'-----BEGIN [A-Z ]*PRIVATE' + rb' KEY-----')]

    def check(label, content):
        nonlocal checked
        checked += 1
        if any(value.encode('utf-8') in content for value in private_paths):
            findings.append({'file': label, 'kind': 'private home path'})
        if any(pattern.search(content) for pattern in patterns):
            findings.append({'file': label, 'kind': 'credential material'})

    paths = git('ls-files', '--cached', '--others', '--exclude-standard', '-z').decode('utf-8').split('\0')
    for name in filter(None, paths):
        if name == '.local-toolchain.json' or Path(name).name == 'credentials.json':
            findings.append({'file': name, 'kind': 'private configuration selected'})
        path = ROOT / name
        if path.is_file():
            check(name, path.read_bytes())
    history_blobs = 0
    if args.history:
        objects = git('rev-list', '--objects', '--all').decode('utf-8').splitlines()
        object_names = {line.split(' ', 1)[0]: line.split(' ', 1)[1] if ' ' in line else '' for line in objects}
        proc = subprocess.Popen(['git', 'cat-file', '--batch'], cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        try:
            for oid, name in object_names.items():
                proc.stdin.write((oid + '\n').encode('ascii'))
                proc.stdin.flush()
                header = proc.stdout.readline().decode('ascii').strip().split()
                assert len(header) == 3, 'Unexpected git object response'
                content = proc.stdout.read(int(header[2]))
                assert proc.stdout.read(1) == b'\n'
                if header[1] == 'blob':
                    history_blobs += 1
                    check(oid[:12] + ':' + name, content)
        finally:
            proc.stdin.close()
            proc.stdout.close()
            proc.wait()
    receipt = {'tool': 'MoonTxnWitness', 'passed': not findings, 'checkedFilesAndBlobs': checked, 'historyBlobs': history_blobs, 'findings': findings, 'scope': 'Private home paths, GitHub token syntax, private keys and selected local configuration; not an exhaustive secret detector'}
    (ROOT / 'verification').mkdir(exist_ok=True)
    (ROOT / 'verification/publication-privacy.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(receipt))
    return 0 if receipt['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(scan())
