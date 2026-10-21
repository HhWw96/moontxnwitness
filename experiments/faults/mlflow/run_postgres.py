"""Controlled actual-PG rehearsal of the unchanged MLflow affected component.

This is not the complete MLflow server. The upstream lock/update method and
SqlLatestMetric class are compiled from their original AST, without edits.
Only the unrelated runs table and application/session wiring are fixtures.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import gzip
import os
import json
import re
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

try:
    import psycopg
    from psycopg import sql
    import sqlalchemy as sa
    from sqlalchemy.orm import declarative_base, relationship, backref, Session
except ImportError as error:
    print(json.dumps({'status': 'not-executed', 'passed': False,
                      'actualDatabaseExecution': False,
                      'missingDependency': error.name}))
    raise SystemExit(3)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'integrations/python'))
from moontxnwitness_capture.capture_v3 import CaptureV3Session

COMMITS = {'before': 'c2dcdb96c62c75f35af3f28b5d493c0cf139a856',
           'fixed': '40c146a23518813e8488e55fc9752e08c3a8bad5'}
RUN_ID = '12345678901234567890123456789012'


def digest(content):
    return hashlib.sha256(content).hexdigest()


def original_node(label, file, name, parent=None):
    with gzip.open(HERE / 'upstream' / label / (file + '.gz'), 'rb') as stream:
        content = stream.read(2 * 1024 * 1024 + 1)
    assert len(content) <= 2 * 1024 * 1024, 'Frozen upstream source size exceeded'
    frozen = json.loads((HERE / 'upstream/fetch-receipt.json').read_text())
    expected = next(r['sha256'] for r in frozen
                    if r['label'] == label and r['file'] == file and 'sha256' in r)
    assert digest(content) == expected, 'Frozen upstream source changed'
    tree = ast.parse(content.decode('utf-8'))
    container = next(n for n in tree.body if getattr(n, 'name', '') == parent) if parent else tree
    node = next(n for n in container.body if getattr(n, 'name', '') == name)
    return node, {'file': file, 'sha256': expected, 'node': name,
                  'astSha256': digest(ast.dump(node, include_attributes=False).encode()),
                  'firstLine': node.lineno, 'lastLine': node.end_lineno}


def load_component(label, schema):
    base = declarative_base(metadata=sa.MetaData(schema=schema))

    class SqlRun(base):
        # Minimal foreign-key fixture; the affected method never queries runs.
        __tablename__ = 'runs'
        run_uuid = sa.Column(sa.String(32), primary_key=True)

    namespace = dict(vars(sa), sa=sa, Base=base, relationship=relationship,
                     backref=backref, Metric=SimpleNamespace,
                     get_current_time_millis=lambda: int(time.time() * 1000))
    model, model_binding = original_node(label, 'mlflow/store/tracking/dbmodels/models.py',
                                         'SqlLatestMetric')
    exec(compile(ast.Module(body=[model], type_ignores=[]), 'frozen-model-'+label, 'exec'), namespace)
    method, method_binding = original_node(label, 'mlflow/store/tracking/sqlalchemy_store.py',
                                           '_update_latest_metrics_if_necessary', 'SqlAlchemyStore')
    exec(compile(ast.Module(body=[method], type_ignores=[]), 'frozen-method-'+label, 'exec'), namespace)
    store_type = type('FrozenAffectedStore', (), {
        '_update_latest_metrics_if_necessary': namespace['_update_latest_metrics_if_necessary']})
    return base, SqlRun, namespace['SqlLatestMetric'], store_type(), [model_binding, method_binding]


def run_case(label, connection, output):
    assert not output.exists()
    output.mkdir(parents=True)
    source_files = [Path(__file__), ROOT / 'integrations/python/moontxnwitness_capture/capture_v3.py',
                    ROOT / 'integrations/python/moontxnwitness_capture/journal_v3.py']
    source_before = {p.relative_to(ROOT).as_posix(): {'sha256': digest(p.read_bytes()),
                     'bytes': p.stat().st_size} for p in source_files}
    (output / 'source-snapshots').mkdir()
    for p in source_files:
        (output / 'source-snapshots' / (p.name + '.gz')).write_bytes(gzip.compress(p.read_bytes(), mtime=0))
    schema = 'mtw_mlflow_' + label + '_' + digest(str(output.resolve()).encode())[:12]
    assert re.fullmatch('[a-z0-9_]+', schema)
    base, run_model, metric, store, bindings = load_component(label, schema)
    params = dict(connection)
    params['options'] = '-c statement_timeout=15000 -c lock_timeout=10000 -c deadlock_timeout=100'
    setup = sa.create_engine('postgresql+psycopg://', creator=lambda: psycopg.connect(**params))
    keys_a = ['X'] + [f'a{i:04}' for i in range(499)]
    keys_b = ['Y'] + [f'b{i:04}' for i in range(499)]
    orders = {'A': keys_a + keys_b, 'B': keys_b + keys_a}
    with setup.begin() as conn:
        conn.exec_driver_sql('CREATE SCHEMA ' + schema)
    base.metadata.create_all(setup)
    with setup.begin() as conn:
        conn.execute(sa.insert(run_model), [{'run_uuid': RUN_ID}])
        conn.execute(sa.insert(metric), [dict(run_uuid=RUN_ID, key=k, value=0.0,
                                             step=0, timestamp=0, is_nan=False)
                                         for k in keys_a + keys_b])
    setup.dispose()
    capture = CaptureV3Session(output / 'journal', exclusive_writers=False)
    capture.publish_snapshot({}, consistent=False)
    capture.gap('affected_component_only', 'This raw SQL rehearsal is an execution-fault case, not a complete relation/isolation proof.')
    engine = sa.create_engine('postgresql+psycopg://', creator=lambda: psycopg.connect(**params),
                              pool_size=2, max_overflow=0)
    mutex, first_start, release = threading.Lock(), threading.Barrier(2), threading.Event()
    state = {name: {'pending': 0, 'done': 0, 'pid': None, 'committed': False} for name in orders}
    controller, errors = [], []
    sql_log = (output / 'sql-executions.jsonl').open('xb')
    sql_bytes = 0
    sql_complete = True

    def record_sql(phase, statement, parameters=None, **fields):
        nonlocal sql_bytes, sql_complete
        try:
            item = {'phase': phase, 'worker': threading.current_thread().name,
                    'sql': statement, **fields}
            if parameters is not None:
                item['parameters'] = capture.encode(parameters)
            line = (json.dumps(item, ensure_ascii=False, allow_nan=False)+'\n').encode()
            with mutex:
                if len(line) > 512 * 1024 or sql_bytes + len(line) > 16 * 1024 * 1024:
                    raise ValueError('Controlled SQL observation budget exceeded')
                sql_log.write(line)
                sql_bytes += len(line)
        except Exception:
            sql_complete = False
            capture.gap('controlled_sql_log_incomplete', 'Fixture SQL observations could not be retained completely.')

    @sa.event.listens_for(engine, 'connect')
    def observe_connection(dbapi, record):
        # Native dialect/driver initialization ran before this listener.
        name = threading.current_thread().name
        if name in state:
            with mutex:
                state[name]['pid'] = dbapi.info.backend_pid
        record.dbapi_connection = capture.wrap(dbapi, role='mlflow-'+name)

    @sa.event.listens_for(engine, 'before_cursor_execute')
    def before(conn, cursor, statement, parameters, context, many):
        record_sql('before', statement, parameters, executemany=many)
        name = threading.current_thread().name
        if name in state and 'FOR UPDATE' in statement.upper():
            with mutex:
                state[name]['pending'] += 1
                first = state[name]['pending'] == 1
            if first:
                first_start.wait(timeout=8)

    @sa.event.listens_for(engine, 'after_cursor_execute')
    def after(conn, cursor, statement, parameters, context, many):
        record_sql('after', statement, rowcount=cursor.rowcount, executemany=many)
        name = threading.current_thread().name
        if name in state and 'FOR UPDATE' in statement.upper():
            with mutex:
                state[name]['done'] += 1
                first = state[name]['done'] == 1
            if first and not release.wait(timeout=8):
                raise RuntimeError('Controller did not observe the registered lock schedule')

    @sa.event.listens_for(engine, 'handle_error')
    def failed(context):
        original = context.original_exception
        record_sql('error', context.statement,
                   sqlstate=getattr(original, 'sqlstate', None),
                   driverClass=type(original).__name__)

    def worker(name):
        step = 1 if name == 'A' else 2
        objects = [metric(run_uuid=RUN_ID, key=k, value=float(step), timestamp=step,
                          step=step, is_nan=False) for k in orders[name]]
        try:
            with Session(engine) as session:
                with session.begin():
                    store._update_latest_metrics_if_necessary(objects, session)
            with mutex:
                state[name]['committed'] = True
        except BaseException as exc:
            original = getattr(exc, 'orig', exc)
            with mutex:
                errors.append({'worker': name, 'class': type(exc).__name__,
                               'driverClass': type(original).__name__,
                               'sqlstate': getattr(original, 'sqlstate', None),
                               'primary': getattr(getattr(original, 'diag', None), 'message_primary', None)})

    threads = [threading.Thread(target=worker, name=name, args=(name,)) for name in orders]
    control_error = None
    try:
        for thread in threads:
            thread.start()
        deadline = time.monotonic() + 7
        with psycopg.connect(**connection, autocommit=True) as monitor:
            while time.monotonic() < deadline:
                with mutex:
                    current = {name: dict(value) for name, value in state.items()}
                if all(value['done'] >= 1 for value in current.values()):
                    controller.append({'gate': 'both-first-batches-completed'})
                    break
                pids = [value['pid'] for value in current.values() if value['pid'] is not None]
                waiting = monitor.execute(
                    'SELECT pid,wait_event_type,wait_event FROM pg_stat_activity WHERE pid=ANY(%s)',
                    (pids,)).fetchall() if pids else []
                blocked = {row[0] for row in waiting if row[1] == 'Lock'}
                if any(value['done'] >= 1 for value in current.values()) and blocked:
                    controller.append({'gate': 'one-completed-other-observed-waiting',
                                       'observedWaits': [list(row) for row in waiting]})
                    break
                if errors:
                    raise RuntimeError('Worker failed before registered schedule was established')
                time.sleep(0.01)
            else:
                raise RuntimeError('Registered schedule observation timed out')
    except BaseException as exc:
        control_error = type(exc).__name__
    finally:
        release.set()
        for thread in threads:
            thread.join(timeout=25)
        alive = [thread.name for thread in threads if thread.is_alive()]
        engine.dispose()
        storage = capture.close(source_closed=False)
        sql_log.flush()
        os.fsync(sql_log.fileno())
        sql_log.close()
    capture.export_diagnostic(output / 'capture.json')
    with psycopg.connect(**connection, autocommit=True) as monitor:
        rows = monitor.execute(sql.SQL('SELECT key,value,step,timestamp FROM {}.latest_metrics ORDER BY key').format(sql.Identifier(schema))).fetchall()
    (output / 'final-rows.json').write_text(json.dumps(rows, ensure_ascii=False)+'\n', encoding='utf-8')
    deadlocks = [error for error in errors if error['sqlstate'] == '40P01']
    committed = sum(value['committed'] for value in state.values())
    source_after = {p.relative_to(ROOT).as_posix(): {'sha256': digest(p.read_bytes()),
                    'bytes': p.stat().st_size} for p in source_files}
    passed = source_before == source_after and sql_complete and not alive and not control_error and len(rows) == 1000 and (
        (label == 'before' and len(deadlocks) == 1 and len(errors) == 1 and committed == 1)
        or (label == 'fixed' and not errors and committed == 2 and all(row[2] == 2 for row in rows)))
    receipt = {'schema': 1, 'passed': passed, 'actualDatabaseExecution': True,
               'scope': 'Unchanged affected upstream method/model; minimal runs fixture, not entire MLflow server',
               'commit': COMMITS[label], 'label': label, 'sourceBindings': bindings,
               'executionFault': 'deadlock' if deadlocks else None,
               'isolationViolationClaim': False, 'G2Claim': False,
               'committed': committed, 'errors': errors, 'controller': controller,
               'controllerError': control_error, 'threadsStillAlive': alive,
               'workers': state, 'keysEach': 1000, 'originalBatchSize': 500,
               'finalRowsSha256': digest((output / 'final-rows.json').read_bytes()),
               'captureSha256': digest((output / 'capture.json').read_bytes()),
               'sqlExecutionsSha256': digest((output / 'sql-executions.jsonl').read_bytes()),
               'sqlObservationsComplete': sql_complete,
               'journal': storage.as_dict() if hasattr(storage, 'as_dict') else storage,
               'versions': {'sqlalchemy': sa.__version__, 'psycopg': psycopg.__version__},
               'runtimeSourceBindings': source_before,
               'runtimeSourceBindingsAfter': source_after,
               'runtimeSourceUnchanged': source_before == source_after}
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--connection-file', type=Path, default=os.environ.get('MTW_PG_CONNECTION_FILE'))
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    assert sa.__version__ == '2.0.55' and psycopg.__version__ == '3.3.6', 'Install frozen fixture requirements'
    assert not args.output.exists()
    args.output.mkdir(parents=True)
    if args.connection_file:
        connection = json.loads(args.connection_file.read_text(encoding='utf-8'))
    elif os.environ.get('MTW_PG_DSN'):
        connection = psycopg.conninfo.conninfo_to_dict(os.environ['MTW_PG_DSN'])
    else:
        receipt = {'schema':1,'status':'not-executed','passed':False,'actualDatabaseExecution':False,'reason':'No explicit PostgreSQL connection configuration'}
        (args.output / 'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(receipt)); return 3
    connection.setdefault('connect_timeout', 5)
    with psycopg.connect(**connection) as probe:
        version_number = probe.info.server_version
        version_string = probe.info.parameter_status('server_version')
    if not 180000 <= version_number < 190000:
        receipt = {'schema': 1, 'status': 'not-executed', 'passed': False,
                   'actualDatabaseExecution': False, 'serverVersion': version_string,
                   'reason': 'Controlled fixture requires PostgreSQL 18'}
        (args.output / 'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(receipt)); return 3
    results = [run_case(label, connection, args.output / label) for label in COMMITS]
    receipt = {'schema': 1, 'passed': all(result['passed'] for result in results),
               'actualDatabaseExecution': True, 'serverVersion': version_string,
               'serverVersionNumber': version_number, 'cases': [{key:result[key] for key in
                   ('label','passed','committed','executionFault','errors')} for result in results],
               'notCompletePlanAcceptance': True}
    (args.output / 'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(receipt))
    return 0 if receipt['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
