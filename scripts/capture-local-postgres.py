"""Run capture verification against an owned PostgreSQL 18 cluster.

Windows uses a temporary drive alias into this repository so PostgreSQL receives
ASCII paths. The alias and database are owned by this run; data/logs are retained.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bin', default=str(ROOT / 'artifacts/postgres18-tools/pgsql/bin'))
    parser.add_argument('--suite', choices=['capture', 'legacy', 'all', 'provenance', 'provenance-cost'], default='capture')
    args = parser.parse_args()
    parent = (ROOT / 'artifacts/capture-postgres').resolve()
    parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='run-', dir=parent)).resolve()
    assert work.is_relative_to(ROOT.resolve())
    binaries = Path(args.bin).resolve()
    suffix = '.exe' if os.name == 'nt' else ''
    assert (binaries / ('initdb' + suffix)).is_file()
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    drive = None
    running = False
    data = work / 'data'
    log = (work / 'control.log').open('ab')
    env = dict(os.environ, MTW_PYTHON=sys.executable)
    try:
        if os.name == 'nt':
            for letter in 'QRSTUVWXYZ':
                if not Path(letter + ':/').exists():
                    drive = letter + ':'
                    break
            if drive is None:
                raise RuntimeError('No unused drive letter for this owned database run')
            subprocess.run(['subst', drive, str(work)], check=True, creationflags=flags)
            alias = Path(drive + '/')
            assert alias.resolve() == work
            env['MTW_PG_ALIAS'] = str(alias / 'pgsql')
            env['MTW_PG_TARGET'] = str(binaries.parent)
            subprocess.run(['powershell', '-NoProfile', '-Command',
                            'New-Item -ItemType Junction -Path $env:MTW_PG_ALIAS -Target $env:MTW_PG_TARGET | Out-Null'],
                           check=True, env=env, creationflags=flags)
            binaries = alias / 'pgsql/bin'
            data = alias / 'data'
            password_file = alias / 'password.txt'
            server_log = alias / 'server.log'
        else:
            password_file = work / 'password.txt'
            server_log = work / 'server.log'
        password = secrets.token_hex(24)
        password_file.write_text(password + '\n', encoding='ascii')

        def control(arguments):
            subprocess.run([str(x) for x in arguments], stdin=subprocess.DEVNULL,
                           stdout=log, stderr=subprocess.STDOUT, env=env, check=True,
                           timeout=120, creationflags=flags)

        control([binaries / ('initdb' + suffix), '-D', data, '-U', 'mtw', '--locale=C',
                 '--encoding=UTF8', '--auth-host=scram-sha-256', '--auth-local=trust',
                 '--pwfile=' + str(password_file)])
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        control([binaries / ('pg_ctl' + suffix), '-D', data, '-l', server_log,
                 '-o', '-h 127.0.0.1 -p ' + str(port), '-w', 'start'])
        running = True
        connection_file = work / 'connection.json'
        connection_file.write_text(json.dumps({'host':'127.0.0.1', 'port':port,
            'dbname':'postgres', 'user':'mtw', 'password':password}), encoding='utf8')
        env['MTW_PG_CONNECTION_FILE'] = str(connection_file)
        suites = ['legacy','capture'] if args.suite == 'all' else [args.suite]
        for suite in suites:
            if suite in ('provenance', 'provenance-cost'):
                output = ROOT / 'verification/provenance-prototypes' / ('run-' + uuid.uuid4().hex)
                script = 'postgres_test.py' if suite == 'provenance' else 'cost_study.py'
                command = [sys.executable, str(ROOT / 'experiments/provenance' / script),
                    '--schema', 'mtw_provenance_' + uuid.uuid4().hex[:12], '--output', str(output)]
                if suite == 'provenance-cost':
                    command.append('--exclusive-cluster')
                result = subprocess.run(command,
                    cwd=ROOT, env=env, creationflags=flags)
                if result.returncode:
                    return result.returncode
                continue
            script = 'postgres-e2e.mjs' if suite == 'legacy' else 'capture-postgres-e2e.mjs'
            result = subprocess.run(['node', str(ROOT / 'scripts' / script)], cwd=ROOT,
                                    env=env, creationflags=flags)
            if result.returncode:
                return result.returncode
        return 0
    finally:
        if running:
            recorded = Path((data / 'postmaster.pid').read_text(encoding='utf8').splitlines()[1]).resolve()
            assert recorded == (work / 'data').resolve()
            subprocess.run([str(binaries / ('pg_ctl' + suffix)), '-D', str(data), '-m', 'fast', '-w', 'stop'],
                           stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=120, creationflags=flags)
        log.close()
        if drive is not None:
            assert Path(drive + '/').resolve() == work
            subprocess.run(['subst', drive, '/D'], check=True, creationflags=flags)
        print('Owned database stopped; files retained in artifacts/capture-postgres/' + work.name)


if __name__ == '__main__':
    raise SystemExit(main())
