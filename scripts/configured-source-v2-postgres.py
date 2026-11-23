"""Check explicit V2 source installation in a new owned PostgreSQL 18.6 cluster."""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import traceback
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'integrations/python'))
from moontxnwitness_capture.configured_source_v2 import install_configured_source_v2, SourceInstallPolicy
from moontxnwitness_capture.configured_sql_v2 import (
    SQLCaptureConfigV2, TableConfigV2, PrimaryKeyConfigV2, ColumnConfig, TEXT_COMPARISON)
from moontxnwitness_capture.configured_point_capture_v2 import PointCaptureV2
from moontxnwitness_capture.configured_async_window_v2 import ConfiguredAsyncCaptureWindowV2
from moontxnwitness_capture.configured_point_projection_v2 import PointProjectionOptionsV2
from moontxnwitness_capture.configured_window_v2 import (
    ConfiguredCaptureWindowV2, SourceInputsV2, observe_source_snapshot_v2)


def q(name): return '"' + name.replace('"', '""') + '"'
def lit(value): return "'" + value.replace("'", "''") + "'"
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def eq(actual, expected):
    if actual != expected: raise AssertionError((actual, expected))


def varchar_binding_fixture(control, connect_writer, schema, writer, output):
    table = TableConfigV2(schema, 'varchar_rows', PrimaryKeyConfigV2('id', 'uuid'),
        (ColumnConfig('email', 'text', TEXT_COMPARISON),))
    config = SQLCaptureConfigV2(table)
    policy = SourceInstallPolicy('mtw_source_v2_varchar', (writer,))
    target = q(schema) + '.varchar_rows'
    control.execute('CREATE TABLE ' + target + ' (id uuid PRIMARY KEY, email varchar(320) COLLATE pg_catalog."C" NOT NULL)')
    control.execute('GRANT SELECT, INSERT, UPDATE, DELETE ON ' + target + ' TO ' + q(writer))
    install_dir = output / 'varchar-install'
    install_configured_source_v2(control, install_dir, config, policy, opt_in=True)
    window = ConfiguredCaptureWindowV2(output / 'varchar-window', config, control, policy,
        SourceInputsV2.from_directory(install_dir), opt_in=True)
    enroll = window.psycopg_factory(connect_writer)
    key = uuid.UUID(int=1057)
    params = {'id': key, 'email': '首个🙂 '}
    select = 'SELECT id, email FROM ' + target + ' WHERE id=%(id)s::UUID'
    with enroll() as connection:
        insert = 'INSERT INTO ' + target + ' (id,email) VALUES (%(id)s::UUID,%(email)s::VARCHAR) RETURNING id'
        eq(connection.execute(insert, params).fetchall(), [(key,)])
        eq(connection.execute(select, {'id': key}).fetchall(), [(key, params['email'])])
    with enroll() as connection:
        update = 'UPDATE ' + target + ' SET email=%(email)s::VARCHAR WHERE id=%(id)s::UUID RETURNING id,email'
        changed = {**params, 'email': '修改后🙂 '}
        eq(connection.execute(update, changed).fetchall(), [(key, changed['email'])])
    eq(control.execute(select, {'id': key}).fetchall(), [(key, changed['email'])])
    bundle = window.seal()
    return {'name': 'varchar-assignment', 'bundle': str(bundle), 'expected': 'compatible',
        'config': config.to_dict(), 'policy': policy.to_dict(), 'bundleSha256': sha(bundle)}


def paged_snapshot_fixture(control, connect_writer, schema, writer, output):
    """Compare the two readers over the same 260 initialized row versions."""
    from psycopg import IsolationLevel

    table = TableConfigV2(schema, 'page_rows', PrimaryKeyConfigV2('id', 'int64'),
        (ColumnConfig('label', 'text', TEXT_COMPARISON),))
    config = SQLCaptureConfigV2(table)
    policy = SourceInstallPolicy('mtw_source_v2_page', (writer,))
    target = q(schema) + '.page_rows'
    control.execute('CREATE TABLE ' + target + ' (id bigint PRIMARY KEY, label text COLLATE pg_catalog."C" NOT NULL)')
    control.execute('INSERT INTO ' + target + " SELECT n,'row-'||n FROM pg_catalog.generate_series(1,260) n")
    control.execute('GRANT SELECT, INSERT, UPDATE, DELETE ON ' + target + ' TO ' + q(writer))
    install = output / 'page-install'
    install_configured_source_v2(control, install, config, policy, opt_in=True)
    installation = SourceInputsV2.from_directory(install)
    fixtures = []
    for profile in ('row-v2', 'paged-v1'):
        out = output / ('snapshot-' + profile)
        window = ConfiguredCaptureWindowV2(out, config, control, policy, installation,
            opt_in=True, snapshot_profile=profile)
        for keys in ((1, 128, 129), (256, 257, 260)):
            with window.psycopg_factory(connect_writer)() as connection:
                for key in keys:
                    eq(connection.execute('SELECT id,label FROM ' + target + ' WHERE id=%s', (key,)).fetchall(),
                        [(key, 'row-' + str(key))])
        path = window.seal()
        fixtures.append({'name': 'snapshot-' + profile, 'bundle': str(path), 'expected': 'compatible',
            'analysisOptions': {'pointFootprintOnly': True},
            'config': config.to_dict(), 'policy': policy.to_dict(), 'bundleSha256': sha(path)})
    window = ConfiguredCaptureWindowV2(output / 'snapshot-paged-late-commit', config, control, policy,
        installation, opt_in=True, snapshot_profile='paged-v1')
    connect = window.psycopg_factory(connect_writer)
    update = 'UPDATE ' + target + ' SET label=%s WHERE id=%s RETURNING id,label'
    with connect() as slow:
        eq(slow.execute(update, ('late', 1)).fetchall(), [(1, 'late')])
        with connect() as fast:
            eq(fast.execute(update, ('early', 260)).fetchall(), [(260, 'early')])
        middle = observe_source_snapshot_v2(control, output / 'paged-mid-commit', config, policy,
            installation, opt_in=True, snapshot_profile='paged-v1')
    path = window.seal()
    before_late = json.loads(middle.read_text('utf8'))['effectVersions']
    finished = json.loads((window.output / 'end' / 'snapshot-receipt.json').read_text('utf8'))['effectVersions']
    late = set(finished) - set(before_late)
    eq(len(late), 1)
    late_version = next(iter(late))
    eq(int(late_version) < max(map(int, before_late)), True)
    fixtures.append({'name': 'snapshot-paged-late-commit', 'bundle': str(path), 'expected': 'compatible',
        'config': config.to_dict(), 'policy': policy.to_dict(), 'bundleSha256': sha(path),
        'lateVersion': late_version, 'earlierVisibleMaximum': str(max(map(int, before_late)))})

    window = ConfiguredCaptureWindowV2(output / 'snapshot-paged-write-skew', config, control, policy,
        installation, opt_in=True, snapshot_profile='paged-v1')
    def repeatable_read():
        connection = connect_writer()
        connection.isolation_level = IsolationLevel.REPEATABLE_READ
        return connection

    connect = window.psycopg_factory(repeatable_read)
    select = 'SELECT id,label FROM ' + target + ' WHERE id=%s'
    barrier = threading.Barrier(2)

    def write_skew(key):
        with connect() as connection:
            observed = [connection.execute(select, (v,)).fetchone() for v in (1, 260)]
            eq(observed, [(1, 'late'), (260, 'early')])
            barrier.wait(timeout=20)
            eq(connection.execute(update, ('disabled', key)).fetchone(), (key, 'disabled'))

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(write_skew, (1, 260)))
    with connect() as connection:
        eq(connection.execute(select, (1,)).fetchone(), (1, 'disabled'))
    path = window.seal()
    fixtures.append({'name': 'snapshot-paged-write-skew', 'bundle': str(path), 'expected': 'refuted',
        'config': config.to_dict(), 'policy': policy.to_dict(), 'bundleSha256': sha(path),
        'originalTransactions': 3, 'expectedReducedTransactions': 2})
    return fixtures


