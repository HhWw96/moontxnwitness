"""Actual original ORM workload through the candidate package, cache on/off.

Run only from run_owned.py. No download, installation, compiler or analyzer.
"""
from __future__ import annotations
import argparse
import ast
import asyncio
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback
import uuid
import zipfile
from common import HERE, CANDIDATE, ROOT, binding, inputs, connection_config, under

def frozen_upstream():
    source = (HERE / 'frozen_upstream_bootstrap.py').read_text(encoding='utf8')
    wanted = {'COMMIT', 'ARCHIVE_SHA256', 'PREFIX', 'UPSTREAM'}
    nodes = [node for node in ast.parse(source).body if
        (isinstance(node, ast.FunctionDef) and node.name == 'verify_upstream') or
        (isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in wanted for t in node.targets))]
    namespace = {'DRAFT': ROOT / 'artifacts/orm-v3-draft', 'Path': Path,
        'hashlib': hashlib, 'json': json, 'zipfile': zipfile}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'frozen-upstream-verifier', 'exec'), namespace)
    report = namespace['verify_upstream']()
    return namespace['UPSTREAM'], report

def definitions():
    import psycopg
    import sqlalchemy
    from sqlalchemy import MetaData
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlalchemy.orm import DeclarativeBase
    from sqlalchemy.orm.attributes import flag_modified
    import fastapi_users_db_sqlalchemy as upstream
    from moontxnwitness_capture.orm import build, UserScope
    source = (HERE / 'frozen_run_postgres.py').read_text(encoding='utf8')
    names = {'RecordingCursor', 'models', 'work', 'surface'}
    nodes = [node for node in ast.parse(source).body if
        (isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names) or
        (isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'IDS' for t in node.targets))]
    assert len(nodes) == 5
    namespace = dict(psycopg=psycopg, uuid=uuid, MetaData=MetaData, IntegrityError=IntegrityError,
        async_sessionmaker=async_sessionmaker, DeclarativeBase=DeclarativeBase,
        flag_modified=flag_modified, SQLAlchemyBaseUserTableUUID=upstream.SQLAlchemyBaseUserTableUUID,
        SQLAlchemyUserDatabase=upstream.SQLAlchemyUserDatabase, build=build, UserScope=UserScope)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'frozen-original-orm-workload', 'exec'), namespace)
    extraction = {node.name: hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()
        for node in nodes if hasattr(node, 'name')}
    return namespace, extraction

def native_append(connection, row):
    """Fixture-only ACK log; observation failure must not mask original errors."""
    try:
        if len(connection._orm_native_replies) >= 512:
            connection._orm_native_reply_gap = True
        else:
            connection._orm_native_replies.append(row)
    except BaseException:
        connection._orm_native_reply_gap = True

def native_reply(connection, command, before, result=None, error=None):
    try:
        row = {'request': command.decode('ascii'), 'before': before,
            'after': int(connection.info.transaction_status), 'acknowledged': False}
        if error is not None:
            row.update(errorClass=type(error).__name__, sqlstate=getattr(error, 'sqlstate', None))
        else:
            tag = getattr(result, 'command_status', None)
            row.update(resultStatus=int(result.status) if result is not None else None,
                commandTag=tag.decode('ascii') if isinstance(tag, bytes) else None,
                acknowledged=result is not None and int(result.status) == 1 and tag in (b'COMMIT', b'ROLLBACK'))
        native_append(connection, row)
    except BaseException:
        connection._orm_native_reply_gap = True

