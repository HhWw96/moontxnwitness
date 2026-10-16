"""Run the controlled PostgreSQL suite in a new owned cluster; preserve its files."""
import argparse
import importlib.util
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bin', required=True, help='PostgreSQL 18 bin directory; full installation tree is needed')
    parser.add_argument('--work-root', default=str(ROOT / 'artifacts/local-postgres'))
    args = parser.parse_args()
    if importlib.util.find_spec('psycopg') is None:
        print('PostgreSQL verification not executed: install the optional fixture driver first.')
        return 3
    binaries = Path(args.bin).resolve()
    suffix = '.exe' if os.name == 'nt' else ''
    assert (binaries / ('initdb' + suffix)).is_file()
    parent = Path(args.work_root).resolve()
    parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='moontxnwitness-pg18-', dir=parent)).resolve()
    assert work.is_relative_to(parent)
    if os.name == 'nt' and not str(work).isascii():
        raise RuntimeError('Use an ASCII --work-root on Windows, for example C:/temp')
    env = dict(os.environ, TEMP=str(work), TMP=str(work))
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    if os.name == 'nt':
        # Passing values through environment variables avoids shell-built path text.
        alias = work / 'pgsql'
        env['MTW_PG_ALIAS'] = str(alias)
        env['MTW_PG_TARGET'] = str(binaries.parent)
        subprocess.run(['powershell', '-NoProfile', '-Command', 'New-Item -ItemType Junction -Path $env:MTW_PG_ALIAS -Target $env:MTW_PG_TARGET | Out-Null'], env=env, check=True, creationflags=flags)
        binaries = alias / binaries.name
    password = secrets.token_hex(20)
    (work / 'password.txt').write_text(password + '\n', encoding='ascii')
    data = work / 'data'
    log = (work / 'control.log').open('ab')

    def run(arguments):
        # A daemon must not inherit capture pipes, which would keep their EOF open.
        subprocess.run([str(x) for x in arguments], stdin=subprocess.DEVNULL,
                       stdout=log, stderr=subprocess.STDOUT, env=env,
                       check=True, timeout=120, creationflags=flags)

    started = False
    try:
        run([binaries / ('initdb' + suffix), '-D', data, '-U', 'mtw', '--locale=C', '--encoding=UTF8', '--auth-host=scram-sha-256', '--auth-local=trust', '--pwfile=' + str(work / 'password.txt')])
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        run([binaries / ('pg_ctl' + suffix), '-D', data, '-l', work / 'server.log', '-o', f'-h 127.0.0.1 -p {port}', '-w', 'start'])
        started = True
        connection = {'host': '127.0.0.1', 'port': port, 'dbname': 'postgres', 'user': 'mtw', 'password': password}
        (work / 'connection.json').write_text(json.dumps(connection), encoding='utf-8')
        env['MTW_PYTHON'] = sys.executable
        env['MTW_PG_CONNECTION_FILE'] = str(work / 'connection.json')
        result = subprocess.run(['node', str(ROOT / 'scripts/postgres-e2e.mjs')], cwd=ROOT, env=env, creationflags=flags)
        return result.returncode
    finally:
        if started:
            pid_file = data / 'postmaster.pid'
            if pid_file.exists():
                recorded = Path(pid_file.read_text(encoding='utf-8').splitlines()[1]).resolve()
                assert recorded == data.resolve(), 'Refuse to stop an unrelated cluster'
                run([binaries / ('pg_ctl' + suffix), '-D', data, '-m', 'fast', '-w', 'stop'])
        log.close()
        print('The project-only cluster is stopped; its temporary files are preserved for inspection.')


if __name__ == '__main__':
    raise SystemExit(main())