def sqlalchemy_fixture(control, connect_writer, schema, writer, output):
    import sqlalchemy as sa
    from sqlalchemy.orm import DeclarativeBase, Session, mapped_column
    from sqlalchemy.pool import NullPool

    eq(sa.__version__, '2.0.55')
    table = TableConfigV2(schema, 'orm_rows', PrimaryKeyConfigV2('id', 'uuid'),
        (ColumnConfig('email', 'text', TEXT_COMPARISON),))
    config = SQLCaptureConfigV2(table)
    policy = SourceInstallPolicy('mtw_source_v2_orm', (writer,))
    target = q(schema) + '.orm_rows'
    control.execute('CREATE TABLE ' + target + ' (id uuid PRIMARY KEY, email varchar(320) COLLATE pg_catalog."C" NOT NULL)')
    control.execute('GRANT SELECT, INSERT, UPDATE, DELETE ON ' + target + ' TO ' + q(writer))
    installation = output / 'orm-install'
    install_configured_source_v2(control, installation, config, policy, opt_in=True)

    class Base(DeclarativeBase):
        pass

    class Member(Base):
        __tablename__ = 'orm_rows'
        __table_args__ = {'schema': schema}
        id = mapped_column(sa.Uuid, primary_key=True)
        email = mapped_column(sa.String(320), nullable=False)

    def execute(window=None):
        engine = sa.create_engine('postgresql+psycopg://', creator=connect_writer,
            poolclass=NullPool, pool_reset_on_return=None)
        if window is not None:
            @sa.event.listens_for(engine, 'connect')
            def enroll(raw_connection, record):
                record.dbapi_connection = window.wrap_connection(raw_connection)
        try:
            key = uuid.UUID(int=1060)
            with Session(engine, expire_on_commit=False) as session:
                member = Member(id=key, email='初始🙂 ')
                session.add(member)
                session.commit()
                session.refresh(member)
                refreshed = (member.id, member.email)
                member.email = '修改🙂 '
                session.commit()
            with Session(engine, expire_on_commit=False) as session:
                member = session.get(Member, key)
                queried = (member.id, member.email)
                session.delete(member)
                session.commit()
                missing = session.get(Member, key)
                session.commit()
            return refreshed, queried, missing, control.execute('SELECT id,email FROM ' + target).fetchall()
        finally:
            engine.dispose()

    baseline = execute()
    eq((baseline[0][1], baseline[1][1], baseline[2], baseline[3]), ('初始🙂 ', '修改🙂 ', None, []))
    window = ConfiguredCaptureWindowV2(output / 'orm-window', config, control, policy,
        SourceInputsV2.from_directory(installation), opt_in=True)
    eq(execute(window), baseline)
    bundle = window.seal()
    return {'name': 'sqlalchemy-crud-refresh', 'bundle': str(bundle), 'expected': 'compatible',
        'config': config.to_dict(), 'policy': policy.to_dict(), 'bundleSha256': sha(bundle),
        'sqlalchemyVersion': sa.__version__, 'businessParityVerified': True}