async def execute_mode(output, enabled, config, workload):
    import psycopg
    from psycopg import sql
    from sqlalchemy import event, insert
    from sqlalchemy.ext.asyncio import create_async_engine
    from moontxnwitness_capture.orm import UserScope, ProvenanceObserver, SourceSink
    from moontxnwitness_capture._orm_source_sink import verify
    from support.install import install, finalize
    from support.control_log import ControlConnection
    output.mkdir(parents=True, exist_ok=False)
    schema = 'mtw_orm_v3_' + uuid.uuid4().hex[:12]
    ids = workload['IDS']
    Base, Plain, Observed = workload['models'](schema)
    observer = sink = observed_engine = None
    controls, physical_connections = [], []
    receipt = {'schema': 1, 'passed': False, 'actualDatabaseExecution': False, 'cacheEnabled': enabled,
        'controlledSchema': schema, 'completeCapture': False, 'coreProofAccepted': False,
        'collectorModule': 'moontxnwitness_capture._orm_async', 'failure': None}
    class RecordingConnection(psycopg.AsyncConnection):
        def _exec_command(self, command, *args, **kwargs):
            wanted = command in (b'COMMIT', b'ROLLBACK')
            before = None
            if wanted:
                try: before = int(self.info.transaction_status)
                except BaseException: self._orm_native_reply_gap = True
            try:
                result = yield from super()._exec_command(command, *args, **kwargs)
            except BaseException as error:
                if wanted:
                    native_reply(self, command, before, error=error)
                raise
            if wanted:
                native_reply(self, command, before, result=result)
            return result
    async def creator():
        raw = await RecordingConnection.connect(**config, cursor_factory=workload['RecordingCursor'])
        raw._orm_native_replies, raw._orm_native_reply_gap = [], False
        physical_connections.append(raw)
        return raw
    plain_engine = create_async_engine('postgresql+psycopg://', async_creator=creator, pool_size=1, max_overflow=0)
    try:
        with psycopg.connect(**(config | {'autocommit': True})) as setup:
            setup.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            receipt.update(actualDatabaseExecution=True, serverVersion=setup.info.server_version)
            assert 180000 <= setup.info.server_version < 190000
        async with plain_engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            for model in (Plain, Observed):
                await connection.execute(insert(model).values(id=uuid.UUID(ids[2]), email='legacy@example.invalid', hashed_password='controlled-fixture'))
        await plain_engine.dispose()
        scope = UserScope(schema, 'observed_user', ids)
        sink = SourceSink(output / 'source-observations.jsonl')
        with psycopg.connect(**(config | {'autocommit': True})) as raw:
            controlled = ControlConnection(raw, sink); controls.append(controlled)
            installed = install(controlled, scope, diagnostic_path=output / 'pre-migration-catalog.json')
        (output / 'installation.json').write_text(json.dumps(installed.metadata, indent=2) + '\n', encoding='utf8')
        receipt['plainDetails'] = {}
        receipt['plain'] = await workload['work'](plain_engine, Plain, receipt['plainDetails'])
        observer = ProvenanceObserver(output / 'journal', installed, sink, cache_enabled=enabled)
        observed_engine = create_async_engine('postgresql+psycopg://', async_creator=creator, pool_size=1, max_overflow=0)
        counts = {name: 0 for name in ('connect', 'checkout', 'checkin', 'reset', 'invalidate')}
        def wrap(dbapi, record): dbapi._connection = observer.wrap_async(dbapi.driver_connection)
        event.listen(observed_engine.sync_engine, 'connect', wrap)
        def counter(name):
            def count(*args, **kwargs): counts[name] += 1
            return count
        for name in counts: event.listen(observed_engine.sync_engine, name, counter(name))
        receipt['observedDetails'] = {}
        receipt['observed'] = await workload['work'](observed_engine, Observed, receipt['observedDetails'])
        receipt['plainSurface'] = await workload['surface'](config, UserScope(schema, 'plain_user', ids))
        receipt['observedSurface'] = await workload['surface'](config, scope, observer)
        assert receipt['plain'] == receipt['observed']
        assert receipt['plainDetails'] == receipt['observedDetails']
        assert receipt['plainSurface'] == receipt['observedSurface']
        assert counts['connect'] >= 2 and counts['checkout'] > counts['connect']
        await observed_engine.dispose()
        with psycopg.connect(**(config | {'autocommit': True})) as raw:
            controlled = ControlConnection(raw, sink); controls.append(controlled)
            final_record = finalize(controlled, installed)
        ledger, state = final_record['ledger'], final_record['state']
        assert not any(row['key'] == ids[1] for row in ledger)
        assert any(row['action'] == 'DELETE' for row in ledger) and len(ledger) >= 6
        assert not any(row.get('newImage', {}).get('email') == 'discarded@example.invalid' for row in ledger if row.get('newImage') is not None)
        sink.append(final_record)
        receipt['poolCounts'], receipt['ledgerCount'] = counts, len(ledger)
        receipt['semanticLedger'] = sorted([{key: row[key] for key in ('key','action','oldPresent','newPresent','oldImage','newImage')} for row in ledger], key=lambda row: json.dumps(row, sort_keys=True))
        receipt['semanticState'] = {key: {'present': row['present'], 'image': row['image']} for key, row in state.items()}
        (output / 'effect-ledger.json').write_text(json.dumps(ledger, indent=2) + '\n', encoding='utf8')
        receipt['journal'] = observer.close(source_closed=False).as_dict()
        receipt['diagnostic'] = observer.export_diagnostic(output / 'diagnostic-trace.json')
        receipt['sourceObservations'] = sink.close()
        assert verify(sink.path)['sha256'] == receipt['sourceObservations']['sha256']
        receipt['cache'] = {'enabled': observer.cache.enabled, 'hits': observer.cache.hits, 'misses': observer.cache.misses,
            'compilations': observer.cache.compilations, 'evictions': observer.cache.evictions, 'bypasses': observer.cache.bypasses,
            'retained': observer.cache.retained, 'context': asdict(observer.cache.context)}
        if enabled:
            assert observer.cache.compilations == 35 and observer.cache.hits > 0
        else:
            assert observer.cache.compilations > 35 and observer.cache.retained == {'entries': 0, 'bytes': 0}
        receipt['initializationAck'] = installed.metadata['initializationWindow'][-1]
        receipt['finalizationAck'] = final_record['finalizationWindow'][-1]
        assert receipt['initializationAck']['commandTag'] == receipt['finalizationAck']['commandTag'] == 'COMMIT'
        receipt['passed'] = True
    except BaseException as error:
        receipt['failure'] = {'class': type(error).__name__, 'sqlstate': getattr(error, 'sqlstate', None),
            'message': str(error) if isinstance(error, (ValueError, AssertionError, TypeError, AttributeError)) else None,
            'frames': [{'file': Path(frame.filename).name, 'line': frame.lineno, 'function': frame.name} for frame in traceback.extract_tb(error.__traceback__)]}
    finally:
        for engine in (plain_engine, observed_engine):
            if engine is not None:
                try: await engine.dispose()
                except BaseException as error: receipt.setdefault('cleanupFailures', []).append(type(error).__name__); receipt['passed'] = False
        if observer:
            try: receipt.setdefault('journal', observer.close(source_closed=False).as_dict())
            except BaseException as error: receipt['storageFailureClass'] = type(error).__name__; receipt['passed'] = False
            receipt['coverageGaps'] = list(observer.gaps)
        if sink:
            try: receipt.setdefault('sourceObservations', sink.close())
            except BaseException as error: receipt['sourceFailureClass'] = type(error).__name__; receipt['passed'] = False
        receipt['controlCoverageGaps'] = [gap for control in controls for gap in control.gaps]
        receipt['nativeReplyCoverageGap'] = any(raw._orm_native_reply_gap for raw in physical_connections)
        receipt['nativeBusinessReplies'] = [{'physicalConnection': index, 'replies': raw._orm_native_replies} for index, raw in enumerate(physical_connections)]
        replies = [row for raw in physical_connections for row in raw._orm_native_replies]
        receipt['nativeAckBoundary'] = {'scope': 'Independent fixture observation of actual SQLAlchemy physical-connection replies; not written back into the capture or source proof',
            'commitConfirmed': sum(row.get('request') == 'COMMIT' and row.get('acknowledged') is True and row.get('commandTag') == 'COMMIT' and row.get('after') == 0 for row in replies),
            'rollbackConfirmed': sum(row.get('request') == 'ROLLBACK' and row.get('acknowledged') is True and row.get('commandTag') == 'ROLLBACK' and row.get('after') == 0 for row in replies),
            'unknownReplies': sum(row.get('acknowledged') is not True for row in replies)}
        if receipt['nativeAckBoundary']['commitConfirmed'] == 0 or receipt['nativeAckBoundary']['rollbackConfirmed'] == 0:
            receipt['passed'] = False
        if receipt['controlCoverageGaps'] or receipt['nativeReplyCoverageGap']: receipt['passed'] = False
        (output / 'database-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf8')
    return receipt

