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
    parser.add_argument('--work-root', type=Path, default=ROOT / 'artifacts/capture-postgres',
                        help='Parent for new owned cluster files; existing runs are never reused or removed')
    parser.add_argument('--suite', choices=['capture', 'legacy', 'all', 'provenance', 'provenance-cost', 'provenance-profile', 'capture-with-profile', 'dislock', 'capture-with-dislock', 'presence', 'presence-database', 'capture-with-presence', 'all-with-presence', 'v3-lifecycle', 'v3-list', 'v3-relation', 'v3-dislock', 'v3-commit', 'v3-business-all', 'mlflow-fault'], default='capture')
    args = parser.parse_args()
    parent = args.work_root.resolve()
    parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='run-', dir=parent)).resolve()
    assert work.is_relative_to(parent)
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
        suites = (['v3-dislock','v3-commit'] if args.suite == 'v3-business-all' else
                  ['legacy','capture','provenance-profile','dislock','presence'] if args.suite == 'all-with-presence' else
                  ['legacy','capture'] if args.suite == 'all' else
                  ['capture','provenance-profile','dislock','presence'] if args.suite == 'capture-with-presence' else
                  ['capture','provenance-profile','dislock'] if args.suite == 'capture-with-dislock' else
                  ['capture','provenance-profile'] if args.suite == 'capture-with-profile' else [args.suite])
        for suite in suites:
            if suite == 'v3-relation':
                output = ROOT / 'verification/relation-v3' / ('postgres-' + uuid.uuid4().hex)
                result = subprocess.run([sys.executable, '-B', str(ROOT / 'experiments/relation_v3/run_postgres.py'),
                    '--output', str(output)], cwd=ROOT, env=env, creationflags=flags)
                if result.returncode:
                    return result.returncode
                replay = subprocess.run(['node', str(ROOT / 'experiments/relation_v3/e2e.mjs'), str(output),
                    str(output.parent / (output.name + '-model'))], cwd=ROOT, env=env, creationflags=flags)
                if replay.returncode:
                    return replay.returncode
                continue
            if suite == 'mlflow-fault':
                output = ROOT / 'verification/faults/mlflow' / ('run-' + uuid.uuid4().hex)
                result = subprocess.run([sys.executable, '-B', str(ROOT / 'experiments/faults/mlflow/run_postgres.py'),
                    '--output', str(output)], cwd=ROOT, env=env, creationflags=flags)
                if result.returncode:
                    return result.returncode
                continue
            if suite == 'v3-commit':
                output = ROOT / 'verification/business/dislock' / ('v3-commit-' + uuid.uuid4().hex)
                result = subprocess.run([sys.executable, '-B', str(ROOT / 'experiments/business/dislock/v3_commit_postgres.py'),
                    '--output', str(output)], cwd=ROOT, env=env, creationflags=flags)
                if result.returncode:
                    return result.returncode
                replay = subprocess.run(['node', str(ROOT / 'experiments/business/dislock/v3_commit_e2e.mjs'), str(output)],
                    cwd=ROOT, env=env, creationflags=flags)
                if replay.returncode:
                    return replay.returncode
                continue
            if suite == 'v3-dislock':
                output = ROOT / 'verification/business/dislock' / ('v3-' + uuid.uuid4().hex)
                result = subprocess.run([sys.executable, '-B', str(ROOT / 'experiments/business/dislock/v3_postgres.py'),
                    '--output', str(output)], cwd=ROOT, env=env, creationflags=flags)
                if result.returncode:
                    return result.returncode
                replay = subprocess.run(['node', str(ROOT / 'experiments/business/dislock/v3_e2e.mjs'), str(output)],
                    cwd=ROOT, env=env, creationflags=flags)
                if replay.returncode:
                    return replay.returncode
                continue
            if suite == 'v3-list':
                output = ROOT / 'verification/list-v3' / ('postgres-' + uuid.uuid4().hex)
                result = subprocess.run([sys.executable, '-B', str(ROOT / 'experiments/list_v3/postgres.py'),
                    '--output', str(output)], cwd=ROOT, env=env, creationflags=flags)
                if result.returncode:
                    return result.returncode
                replay = subprocess.run(['node', str(ROOT / 'experiments/list_v3/e2e.mjs'), str(output)],
                    cwd=ROOT, env=env, creationflags=flags)
                if replay.returncode:
                    return replay.returncode
                continue
            if suite == 'v3-lifecycle':
                output = ROOT / 'verification/v3' / ('postgres-' + uuid.uuid4().hex)
                result = subprocess.run([sys.executable, '-B', str(ROOT / 'experiments/lifecycle_v3/postgres.py'),
                    '--output', str(output)], cwd=ROOT, env=env, creationflags=flags)
                if result.returncode:
                    return result.returncode
                replay = subprocess.run(['node', str(ROOT / 'experiments/lifecycle_v3/e2e.mjs'), str(output)],
                    cwd=ROOT, env=env, creationflags=flags)
                if replay.returncode:
                    return replay.returncode
                continue
            if suite in ('presence', 'presence-database'):
                output = ROOT / 'verification/provenance-presence' / ('run-' + uuid.uuid4().hex)
                command = (['node', str(ROOT / 'experiments/provenance/presence_e2e.mjs')]
                    if suite == 'presence' else [sys.executable, '-B', str(ROOT / 'experiments/provenance/presence_postgres.py')])
                result = subprocess.run(command + [
                    '--schema', 'mtw_provenance_presence_' + uuid.uuid4().hex[:12], '--output', str(output)],
                    cwd=ROOT, env=env, creationflags=flags)
                if result.returncode:
                    return result.returncode
                extra = output / 'initialization'
                guard = subprocess.run([sys.executable, '-B', str(ROOT / 'experiments/provenance/initialization_postgres.py'),
                    '--schema', 'mtw_provenance_ack_' + uuid.uuid4().hex[:12], '--output', str(extra)],
                    cwd=ROOT, env=env, creationflags=flags)
                if guard.returncode:
                    return guard.returncode
                continue
            if suite == 'dislock':
                output = ROOT / 'verification/business/dislock' / ('run-' + uuid.uuid4().hex)
                result = subprocess.run(['node', str(ROOT / 'experiments/business/dislock/e2e.mjs'),
                    '--schema', 'mtw_provenance_dislock_' + uuid.uuid4().hex[:12], '--output', str(output)],
                    cwd=ROOT, env=env, creationflags=flags)
                if result.returncode:
                    return result.returncode
                continue
            if suite == 'provenance-profile':
                output = ROOT / 'verification/provenance-profile' / ('run-' + uuid.uuid4().hex)
                result = subprocess.run(['node', str(ROOT / 'experiments/provenance/capture_profile_e2e.mjs'),
                    '--schema', 'mtw_provenance_profile_' + uuid.uuid4().hex[:12], '--output', str(output)],
                    cwd=ROOT, env=env, creationflags=flags)
                if result.returncode:
                    return result.returncode
                continue
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
        print('Owned database stopped; cluster and logs retained in the selected work root as ' + work.name)


if __name__ == '__main__':
    raise SystemExit(main())