def async_sqlalchemy_fixtures(control, connect_writer, schema, writer, output, upstream=None, seed_campaign=False):
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.orm import DeclarativeBase, mapped_column
    from sqlalchemy.pool import NullPool

    table = TableConfigV2(schema, 'async_orm_rows', PrimaryKeyConfigV2('id', 'uuid'),
        (ColumnConfig('email', 'text', TEXT_COMPARISON),))
    config = SQLCaptureConfigV2(table)
    policy = SourceInstallPolicy('mtw_source_async_' + schema, (writer,))
    target = q(schema) + '.async_orm_rows'
    control.execute('CREATE TABLE ' + target + ' (id uuid PRIMARY KEY, email varchar(320) COLLATE pg_catalog."C" NOT NULL)')
    control.execute('GRANT SELECT, INSERT, UPDATE, DELETE ON ' + target + ' TO ' + q(writer))
    install_dir = output / 'async-orm-install'
    install_configured_source_v2(control, install_dir, config, policy, opt_in=True)
    installation = SourceInputsV2.from_directory(install_dir)

    class Base(DeclarativeBase):
        pass

    class Member(Base):
        __tablename__ = 'async_orm_rows'
        __table_args__ = {'schema': schema}
        id = mapped_column(sa.Uuid, primary_key=True)
        email = mapped_column(sa.String(320), nullable=False)

    key = uuid.UUID(int=1061)

    async def run(engine):
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            member = Member(id=key, email='初始🙂 ')
            session.add(member)
            await session.commit()
            await session.refresh(member)
            refreshed = (member.id, member.email)
            member.email = '修改🙂 '
            await session.commit()
        async with session_factory() as session:
            member = await session.get(Member, key)
            queried = (member.id, member.email)
            await session.delete(member)
            await session.commit()
            missing = await session.get(Member, key)
            await session.commit()
        return refreshed, queried, missing, control.execute('SELECT id,email FROM ' + target).fetchall()

    async def baseline(workload):
        engine = create_async_engine('postgresql+psycopg://', async_creator=connect_writer,
            poolclass=NullPool, pool_reset_on_return=None)
        try:
            return await workload(engine)
        finally:
            await engine.dispose()

    def new_window(name, **options):
        return ConfiguredAsyncCaptureWindowV2(output / name, config, control, policy, installation, opt_in=True, **options)

    def fixture(window, name, expected):
        bundle = window.seal()
        return {'name': name, 'bundle': str(bundle), 'expected': expected, 'config': config.to_dict(),
            'policy': policy.to_dict(), 'bundleSha256': sha(bundle), 'sqlalchemyVersion': sa.__version__}

    async def run_fixtures():
        expected = await baseline(run)
        eq((expected[0][1], expected[1][1], expected[2], expected[3]), ('初始🙂 ', '修改🙂 ', None, []))
        window = new_window('async-orm-window')
        async with window.sqlalchemy_engine(connect_writer) as engine:
            eq(await run(engine), expected)
            try:
                window.seal()
            except ValueError as error:
                eq(str(error), 'Finish the owned SQLAlchemy engine scope before sealing')
            else:
                raise AssertionError('Sealed an open engine scope')
        verified = fixture(window, 'async-sqlalchemy-crud-refresh', 'compatible')
        verified['businessParityVerified'] = True

        window = new_window('async-orm-pool-window', sqlalchemy_pool_size=1)
        async with window.sqlalchemy_engine(connect_writer) as engine:
            eq(await run(engine), expected)
        pooled = fixture(window, 'async-sqlalchemy-pooled-crud', 'compatible')
        life = json.loads(Path(pooled['bundle']).read_text('utf8'))['lifecycleText']
        events = [json.loads(line) for line in life.splitlines()]
        enrollments = [event for event in events if event['kind'] == 'configured-point-pool-enroll']
        leases = [json.loads(event['frameText']) for event in events if event['kind'] == 'configured-point-pool-checkout']
        eq(len(enrollments), 1)
        eq([lease['lease'] for lease in leases], list(range(1, len(leases) + 1)))
        eq(len({lease['backendPid'] for lease in leases}), 1)
        if len(leases) < 3:
            raise AssertionError('Expected actual physical connection reuse across SQLAlchemy sessions')
        pooled.update(businessParityVerified=True, physicalConnections=1, actualLeases=len(leases))

        window = new_window('async-orm-pool-invalidation', sqlalchemy_pool_size=1)
        async with window.sqlalchemy_engine(connect_writer) as engine:
            statement = sa.select(Member.id, Member.email).where(Member.id == key)
            async with engine.connect() as connection:
                eq((await connection.execute(statement)).fetchone(), None)
                await connection.commit()
                await connection.invalidate()
            async with engine.connect() as replacement:
                eq((await replacement.execute(statement)).fetchone(), None)
                await replacement.commit()
        invalidated = fixture(window, 'async-sqlalchemy-pool-invalidated', 'unknown')
        invalidated['expectedReason'] = 'configured_factory_unobserved'

        keys = (uuid.UUID(int=1063), uuid.UUID(int=1064))
        # Load reference rows before the window so both anomaly transactions
        # have the captured starting snapshot as their source.
        async with await connect_writer() as seed:
            for identity in keys:
                await seed.execute('INSERT INTO ' + target + ' (id,email) VALUES (%s,%s)', (identity, 'enabled'))
        window = new_window('async-orm-pool-write-skew', sqlalchemy_pool_size=2)
        async with window.sqlalchemy_engine(connect_writer) as engine:
            barrier = asyncio.Barrier(2)

            async def write_skew(key):
                async with engine.connect() as connection:
                    await connection.execution_options(isolation_level='REPEATABLE READ')
                    for identity in keys:
                        statement = sa.select(Member.id, Member.email).where(Member.id == identity)
                        eq((await connection.execute(statement)).fetchone(), (identity, 'enabled'))
                    await asyncio.wait_for(barrier.wait(), timeout=20)
                    await connection.execute(sa.update(Member).where(Member.id == key).values(email='disabled'))
                    await connection.commit()

            await asyncio.gather(*(write_skew(identity) for identity in keys))
        eq(control.execute('SELECT count(*) FROM ' + target + ' WHERE email=%s', ('disabled',)).fetchone()[0], 2)
        skew = fixture(window, 'async-sqlalchemy-pooled-write-skew', 'refuted')

        window = new_window('async-orm-unread-window')
        async with window.sqlalchemy_engine(connect_writer) as engine:
            async with engine.connect() as connection:
                await connection.execute(sa.insert(Member).values(id=key, email='undelivered'))
                await connection.commit()
                result = await connection.execute(sa.select(Member.id, Member.email).where(Member.id == key))
                result.close()
                await connection.commit()
        unread = fixture(window, 'async-sqlalchemy-prefetched-unread', 'unknown')
        unread['expectedReason'] = 'orm_unconsumed_result'
        fixtures = [verified, unread, pooled, invalidated, skew]
        if upstream is not None:
            fixtures.extend(await fastapi_users_fixtures(control, connect_writer, schema, writer,
                output, upstream, baseline, seed_campaign=seed_campaign))
        return fixtures

    if os.name == 'nt':
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
            return runner.run(run_fixtures())
    return asyncio.run(run_fixtures())