async def run(output, run_root, connection_file):
    output = under(output, run_root)
    if output != Path(run_root).resolve() / 'database': raise ValueError('Use the owned database output directory')
    output.mkdir(parents=True, exist_ok=False)
    before = inputs()
    receipt = {'schema': 1, 'kind': 'isolated-candidate-orm-actual-db-comparison', 'passed': False,
        'actualDatabaseExecution': False, 'releaseAcceptance': False, 'completeCapture': False, 'coreProofAccepted': False,
        'formalPerformanceMeasured': False, 'analyzerExecuted': False, 'sourceBindingsBefore': before}
    try:
        config = connection_config(run_root, connection_file)
        upstream_path, receipt['upstream'] = frozen_upstream()
        package_path = CANDIDATE / 'payload/integrations/python'
        sys.path[:0] = [str(package_path), str(upstream_path)]
        import sqlalchemy, psycopg, fastapi_users_db_sqlalchemy
        from moontxnwitness_capture import orm
        from moontxnwitness_capture import _orm_async
        assert sqlalchemy.__version__ == '2.0.55' and psycopg.__version__ == '3.3.6'
        assert Path(orm.__file__).resolve() == package_path / 'moontxnwitness_capture/orm.py'
        assert Path(_orm_async.__file__).resolve() == package_path / 'moontxnwitness_capture/_orm_async.py'
        assert Path(fastapi_users_db_sqlalchemy.__file__).resolve() == upstream_path / 'fastapi_users_db_sqlalchemy/__init__.py'
        receipt['runtime'] = {'python': sys.version.split()[0], 'sqlalchemy': sqlalchemy.__version__, 'psycopg': psycopg.__version__}
        receipt['actualCollectorFiles'] = {name: binding(package_path / 'moontxnwitness_capture' / name)
            for name in ('orm.py','_orm_policy.py','_orm_async.py','_orm_raw_async.py')}
        workload, receipt['extractedOriginalWorkloadAstSha256'] = definitions()
        modes = []
        for enabled, name in ((False, 'cache-disabled'), (True, 'cache-enabled')):
            mode = await execute_mode(output / name, enabled, config, workload)
            modes.append(mode)
            receipt['actualDatabaseExecution'] |= mode['actualDatabaseExecution']
            if not mode['passed']: raise AssertionError('First actual mode failed; original logs and expectations retained')
        left, right = modes
        fields = ('plain','observed','plainDetails','observedDetails','plainSurface','observedSurface','semanticLedger','semanticState','ledgerCount')
        receipt['modeComparisons'] = {name: left[name] == right[name] for name in fields}
        assert all(receipt['modeComparisons'].values())
        receipt['modes'] = [{'name': name, 'passed': mode['passed'], 'cache': mode['cache'],
            'receipt': name + '/database-receipt.json', **binding(output / name / 'database-receipt.json')}
            for name, mode in zip(('cache-disabled','cache-enabled'), modes)]
        receipt['passed'] = True
    except BaseException as error:
        receipt['failure'] = {'class': type(error).__name__, 'message': str(error) if isinstance(error, (ValueError, AssertionError)) else None,
            'frames': [{'file': Path(frame.filename).name, 'line': frame.lineno, 'function': frame.name} for frame in traceback.extract_tb(error.__traceback__)]}
    finally:
        receipt['sourceBindingsAfter'] = inputs()
        receipt['sourceBindingsUnchanged'] = receipt['sourceBindingsAfter'] == before
        if not receipt['sourceBindingsUnchanged']: receipt['passed'] = False
        (output / 'comparison-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'passed': receipt['passed'], 'actualDatabaseExecution': receipt['actualDatabaseExecution'],
        'receipt': 'database/comparison-receipt.json'}))
    return 0 if receipt['passed'] else 1

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    run_root = under(os.environ['MTW_V013_RUN_ROOT'], HERE / 'executions')
    if os.name == 'nt': asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    raise SystemExit(asyncio.run(run(args.output, run_root, os.environ['MTW_PG_CONNECTION_FILE'])))
