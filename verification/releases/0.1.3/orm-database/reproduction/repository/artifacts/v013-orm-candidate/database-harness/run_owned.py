"""Own one fresh loopback PG18 cluster; preserve private files and all failures."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import uuid
from common import HERE, binding, inputs

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bin', required=True, type=Path)
    parser.add_argument('--work-root', default=HERE / 'executions', type=Path)
    args = parser.parse_args()
    parent, allowed = args.work_root.resolve(), (HERE / 'executions').resolve()
    if not parent.is_relative_to(allowed):
        raise ValueError('All execution output must remain in this isolated harness executions directory')
    binaries = args.bin.resolve()
    suffix = '.exe' if os.name == 'nt' else ''
    if not all((binaries / (name + suffix)).is_file() for name in ('initdb','pg_ctl')):
        raise ValueError('Use the existing PostgreSQL tools; this controller downloads nothing')
    before = inputs()
    parent.mkdir(parents=True, exist_ok=True)
    run = parent / ('run-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    run.mkdir(exist_ok=False)
    private = run / 'private'; private.mkdir()
    receipt = {'schema': 1, 'kind': 'isolated-v013-orm-owned-pg18', 'passed': False,
        'actualDatabaseExecution': False, 'clusterStarted': False, 'ownedDatabaseStopped': False,
        'releaseAcceptance': False, 'formalPerformanceMeasured': False, 'buildExecuted': False,
        'installationOfDependenciesExecuted': False, 'completeCapture': False, 'coreProofAccepted': False,
        'sourceBindingsBefore': before, 'privateDirectoryExcludedFromPublicEvidence': True}
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    env = {key: value for key, value in os.environ.items() if not any(part in key.upper() for part in ('TOKEN','SECRET','AUTHORIZATION','PRIVATE_KEY'))}
    env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1', MTW_V013_RUN_ROOT=str(run))
    env.pop('MTW_PG_DSN', None); env.pop('MTW_PG_CONNECTION_FILE', None)
    drive, running = None, False
    data = private / 'data'
    with (run / 'control.log').open('xb') as control_log:
        def control(arguments):
            return subprocess.run([str(value) for value in arguments], stdin=subprocess.DEVNULL,
                stdout=control_log, stderr=subprocess.STDOUT, env=env, timeout=120,
                check=True, creationflags=flags)
        try:
            alias = private
            if os.name == 'nt':
                for letter in 'QRSTUVWXYZ':
                    if not Path(letter + ':/').exists(): drive = letter + ':'; break
                if drive is None: raise RuntimeError('No unused drive letter for the owned cluster')
                control(['subst', drive, private])
                alias = Path(drive + '/')
                if alias.resolve() != private.resolve(): raise ValueError('Owned drive alias resolved elsewhere')
                env['MTW_PG_ALIAS'], env['MTW_PG_TARGET'] = str(alias / 'pgsql'), str(binaries.parent)
                control(['powershell', '-NoProfile', '-Command',
                    'New-Item -ItemType Junction -Path $env:MTW_PG_ALIAS -Target $env:MTW_PG_TARGET | Out-Null'])
                binaries = alias / 'pgsql/bin'
            data = alias / 'data'
            password_file, server_log = alias / 'password.txt', alias / 'server.log'
            password = secrets.token_hex(24)
            with password_file.open('x', encoding='ascii') as stream: stream.write(password + '\n')
            control([binaries / ('initdb' + suffix), '-D', data, '-U', 'mtw', '--locale=C',
                '--encoding=UTF8', '--auth-host=scram-sha-256', '--auth-local=trust', '--pwfile=' + str(password_file)])
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
            control([binaries / ('pg_ctl' + suffix), '-D', data, '-l', server_log,
                '-o', '-h 127.0.0.1 -p ' + str(port), '-w', 'start'])
            running = True; receipt['clusterStarted'] = True
            connection_file = private / 'connection.json'
            with connection_file.open('x', encoding='utf8') as stream:
                json.dump({'host':'127.0.0.1','port':port,'dbname':'postgres','user':'mtw','password':password}, stream)
            env['MTW_PG_CONNECTION_FILE'] = str(connection_file)
            with (run / 'first.log').open('xb') as log:
                process = subprocess.run([sys.executable, '-B', str(HERE / 'run_database.py'), '--output', str(run / 'database')],
                    cwd=HERE, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                    timeout=900, creationflags=flags)
            receipt['exitCode'] = process.returncode
            result_path = run / 'database/comparison-receipt.json'
            if result_path.is_file():
                actual = json.loads(result_path.read_text(encoding='utf8'))
                receipt['databaseReceipt'] = {'path':'database/comparison-receipt.json', **binding(result_path)}
                receipt['actualDatabaseExecution'] = actual.get('actualDatabaseExecution') is True
                if process.returncode != 0 or actual.get('passed') is not True:
                    raise ValueError('First actual ORM comparison failed; no expectations or output were replaced')
            else:
                raise ValueError('Actual comparison did not produce its receipt; first log retained')
            receipt['passed'] = True
        except BaseException as error:
            receipt['failure'] = {'class':type(error).__name__,
                'message':str(error) if isinstance(error, ValueError) else None}
        finally:
            if running:
                try:
                    if data.resolve() != (private / 'data').resolve():
                        raise ValueError('Refuse stopping a cluster outside this run')
                    control([binaries / ('pg_ctl' + suffix), '-D', data, '-m', 'immediate', '-w', 'stop'])
                    receipt['ownedDatabaseStopped'] = True
                except BaseException as error:
                    receipt['stopFailureClass'] = type(error).__name__; receipt['passed'] = False
            if drive is not None:
                try: control(['subst', drive, '/D'])
                except BaseException as error:
                    receipt['aliasCleanupFailureClass'] = type(error).__name__; receipt['passed'] = False
            try:
                receipt['sourceBindingsAfter'] = inputs()
                receipt['sourceBindingsUnchanged'] = before == receipt['sourceBindingsAfter']
                if not receipt['sourceBindingsUnchanged']: receipt['passed'] = False
            except BaseException as error:
                receipt['sourceVerificationFailureClass'] = type(error).__name__; receipt['passed'] = False
            if not receipt['ownedDatabaseStopped']: receipt['passed'] = False
            with (run / 'execution-receipt.json').open('x', encoding='utf8') as stream:
                json.dump(receipt, stream, indent=2); stream.write('\n')
    print(json.dumps({'passed':receipt['passed'],'actualDatabaseExecution':receipt['actualDatabaseExecution'],
        'ownedDatabaseStopped':receipt['ownedDatabaseStopped'],
        'receipt':(run / 'execution-receipt.json').relative_to(HERE).as_posix()}))
    return 0 if receipt['passed'] else 1

if __name__ == '__main__': raise SystemExit(main())