async def fastapi_users_fixtures(control, connect_writer, schema, writer, output, upstream, baseline, *, seed_campaign):
    from random import Random
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlalchemy.orm import DeclarativeBase
    sys.path.insert(0, str(ROOT/'experiments/business/fastapi_users'))
    from profile_demo import COMMIT, upstream as verify_upstream

    files = verify_upstream(upstream)
    from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTableUUID, SQLAlchemyUserDatabase

    class Base(DeclarativeBase):
        pass

    class User(SQLAlchemyBaseUserTableUUID, Base):
        __tablename__ = 'configured_users'
        __table_args__ = {'schema': schema}

    table = TableConfigV2(schema, User.__tablename__, PrimaryKeyConfigV2('id', 'uuid'), (
        ColumnConfig('email', 'text', TEXT_COMPARISON),
        ColumnConfig('hashed_password', 'text', TEXT_COMPARISON),
        ColumnConfig('is_active', 'bool'), ColumnConfig('is_superuser', 'bool'), ColumnConfig('is_verified', 'bool'),
    ))
    config = SQLCaptureConfigV2(table)
    policy = SourceInstallPolicy('mtw_source_users_' + schema, (writer,))
    target = q(schema) + '.configured_users'
    control.execute('CREATE TABLE ' + target + ' (id uuid PRIMARY KEY, '
        'email varchar(320) COLLATE pg_catalog."C" NOT NULL UNIQUE, '
        'hashed_password varchar(1024) COLLATE pg_catalog."C" NOT NULL, '
        'is_active boolean NOT NULL, is_superuser boolean NOT NULL, is_verified boolean NOT NULL)')
    control.execute('GRANT SELECT, INSERT, UPDATE, DELETE ON ' + target + ' TO ' + q(writer))
    seeds = tuple(range(30)) if seed_campaign else (None,)
    cases = []
    for seed in seeds:
        if seed is None:
            identity, email, active, verified = uuid.UUID(int=1062), 'user@example.invalid', True, False
        else:
            random = Random(seed)
            identity = uuid.UUID(int=random.getrandbits(128), version=4)
            email = f'user-{seed}@example.invalid'
            active, verified = bool(random.getrandbits(1)), bool(random.getrandbits(1))
        cases.append((seed, dict(id=identity, email=email, hashed_password='fixture-only',
            is_active=active, is_superuser=False, is_verified=verified)))
    if seed_campaign:
        plan_path = output / 'async-users-seeds.json'
        with plan_path.open('x', encoding='utf-8') as plan:
            json.dump({'upstreamCommit': COMMIT, 'seeds': list(seeds)}, plan, sort_keys=True)
            plan.write('\n')

    async def run(engine, data):
        identity = data['id']
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            db = SQLAlchemyUserDatabase(session, User)
            absent_before = await db.get(identity)
            created = await db.create(dict(data))
            created_state = (created.id, created.email, created.is_active, created.is_verified)
            changed = await db.update(created, {'is_active': not data['is_active']})
            observed = await db.get(identity)
            queried_state = (observed.id, observed.email, observed.is_active, observed.is_verified)
            await db.delete(changed)
            absent_after = await db.get(identity)
            # Keep this read-only transaction in the committed point-window model.
            await session.commit()
        return (absent_before, created_state, queried_state, absent_after,
                control.execute('SELECT id FROM ' + target).fetchall())

    async def run_duplicate(engine):
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        data = cases[0][1]
        identity = data['id']
        conflicting = uuid.UUID(int=41063)
        async with sessions() as session:
            db = SQLAlchemyUserDatabase(session, User)
            await db.create(dict(data))
            try:
                await db.create(dict(data, id=conflicting))
            except IntegrityError as error:
                sqlstate = error.orig.sqlstate
                await session.rollback()
            else:
                raise AssertionError('Expected the original unique-email constraint to reject the duplicate')
            row = await db.get(identity)
            eq(await db.get(conflicting), None)
            await db.delete(row)
        return sqlstate, control.execute('SELECT id FROM ' + target).fetchall()

    expected = []
    for _, data in cases:
        outcome = await baseline(lambda engine: run(engine, data))
        before = (data['id'], data['email'], data['is_active'], data['is_verified'])
        after = (data['id'], data['email'], not data['is_active'], data['is_verified'])
        eq(outcome, (None, before, after, None, []))
        expected.append(outcome)
    if seed_campaign:
        duplicate_expected = await baseline(run_duplicate)
        eq(duplicate_expected, ('23505', []))
    install_dir = output / 'async-users-install'
    install_configured_source_v2(control, install_dir, config, policy, opt_in=True)
    installation = SourceInputsV2.from_directory(install_dir)
    fixtures = []
    for (seed, data), outcome in zip(cases, expected, strict=True):
        suffix = '' if seed is None else f'-{seed:02d}'
        window = ConfiguredAsyncCaptureWindowV2(output / ('async-users-window' + suffix), config,
            control, policy, installation, opt_in=True)
        async with window.sqlalchemy_engine(connect_writer) as engine:
            eq(await run(engine, data), outcome)
        bundle = window.seal()
        record = {'name': 'fastapi-users-base-crud' + suffix, 'bundle': str(bundle), 'expected': 'compatible',
            'config': config.to_dict(), 'policy': policy.to_dict(), 'bundleSha256': sha(bundle),
            'upstreamCommit': COMMIT, 'upstreamFiles': files, 'businessParityVerified': True}
        if seed_campaign:
            record.update(seed=seed, seedPlanSha256=sha(plan_path))
        fixtures.append(record)
    if seed_campaign:
        window = ConfiguredAsyncCaptureWindowV2(output / 'async-users-duplicate', config, control,
            policy, installation, opt_in=True)
        async with window.sqlalchemy_engine(connect_writer) as engine:
            eq(await run_duplicate(engine), duplicate_expected)
        bundle = window.seal()
        fixtures.append({'name': 'fastapi-users-duplicate-email', 'bundle': str(bundle), 'expected': 'unknown',
            'config': config.to_dict(), 'policy': policy.to_dict(), 'bundleSha256': sha(bundle),
            'upstreamCommit': COMMIT, 'businessParityVerified': True, 'businessSqlstate': duplicate_expected[0]})
    return fixtures


def analysis_fixtures(control, connect_writer, config, policy, installation, output, key, fresh, other_key, *, with_reduction=False):
    """Run original SQL through wrappers; no model histories are constructed here."""
    import psycopg
    target=q(config.table.schema)+'.'+q(config.table.table)
    select='SELECT identity,balance,enabled FROM '+target+' WHERE identity=%s'
    insert='INSERT INTO '+target+'(identity,balance,enabled) VALUES(%s,%s,%s) RETURNING identity,balance,enabled'
    cases=[]
    def window(name):return ConfiguredCaptureWindowV2(output/name,config,control,policy,installation,opt_in=True)
    def enrolled(isolation=None):
        # Exercise the public owned-factory path, including its in-flight seal
        # guard. Application SQL and actual result consumption remain unchanged.
        def factory():
            raw=connect_writer()
            try:
                if isolation is not None:raw.isolation_level=isolation
                return raw
            except BaseException:
                try:raw.close()
                except BaseException:pass
                raise
        return w.psycopg_factory(factory)()
    w=window('crud');c=enrolled()
    eq(c.execute(select,(fresh,)).fetchall(),[])
    eq(c.execute(insert,(fresh,30,True)).fetchone(),(fresh,30,True))
    c.execute('UPDATE '+target+' SET balance=%s WHERE identity=%s',(31,fresh))
    eq(c.execute(select,(fresh,)).fetchone(),(fresh,31,True))
    eq(c.execute('DELETE FROM '+target+' WHERE identity=%s RETURNING balance',(fresh,)).fetchone(),(31,))
    eq(c.execute(select,(fresh,)).fetchall(),[])
    c.commit()
    c.execute(select,(key,)).fetchone();c.commit();c.close()
    path=w.seal();cases.append({'name':'crud','bundle':str(path),'expected':'compatible','config':config.to_dict(),'policy':policy.to_dict(),'bundleSha256':sha(path)})
    def reset():
        with connect_writer() as c:
            for identity in (key,other_key):c.execute('UPDATE '+target+' SET enabled=%s WHERE identity=%s',(True,identity))
    reset();w=window('rr-write-skew');barrier=threading.Barrier(2)
    def participant(identity):
        c=enrolled(psycopg.IsolationLevel.REPEATABLE_READ)
        try:
            before=[c.execute(select,(v,)).fetchone() for v in (key,other_key)]
            eq(all(r[2] for r in before),True);barrier.wait(timeout=20)
            c.execute('UPDATE '+target+' SET enabled=%s WHERE identity=%s',(False,identity));c.commit()
            return {'committed':True,'rows':len(before)}
        finally:c.close()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(participant,(key,other_key)))
    eq(control.execute('SELECT count(*) FROM '+target+' WHERE identity IN (%s,%s) AND enabled',(key,other_key)).fetchone()[0],0)
    path=w.seal();cases.append({'name':'rr-write-skew','bundle':str(path),'expected':'refuted','config':config.to_dict(),'policy':policy.to_dict(),'bundleSha256':sha(path),'participants':results})
    if with_reduction:
        reset();w=window('rr-write-skew-noise');barrier=threading.Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(participant,(key,other_key)))
        c=enrolled()
        try:
            # These observed reads depend on a committed anomaly writer. A
            # selection cannot silently replace their source with initial data.
            for _ in range(3):
                eq(c.execute(select,(key,)).fetchone()[2],False);c.commit()
        finally:c.close()
        path=w.seal();cases.append({'name':'rr-write-skew-noise','bundle':str(path),'expected':'refuted','config':config.to_dict(),'policy':policy.to_dict(),'bundleSha256':sha(path),'participants':results,'originalTransactions':5,'expectedReducedTransactions':2})
    reset();w=window('serializable-ordered')
    for identity in (key,other_key):
        c=enrolled(psycopg.IsolationLevel.SERIALIZABLE)
        try:
            before=[c.execute(select,(v,)).fetchone() for v in (key,other_key)]
            if all(r[2] for r in before):c.execute('UPDATE '+target+' SET enabled=%s WHERE identity=%s',(False,identity))
            c.commit()
        finally:c.close()
    eq(control.execute('SELECT count(*) FROM '+target+' WHERE identity IN (%s,%s) AND enabled',(key,other_key)).fetchone()[0],1)
    path=w.seal();cases.append({'name':'serializable-ordered','bundle':str(path),'expected':'compatible','config':config.to_dict(),'policy':policy.to_dict(),'bundleSha256':sha(path)})
    # No-op writes are observations too: dropping the two zero-row UPDATEs
    # below would incorrectly turn this nonserializable history into two
    # independent inserts. This protocol deliberately reports it as unknown.
    missing = fresh+100 if isinstance(fresh,int) else fresh+'-missing' if isinstance(fresh,str) else uuid.UUID(int=fresh.int+100)
    w=window('zero-write-skew');barrier=threading.Barrier(2)
    def no_op_participant(pair):
        own,other=pair
        c=enrolled(psycopg.IsolationLevel.REPEATABLE_READ)
        try:
            eq(c.execute('UPDATE '+target+' SET balance=%s WHERE identity=%s RETURNING identity,balance,enabled',(40,own)).fetchall(),[])
            barrier.wait(timeout=20)
            eq(c.execute(insert,(other,40,True)).fetchone(),(other,40,True));c.commit()
            return {'zeroRowWrite':True,'committed':True}
        finally:c.close()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(no_op_participant,((fresh,missing),(missing,fresh))))
    path=w.seal();cases.append({'name':'zero-write-skew','bundle':str(path),'expected':'unknown','expectedReason':'unsupported:window-zero-row-write','config':config.to_dict(),'policy':policy.to_dict(),'bundleSha256':sha(path),'participants':results})
    return cases


