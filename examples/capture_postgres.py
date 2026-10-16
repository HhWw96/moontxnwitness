"""Capture controlled point-read/write PostgreSQL isolation scenarios, not production tables."""
import argparse
import json
import os
import platform
import sys
import threading
import time
import uuid
from pathlib import Path


def capture(parameters, rounds, trace_path):
    import psycopg
    from psycopg import sql
    origin = time.monotonic_ns()
    clock = lambda: (time.monotonic_ns() - origin) // 1000
    namespace = 'mtw_' + uuid.uuid4().hex
    trace = []
    lock = threading.Lock()

    def connect():
        conn = psycopg.connect(**parameters, autocommit=True, connect_timeout=5)
        conn.execute('SET statement_timeout = 5000')
        conn.execute('SET lock_timeout = 5000')
        return conn

    def event(tx, action, **details):
        with lock:
            row = {'transaction': tx, 'action': action, 'observedAtUs': clock(), **details}
            trace.append(row)
            # Persist observations as they arrive so failures retain partial evidence.
            with trace_path.open('a', encoding='utf-8') as output:
                output.write(json.dumps(row) + '\n')

    with connect() as setup:
        server_version = setup.execute('SELECT version()').fetchone()[0]
        assert 180000 <= setup.info.server_version < 190000, 'This fixture requires PostgreSQL 18'
        setup.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(namespace)))
        table = sql.Identifier(namespace, 'registers')
        setup.execute(sql.SQL('CREATE TABLE {} (key text PRIMARY KEY, value integer NOT NULL, version text NOT NULL)').format(table))
        histories = {}
        cases = []
        try:
            for isolation in ('REPEATABLE READ', 'SERIALIZABLE'):
                initial = {}
                transactions = []
                outcomes = []
                prefix = 'rr' if isolation == 'REPEATABLE READ' else 'serial'
                for round_id in range(rounds):
                    keys = [f'{prefix}/{round_id}/x', f'{prefix}/{round_id}/y']
                    for key in keys:
                        version = key + ':initial'
                        initial[key] = version
                        setup.execute(sql.SQL('INSERT INTO {} (key,value,version) VALUES (%s,1,%s)').format(table), (key, version))
                    barrier = threading.Barrier(2, timeout=10)
                    results = []
                    errors = []

                    def transaction(tx_id, own_key, rendezvous=None):
                        ops = []
                        start = clock()
                        state = None
                        backend = None
                        with connect() as conn:
                            backend = conn.info.backend_pid
                            try:
                                conn.execute('BEGIN ISOLATION LEVEL ' + isolation)
                                event(tx_id, 'begin', isolation=isolation, backendPid=backend, sql='BEGIN ISOLATION LEVEL ' + isolation)
                                values = []
                                for key in keys:
                                    value, version = conn.execute(sql.SQL('SELECT value,version FROM {} WHERE key=%s').format(table), (key,)).fetchone()
                                    values.append(value)
                                    ops.append({'type': 'read', 'key': key, 'version': version})
                                    event(tx_id, 'point-read', key=key, value=value, version=version, sql='SELECT value,version FROM <fixture>.registers WHERE key=%s')
                                if rendezvous:
                                    rendezvous.wait()
                                if sum(values) > 1:
                                    version = tx_id + ':write'
                                    updated = conn.execute(sql.SQL('UPDATE {} SET value=0,version=%s WHERE key=%s').format(table), (version, own_key))
                                    assert updated.rowcount == 1
                                    ops.append({'type': 'write', 'key': own_key, 'version': version})
                                    event(tx_id, 'point-write', key=own_key, value=0, version=version, affectedRows=updated.rowcount, sql='UPDATE <fixture>.registers SET value=0,version=%s WHERE key=%s')
                                conn.execute('COMMIT')
                                status = 'committed'
                                event(tx_id, 'commit-ack', sql='COMMIT')
                            except psycopg.Error as error:
                                state = error.sqlstate
                                if state != '40001':
                                    event(tx_id, 'unexpected-error', sqlstate=state)
                                    raise
                                conn.execute('ROLLBACK')
                                status = 'aborted'
                                event(tx_id, 'server-abort', sqlstate=state, rollbackAcknowledged=True, sql='ROLLBACK')
                        return {'id': tx_id, 'status': status, 'ops': ops, 'start': start, 'end': clock()}, state, backend

                    def worker(index):
                        try:
                            result = transaction(f'{prefix}:{round_id}:{index}', keys[index], barrier)
                            with lock:
                                results.append((index, *result))
                        except Exception as error:
                            with lock:
                                errors.append(type(error).__name__)
                            barrier.abort()

                    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
                    for thread in threads:
                        thread.start()
                    for thread in threads:
                        thread.join(timeout=20)
                    assert not any(thread.is_alive() for thread in threads), 'Worker exceeded its bounded execution window'
                    assert not errors and len(results) == 2, 'Actual database capture failed: ' + ','.join(errors)
                    assert len({row[3] for row in results}) == 2, 'Workers must use distinct backend connections'
                    transactions.extend(row[1] for row in results)
                    aborted = [row for row in results if row[1]['status'] == 'aborted']
                    if isolation == 'REPEATABLE READ':
                        assert not aborted, 'Both distinct-row writes should commit in the controlled RR schedule'
                    else:
                        assert len(aborted) == 1 and aborted[0][2] == '40001'
                        index, original, _, _ = aborted[0]
                        retry = None
                        for retry_id in range(1, 4):
                            retry, state, _ = transaction(original['id'] + ':retry' + str(retry_id), keys[index])
                            transactions.append(retry)
                            if retry['status'] == 'committed':
                                break
                        assert retry and retry['status'] == 'committed', 'Fresh retry did not commit'
                    final = [setup.execute(sql.SQL('SELECT value FROM {} WHERE key=%s').format(table), (key,)).fetchone()[0] for key in keys]
                    assert sum(final) == (0 if isolation == 'REPEATABLE READ' else 1)
                    outcomes.append({'round': round_id, 'initialConcurrentCommits': 2 - len(aborted), 'initialConcurrentAborts': len(aborted), 'sqlstates': [row[2] for row in aborted], 'finalOnCallCount': sum(final)})
                transactions.sort(key=lambda tx: (tx['start'], tx['id']))
                histories[prefix] = {'schemaVersion': 1, 'name': 'Actual PostgreSQL ' + isolation + ' controlled point-register capture', 'model': 'strict-serializable', 'initial': initial, 'transactions': transactions}
                cases.append({'isolation': isolation, 'rounds': rounds, 'workers': 2, 'results': outcomes, 'committed': sum(t['status'] == 'committed' for t in transactions), 'aborted': sum(t['status'] == 'aborted' for t in transactions)})
        finally:
            # Only the unique schema created by this invocation is removed.
            setup.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(namespace)))
    metadata = {'passed': True, 'actualDatabaseExecution': True, 'server': server_version, 'driver': psycopg.__version__, 'python': platform.python_version(), 'cases': cases, 'clock': 'one Python process monotonic_ns origin, integer microseconds', 'versionOrderSource': 'at most one committed writer per fixture key; no total commit order inferred', 'claim': 'Controlled RR serialization anomaly and Serializable abort/retry; not a PostgreSQL vulnerability or database-wide certification'}
    return histories, metadata, trace


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--rounds', type=int, default=20)
    parser.add_argument('--connection-file')
    args = parser.parse_args()
    if not 1 <= args.rounds <= 50:
        parser.error('rounds must be in 1..50')
    try:
        import psycopg
    except ImportError:
        print(json.dumps({'status': 'not-executed', 'passed': False, 'actualDatabaseExecution': False, 'reason': 'Optional psycopg driver is missing'}))
        return 3
    if args.connection_file:
        parameters = json.loads(Path(args.connection_file).read_text(encoding='utf-8'))
    elif os.environ.get('MTW_PG_DSN'):
        parameters = {'conninfo': os.environ['MTW_PG_DSN']}
    else:
        print(json.dumps({'status': 'not-executed', 'passed': False, 'actualDatabaseExecution': False, 'reason': 'Set MTW_PG_DSN or provide an explicit connection file'}))
        return 3
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    try:
        histories, metadata, trace = capture(parameters, args.rounds, output / 'sql-events.jsonl')
        for name, history in histories.items():
            (output / (name + '-history.json')).write_text(json.dumps(history, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        (output / 'capture.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
        (output / 'sql-events.json').write_text(json.dumps(trace, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'passed': True, 'actualDatabaseExecution': True, 'roundsPerScenario': args.rounds}))
        return 0
    except Exception as error:
        # Never print a DSN, password, connection parameters or raw driver exception.
        failure = {'status': 'failed', 'passed': False, 'failure': type(error).__name__}
        (output / 'capture-failure.json').write_text(json.dumps(failure, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(failure))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