def async_analysis_fixtures(control, connect_writer, connect_async_writer, config, policy, installation, output, key, fresh, other, *, with_reduction=False):
    import psycopg

    target = q(config.table.schema) + '.' + q(config.table.table)
    select = 'SELECT identity,balance,enabled FROM ' + target + ' WHERE identity=%s'
    update = 'UPDATE ' + target + ' SET enabled=%s WHERE identity=%s'
    insert = 'INSERT INTO ' + target + '(identity,balance,enabled) VALUES(%s,%s,%s) RETURNING identity,balance,enabled'
    delete = 'DELETE FROM ' + target + ' WHERE identity=%s RETURNING balance'

    async def row(connection, identity):
        cursor = await connection.execute(select, (identity,))
        eq([column.name for column in cursor.description], ['identity', 'balance', 'enabled'])
        return await cursor.fetchone()

    async def crud(window, connect):
        async with await connect() as connection:
            cursor = await connection.execute(select, (fresh,))
            eq(await cursor.fetchall(), [])
        async with await connect() as connection:
            eq((await row(connection, key))[0], key)
            cursor = await connection.execute(insert, (fresh, 50, True))
            eq(await cursor.fetchmany(1), [(fresh, 50, True)])
            cursor = await connection.execute(update, (False, fresh))
            eq((cursor.description, cursor.rowcount), (None, 1))
            eq(await row(connection, fresh), (fresh, 50, False))
            cursor = await connection.execute(delete, (fresh,))
            eq(await cursor.fetchone(), (50,))
            cursor = await connection.execute(select, (fresh,))
            eq(await cursor.fetchall(), [])

    async def observe_constraint(connection):
        rows = [await row(connection, identity) for identity in (key, other)]
        return [result[2] for result in rows]

    async def apply_rule(connection, identity, enabled):
        if all(enabled):
            cursor = await connection.execute(update, (False, identity))
            eq(cursor.rowcount, 1)
            return True
        return False

    async def skew(connect, isolation, *, noise=0):
        connections = [await connect(isolation), await connect(isolation)]
        try:
            initial = [await observe_constraint(connection) for connection in connections]
            eq(initial, [[True, True], [True, True]])
            for connection, identity, observed in zip(connections, (key, other), initial):
                eq(await apply_rule(connection, identity, observed), True)
            await connections[0].commit()
            observations = {'committed': 2, 'initialEnabled': initial}
            if isolation == psycopg.IsolationLevel.REPEATABLE_READ:
                await connections[1].commit()
            else:
                try:
                    await connections[1].commit()
                except psycopg.errors.SerializationFailure as error:
                    eq((error.sqlstate, error.diag.sqlstate), ('40001', '40001'))
                    await connections[1].rollback()
                    observations['rollbackSqlstate'] = error.sqlstate
                else:
                    raise AssertionError('Expected PostgreSQL to abort the second Serializable writer')
                retry = await observe_constraint(connections[1])
                eq(retry, [False, True])
                eq(await apply_rule(connections[1], other, retry), False)
                await connections[1].commit()
                observations.update(retryEnabled=retry, retryCommitted=True)
            for _ in range(noise):
                eq((await row(connections[0], key))[2], False)
                await connections[0].commit()
            return observations
        finally:
            for connection in connections:
                await connection.close()

    async def cancelled_acquisition(window, connect):
        started = asyncio.Event()

        async def pending_factory():
            started.set()
            await asyncio.Future()

        pending = asyncio.create_task(window.psycopg_factory(pending_factory)())
        await started.wait()
        try:
            try:
                window.seal()
            except ValueError as error:
                assert 'factory' in str(error)
            else:
                raise AssertionError('In-flight acquisition unexpectedly sealed')
        finally:
            pending.cancel()
            try:
                await pending
            except asyncio.CancelledError:
                pass
        async with await connect() as connection:
            await row(connection, key)
        return {'originalCancellationObserved': pending.cancelled(), 'acquisitionGuardObserved': True}

    async def cancelled_execute(window, connect):
        raw = await connect_async_writer()
        connection = await connect()
        try:
            # The blocker rolls back and publishes no ledger effect. Observe
            # actual server lock wait before cancelling the business statement.
            await raw.execute(update, (True, key))
            pid = connection.info.backend_pid
            pending = asyncio.create_task(connection.execute(update, (False, key)))
            try:
                async with asyncio.timeout(10):
                    while True:
                        cursor = await raw.execute(
                            "SELECT NOT pg_catalog.pg_stat_clear_snapshot() IS NULL")
                        await cursor.fetchone()
                        cursor = await raw.execute("SELECT wait_event_type FROM pg_catalog.pg_stat_activity WHERE pid=%s", (pid,))
                        if await cursor.fetchone() == ('Lock',):
                            break
                        await asyncio.sleep(0.01)
            finally:
                pending.cancel()
                try:
                    await pending
                except asyncio.CancelledError:
                    pass
            eq(pending.cancelled(), True)
            await connection.rollback()
            await raw.rollback()
            eq((await row(connection, key))[2], False)
            await connection.commit()
            return {'originalCancellationObserved': True, 'serverLockWaitObserved': True, 'retryCommitted': True}
        finally:
            await connection.close()
            await raw.close()

    def run(name, scenario, expected, *, expected_reason=None, remaining=None):
        window = ConfiguredAsyncCaptureWindowV2(output/name, config, control, policy, installation, opt_in=True)

        async def factory(isolation=None):
            raw = await connect_async_writer()
            if isolation is not None:
                await raw.set_isolation_level(isolation)
            return raw

        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop if os.name == 'nt' else None) as runner:
            observations = runner.run(scenario(window, window.psycopg_factory(factory)))
        path = window.seal()
        result = {'name': name, 'bundle': str(path), 'config': config.to_dict(), 'policy': policy.to_dict(),
                  'bundleSha256': sha(path), 'expected': expected, 'asynchronous': True, 'observations': observations}
        if expected_reason is not None:
            result['expectedReason'] = expected_reason
        if remaining is not None:
            enabled = [control.execute(select, (identity,)).fetchone()[2] for identity in (key, other)]
            eq(sum(enabled), remaining)
            result['observations']['finalEnabled'] = enabled
        return result

    def reset():
        with connect_writer() as connection:
            for identity in (key, other):
                connection.execute(update, (True, identity))

    reset()
    results = [run('async-crud', crud, 'compatible')]
    results.append(run('async-rr-write-skew', lambda w, c: skew(c, psycopg.IsolationLevel.REPEATABLE_READ), 'refuted', remaining=0))
    if with_reduction:
        reset()
        noisy = run('async-rr-write-skew-noise', lambda w, c: skew(c, psycopg.IsolationLevel.REPEATABLE_READ, noise=3), 'refuted', remaining=0)
        noisy.update(originalTransactions=5, expectedReducedTransactions=2)
        results.append(noisy)
    reset()
    aborted = run('async-serializable-retry', lambda w, c: skew(c, psycopg.IsolationLevel.SERIALIZABLE), 'unknown', remaining=1)
    events = json.loads(json.loads(Path(aborted['bundle']).read_text('utf8'))['diagnosticTraceText'])['events']
    rollback, = [event for event in events if event['kind'] == 'rollback_ok']
    eq(rollback['commitResponse']['sqlstate'], '40001')
    txs = [event['tx'] for event in events if event['kind'] == 'begin']
    eq(len(set(txs)), 3)
    assert rollback['tx'] != txs[-1]
    results.append(aborted)
    results.append(run('async-cancelled-acquisition', cancelled_acquisition, 'unknown', expected_reason='configured_factory_unobserved'))
    results.append(run('async-cancelled-execute', cancelled_execute, 'unknown', expected_reason='orm_statement_failed'))
    return results


def suite(admin, connect, work, *, with_window=False, with_analysis=False, with_reduction=False, connect_async=None,
          with_sqlalchemy=False, fastapi_users_checkout=None, with_paged=False,
          fastapi_users_seed_campaign=False):
    records = []
    for index, kind in enumerate(('int64', 'text', 'uuid')):
        owner, writer, schema = 'source_owner_'+str(index), 'source_writer_'+str(index), 'app_'+str(index)
        password = secrets.token_hex(20)
        admin.execute('CREATE ROLE '+q(owner)+' NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS')
        admin.execute('CREATE ROLE '+q(writer)+' LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD '+lit(password))
        admin.execute('GRANT CREATE ON DATABASE '+q(admin.info.dbname)+' TO '+q(owner))
        admin.execute('CREATE SCHEMA '+q(schema)+' AUTHORIZATION '+q(owner))
        table = TableConfigV2(schema, 'rows', PrimaryKeyConfigV2('identity', kind, TEXT_COMPARISON if kind=='text' else None),
            (ColumnConfig('balance','int64'),ColumnConfig('enabled','bool')))
        config, target = SQLCaptureConfigV2(table), q(schema)+'."rows"'
        key = 7 if kind=='int64' else '客户🙂' if kind=='text' else uuid.UUID('a8098c1a-f86e-11da-bd1a-00112444be1e')
        fresh = 9 if kind=='int64' else '新客户🙂' if kind=='text' else uuid.UUID('00000000-0000-0000-0000-000000000009')
        pk_type = {'int64':'bigint','text':'text COLLATE pg_catalog."C"','uuid':'uuid'}[kind]
        with connect(autocommit=True) as control:
            control.execute('SET ROLE '+q(owner))
            # PK deliberately last physically: explicit projection is name-based.
            control.execute('CREATE TABLE '+target+' (balance bigint NOT NULL, enabled boolean NOT NULL, identity '+pk_type+' PRIMARY KEY)')
            control.execute('INSERT INTO '+target+' VALUES(17,true,%s)',(key,))
            control.execute('GRANT USAGE ON SCHEMA '+q(schema)+' TO '+q(writer))
            control.execute('GRANT SELECT,INSERT,UPDATE,DELETE ON '+target+' TO '+q(writer))
            policy = SourceInstallPolicy('mtw_source_v2_'+str(index),(writer,))
            installation = install_configured_source_v2(control,work/('install-'+str(index)),config,policy,opt_in=True).to_dict()
            eq(installation['status'],'installed-components-only')
            for field in ('catalogComponentsChecked','initialSnapshotComponentsChecked','initialLedgerComponentsChecked','actualCommitConfirmed'):
                eq(installation[field],True)
            for field in ('sourceFactsProduced','sourceAuthenticated','moonbitCatalogVerified','completeWindow','modelCoverageAccepted'):
                eq(installation[field],False)
            eq(installation['initialRows'],1)
            capture_path=work/('capture-'+str(index))
            window=None
            if with_window:
                window=ConfiguredCaptureWindowV2(work/('window-'+str(index)),config,control,policy,
                    SourceInputsV2.from_directory(work/('install-'+str(index))),opt_in=True)
                capture=window.observer;capture_path=window.output/'capture'
            else:capture = PointCaptureV2(capture_path,config,opt_in=True)
            raw = connect(user=writer,password=password)
            backend_pid = raw.info.backend_pid
            connection = window.wrap_connection(raw) if window else capture.wrap(raw)
            cursor = connection.execute('INSERT INTO '+target+'(identity,balance,enabled) VALUES(%s,%s,%s) RETURNING identity,balance,enabled',(fresh,10,True))
            eq(cursor.fetchone(),(fresh,10,True)); connection.commit()
            cursor = connection.execute('UPDATE '+target+' SET balance=%s WHERE identity=%s RETURNING identity,balance,enabled',(11,fresh))
            eq(cursor.fetchone(),(fresh,11,True)); connection.commit()
            cursor = connection.execute('DELETE FROM '+target+' WHERE identity=%s RETURNING identity,balance,enabled',(fresh,))
            eq(cursor.fetchone(),(fresh,11,True)); connection.commit()
            # Out-of-grammar PK mutation is rejected by the explicit source scope.
            import psycopg
            try: connection.execute('UPDATE '+target+' SET identity=%s WHERE identity=%s',(fresh,key))
            except psycopg.errors.CheckViolation as error: eq(error.sqlstate,'23514')
            else: raise AssertionError('Installed V2 key guard did not reject a changed key')
            connection.rollback(); connection.close()
            ledger = control.execute('SELECT version,base_version,operation,writer_login,writer_pid,row_key::text,row_values::text FROM '+q(policy.namespace)+'.effects ORDER BY version').fetchall()
            eq([r[2] for r in ledger],['INITIAL','INSERT','UPDATE','DELETE'])
            eq(len({r[0] for r in ledger}),4)
            eq(all(r[3]==writer and r[4]==backend_pid for r in ledger[1:]),True)
            eq(ledger[1][1],None)
            eq(ledger[2][1],ledger[1][0]); eq(ledger[3][1],ledger[2][0])
            eq(json.loads(ledger[3][5]),str(fresh) if kind=='uuid' else fresh)
            eq(ledger[3][6],None)
            eq(control.execute('SELECT balance,enabled,identity FROM '+target).fetchall(),[(17,True,key)])
            window_check=None
            if window:
                slow_key=101 if kind=='int64' else '慢提交🙂' if kind=='text' else uuid.UUID(int=101)
                fast_key=102 if kind=='int64' else '快提交🙂' if kind=='text' else uuid.UUID(int=102)
                slow=window.wrap_connection(connect(user=writer,password=password))
                fast=window.wrap_connection(connect(user=writer,password=password))
                statement='INSERT INTO '+target+'(identity,balance,enabled) VALUES(%s,%s,%s) RETURNING identity,balance,enabled'
                eq(slow.execute(statement,(slow_key,20,True)).fetchone(),(slow_key,20,True))
                eq(fast.execute(statement,(fast_key,21,True)).fetchone(),(fast_key,21,True))
                fast.commit();fast.close()
                middle_path=observe_source_snapshot_v2(control,work/('middle-'+str(index)),config,policy,
                    window.installation,opt_in=True)
                middle=json.loads(middle_path.read_text('utf8'))
                slow.commit();slow.close()
                bundle_path=window.seal();bundle=json.loads(bundle_path.read_text('utf8'))
                start=json.loads(json.loads(bundle['startInputText'])['receiptText'])
                end=json.loads(json.loads(bundle['endInputText'])['receiptText'])
                missed=set(end['effectVersions'])-set(middle['effectVersions'])
                eq(len(missed),1)
                late=next(iter(missed));eq(int(late)<max(map(int,middle['effectVersions'])),True)
                eq(set(start['effectVersions']).issubset(end['effectVersions']),True)
                eq(len(set(end['effectVersions'])-set(start['effectVersions'])),5)
                eq(end['rowsObserved'],3)
                # All three inputs are raw retained observations; no model
                # coverage flag is inferred from successful durability checks.
                eq(json.loads((window.output/'window-receipt.json').read_text('utf8'))['completeWindow'],False)
                window_check={'passed':True,'bundleSha256':sha(bundle_path),'startEffects':len(start['effectVersions']),
                    'endEffects':len(end['effectVersions']),'lateCommittedLowVersion':late,
                    'middleMaximumVersion':str(max(map(int,middle['effectVersions']))),
                    'fullLedgerDifferenceIncludesLateVersion':True,'completeWindow':False,'modelCoverageAccepted':False}
            else:capture.close()
            retained = [json.loads(line) for line in (capture_path/'lifecycle.jsonl').read_text('utf8').splitlines()]
            probes = [json.loads(event['frameText']) for event in retained if event['kind']=='configured-point-writer']
            eq(len(probes),5 if window else 3)
            eq(all(json.loads(p['deliveredText'])['login']==writer for p in probes),True)
            analysis=[]
            if with_analysis:
                if not with_window:raise ValueError('Analysis fixtures also require --with-window')
                analysis=analysis_fixtures(control,lambda:connect(user=writer,password=password),config,policy,window.installation,work/('analysis-'+str(index)),key,fresh,slow_key,with_reduction=with_reduction)
                if kind == 'uuid':
                    analysis.append(varchar_binding_fixture(control,
                        lambda: connect(user=writer,password=password),schema,writer,work))
                    if with_paged:
                        analysis.extend(paged_snapshot_fixture(control,
                            lambda: connect(user=writer,password=password),schema,writer,work))
                    if with_sqlalchemy:
                        analysis.append(sqlalchemy_fixture(control,
                            lambda: connect(user=writer,password=password),schema,writer,work))
                        if connect_async is not None:
                            analysis.extend(async_sqlalchemy_fixtures(control,
                                lambda: connect_async(user=writer,password=password),schema,writer,work,
                                upstream=fastapi_users_checkout, seed_campaign=fastapi_users_seed_campaign))
                if connect_async is not None:
                    async_key = 903 if kind == 'int64' else '异步新键🙂' if kind == 'text' else uuid.UUID(int=903)
                    analysis.extend(async_analysis_fixtures(control, lambda: connect(user=writer,password=password),
                        lambda: connect_async(user=writer,password=password),config,policy,window.installation,
                        work/('async-analysis-'+str(index)),key,async_key,slow_key,with_reduction=with_reduction))
            records.append({'keyType':kind,'passed':True,'initialRows':1,'committedEffects':3,'analysisFixtures':analysis,
                'sourceInstallationReceiptSha256':sha(work/('install-'+str(index))/'receipt-v2.json'),
                'sourceInstallationLogSha256':sha(work/('install-'+str(index))/'source-install-v2.jsonl'),
                'captureLogSha256':sha(capture_path/'lifecycle.jsonl'),
                'ledger':ledger,'writerCheckpoints':len(probes),'windowCheck':window_check,
                'sourceFactsProduced':False,'completeWindow':False,'modelCoverageAccepted':False})
    return records


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    target=cli.add_mutually_exclusive_group(required=True)
    target.add_argument('--bin',type=Path,help='PostgreSQL 18.6 binaries for a new owned local cluster')
    target.add_argument('--dsn-env',help='Environment variable for an isolated PostgreSQL 18.6 test service')
    cli.add_argument('--owned-database',action='store_true',help='Acknowledge the selected service is disposable and may receive test roles and tables')
    cli.add_argument('--output',type=Path,required=True)
    cli.add_argument('--with-window',action='store_true',help='Also seal raw window inputs and verify out-of-order commit visibility')
    cli.add_argument('--with-analysis',action='store_true',help='Also run committed CRUD, real RR write skew and ordered Serializable business windows')
    cli.add_argument('--with-reduction',action='store_true',help='Also capture source-dependent noise transactions for model-preserving reduction')
    cli.add_argument('--with-async',action='store_true',help='Exercise native async business connections in the same source-window scope')
    cli.add_argument('--with-sqlalchemy',action='store_true',help='Exercise paired SQLAlchemy ORM CRUD and refresh using the scoped NullPool recipe')
    cli.add_argument('--fastapi-users-checkout',type=Path,help='Compare the original pinned FastAPI Users SQLAlchemy base-user CRUD')
    cli.add_argument('--fastapi-users-seed-campaign',action='store_true',help='Record and run all 30 fixed base-user workloads with and without capture')
    cli.add_argument('--with-paged',action='store_true',help='Compare full and paged snapshots over 260 rows')
    args=cli.parse_args()
    if args.with_analysis and not args.with_window:cli.error('--with-analysis requires --with-window')
    if args.with_reduction and not args.with_analysis:cli.error('--with-reduction requires --with-analysis')
    if args.with_async and not args.with_analysis:cli.error('--with-async requires --with-analysis')
    if args.with_sqlalchemy and not args.with_analysis:cli.error('--with-sqlalchemy requires --with-analysis')
    if args.fastapi_users_checkout and not (args.with_async and args.with_sqlalchemy):
        cli.error('--fastapi-users-checkout requires --with-async and --with-sqlalchemy')
    if args.fastapi_users_seed_campaign and not args.fastapi_users_checkout:
        cli.error('--fastapi-users-seed-campaign requires --fastapi-users-checkout')
    if args.with_paged and not args.with_analysis:cli.error('--with-paged requires --with-analysis')
    if args.dsn_env and not args.owned_database:cli.error('--dsn-env requires --owned-database')
    if args.dsn_env and not os.environ.get(args.dsn_env):cli.error('the selected DSN environment variable is empty')
    work=args.output.resolve()
    if os.name=='nt':assert work.is_relative_to(Path(r'D:\CodexScratch').resolve())
    work.mkdir(parents=True,exist_ok=False)
    for name,version in [('psycopg','3.3.6'),('sqlglot','30.26.0')]:eq(importlib.metadata.version(name),version)
    if args.dsn_env:
        import psycopg
        from psycopg.conninfo import conninfo_to_dict
        service=conninfo_to_dict(os.environ[args.dsn_env])
        def connect(**kwargs):return psycopg.connect(**dict(service,**kwargs))
        def connect_async(**kwargs):return psycopg.AsyncConnection.connect(**dict(service,**kwargs))
        receipt={'format':'configured-source-v2-native-installation-validation/v1','passed':False,'actualDatabaseExecution':False,
            'actualV2InstallationExecuted':False,'formalPerformanceMeasurement':False,'windowProducerRequested':args.with_window,
            'analysisFixturesRequested':args.with_analysis,'reductionFixturesRequested':args.with_reduction,
            'fastapiUsersSeedCampaign':args.fastapi_users_seed_campaign,
            'sourceSha256':{str(Path(__file__).resolve().relative_to(ROOT)):sha(Path(__file__))}}
        try:
            with connect(autocommit=True) as admin:
                eq(int(admin.execute('SHOW server_version_num').fetchone()[0]),180006)
                receipt['postgresVersion']='postgres (PostgreSQL) 18.6';receipt['actualDatabaseExecution']=True
                receipt['records']=suite(admin,connect,work,with_window=args.with_window,with_analysis=args.with_analysis,
                    with_reduction=args.with_reduction,connect_async=connect_async if args.with_async else None,
                    with_sqlalchemy=args.with_sqlalchemy,fastapi_users_checkout=args.fastapi_users_checkout,
                    fastapi_users_seed_campaign=args.fastapi_users_seed_campaign,
                    with_paged=args.with_paged)
                receipt['actualV2InstallationExecuted'],receipt['passed']=True,True
        except BaseException:receipt['error']=traceback.format_exc()
        (work/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        print(json.dumps({'passed':receipt['passed'],'layouts':len(receipt.get('records',[])),'receipt':str(work/'receipt.json')}))
        if not receipt['passed']:print(receipt.get('error',''),file=sys.stderr)
        return 0 if receipt['passed'] else 1
    binaries=args.bin.resolve()
    version=subprocess.check_output([str(binaries/('postgres.exe' if os.name=='nt' else 'postgres')),'--version'],text=True).strip();eq(version,'postgres (PostgreSQL) 18.6')
    password=secrets.token_hex(20);(work/'password.txt').write_text(password+'\n',encoding='ascii')
    data,started=work/'data',False
    environment=dict(os.environ,TEMP=str(work),TMP=str(work));flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    receipt={'format':'configured-source-v2-native-installation-validation/v1','passed':False,'actualDatabaseExecution':False,
        'actualV2InstallationExecuted':False,'postgresVersion':version,'sourceFactsProduced':False,'completeWindow':False,
        'modelCoverageAccepted':False,'formalPerformanceMeasurement':False,'windowProducerRequested':args.with_window,'analysisFixturesRequested':args.with_analysis,'reductionFixturesRequested':args.with_reduction,
        'fastapiUsersSeedCampaign':args.fastapi_users_seed_campaign,
        'sourceSha256':{str(path.relative_to(ROOT)):sha(path) for path in [Path(__file__).resolve(),ROOT/'integrations/python/moontxnwitness_capture/configured_source_v2.py',ROOT/'integrations/python/moontxnwitness_capture/configured_point_capture_v2.py',ROOT/'integrations/python/moontxnwitness_capture/configured_window_v2.py']}}
    with (work/'control.log').open('xb') as log:
        def run(parts):subprocess.run([str(p) for p in parts],env=environment,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120,creationflags=flags)
        try:
            run([binaries/'initdb.exe','-D',data,'-U','mtw','--locale=C','--encoding=UTF8','--auth-host=scram-sha-256','--auth-local=trust','--pwfile='+str(work/'password.txt')])
            with socket.socket() as endpoint:endpoint.bind(('127.0.0.1',0));port=endpoint.getsockname()[1]
            run([binaries/'pg_ctl.exe','-D',data,'-l',work/'server.log','-o','-h 127.0.0.1 -p '+str(port)+' -c shared_buffers=32MB -c max_connections=10','-w','start']);started=True
            import psycopg
            def connect(**kwargs):
                options=dict(host='127.0.0.1',port=port,dbname='postgres',user='mtw',password=password);options.update(kwargs)
                return psycopg.connect(**options)
            def connect_async(**kwargs):
                options=dict(host='127.0.0.1',port=port,dbname='postgres',user='mtw',password=password);options.update(kwargs)
                return psycopg.AsyncConnection.connect(**options)
            with connect(autocommit=True) as admin:
                receipt['actualDatabaseExecution']=True
                receipt['records']=suite(admin,connect,work,with_window=args.with_window,with_analysis=args.with_analysis,
                    with_reduction=args.with_reduction,connect_async=connect_async if args.with_async else None,
                    with_sqlalchemy=args.with_sqlalchemy,fastapi_users_checkout=args.fastapi_users_checkout,
                    fastapi_users_seed_campaign=args.fastapi_users_seed_campaign,
                    with_paged=args.with_paged)
                receipt['actualV2InstallationExecuted'],receipt['passed']=True,True
        except BaseException:receipt['error']=traceback.format_exc()
        finally:
            if started and (data/'postmaster.pid').exists():
                actual=Path((data/'postmaster.pid').read_text('utf8').splitlines()[1]).resolve();assert actual==data
                run([binaries/'pg_ctl.exe','-D',data,'-m','fast','-w','stop'])
    (work/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'passed':receipt['passed'],'layouts':len(receipt.get('records',[])),'receipt':str(work/'receipt.json')}))
    if not receipt['passed']:print(receipt.get('error',''),file=sys.stderr)
    return 0 if receipt['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
