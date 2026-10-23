"""Actual pinned FastAPI Users base-user CRUD with the configured source profile.

Creates a fresh retained fixture schema on an explicitly owned PG18 instance.
Runs upstream business methods; never writes semantic history facts by hand.
"""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'integrations/python'))
COMMIT='6397ace506d829a2ee12786da5d724c3f4c6b634'


def upstream(path):
    path=Path(path).resolve();command=['git','-C',str(path)]
    head=subprocess.check_output(command+['rev-parse','HEAD'],stderr=subprocess.DEVNULL).decode().strip()
    if head!=COMMIT:raise ValueError('Use the declared immutable FastAPI Users SQLAlchemy v7.0.0 commit')
    names=subprocess.check_output(command+['ls-tree','-r','--name-only','HEAD','--','fastapi_users_db_sqlalchemy']).decode().splitlines()
    names=[name for name in names if name.endswith('.py')]
    if not names:raise ValueError('Pinned runtime package is missing')
    actual={file.relative_to(path).as_posix() for file in (path/'fastapi_users_db_sqlalchemy').rglob('*.py')}
    if actual!=set(names):raise ValueError('Untracked or missing runtime module in the upstream package')
    hashes={}
    for name in names:
        original=subprocess.check_output(command+['show','HEAD:'+name])
        if (path/name).read_bytes()!=original:raise ValueError('Pinned upstream runtime source was modified')
        hashes[name]=hashlib.sha256(original).hexdigest()
    sys.path.insert(0,str(path));return hashes


async def run(args,kwargs,receipt):
    import psycopg
    import sqlalchemy
    from sqlalchemy.orm import DeclarativeBase
    from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
    from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTableUUID,SQLAlchemyUserDatabase
    from moontxnwitness_capture.orm import UserScope
    from moontxnwitness_capture.profiles.fastapi_users import install_user_profile
    if psycopg.__version__!='3.3.6' or sqlalchemy.__version__!='2.0.55':raise ValueError('Pinned driver/compiler versions required')
    setup=psycopg.connect(**dict(kwargs,autocommit=True));engine=capture=None
    try:
        if not 180000<=setup.info.server_version<190000:raise ValueError('Owned PostgreSQL18 required')
        receipt.update(actualDatabaseExecution=True,server=setup.execute('SELECT version()').fetchone()[0],
                       psycopg=psycopg.__version__,sqlalchemy=sqlalchemy.__version__)
        schema='mtw_orm_v3_'+uuid.uuid4().hex[:12];setup.execute('CREATE SCHEMA "'+schema+'"')
        ids=tuple(str(uuid.uuid4()) for _ in range(3));receipt.update(fixtureSchema=schema,knownIds=ids)
        class Base(DeclarativeBase):pass
        class User(SQLAlchemyBaseUserTableUUID,Base):
            __tablename__='observed_user'
            __table_args__={'schema':schema}
        engine=create_async_engine('postgresql+psycopg://',async_creator=lambda:psycopg.AsyncConnection.connect(**kwargs),pool_size=2,max_overflow=0)
        # Explicit fixture/schema setup precedes the profile window. The locked
        # installer independently verifies the original resulting catalog.
        async with engine.begin() as connection:await connection.run_sync(Base.metadata.create_all)
        Session=async_sessionmaker(engine,expire_on_commit=False)
        async with Session() as session:
            database=SQLAlchemyUserDatabase(session,User)
            await database.create({'id':uuid.UUID(ids[2]),'email':'legacy@example.invalid',
                'hashed_password':'fixture-only','is_active':True,'is_superuser':False,'is_verified':False})
        await engine.dispose()
        capture,control=install_user_profile(setup,UserScope(schema,'observed_user',ids),Path(args.output)/'profile')
        capture.attach_engine(engine);checks=[]
        async with Session() as session:
            database=SQLAlchemyUserDatabase(session,User)
            legacy=await database.get(uuid.UUID(ids[2]));assert legacy.email=='legacy@example.invalid'
            checks.append('get-existing-real-upstream')
            assert await database.get(uuid.UUID(ids[1])) is None;checks.append('get-absent-real-upstream')
            created=await database.create({'id':uuid.UUID(ids[0]),'email':'created@example.invalid',
                'hashed_password':'fixture-only','is_active':True,'is_superuser':False,'is_verified':False})
            assert str(created.id)==ids[0] and created.email=='created@example.invalid';checks.append('create-commit-refresh-real-upstream')
            updated=await database.update(created,{'is_active':False})
            assert updated.is_active is False;checks.append('update-commit-refresh-real-upstream')
            observed=await database.get(uuid.UUID(ids[0]));assert observed.is_active is False;checks.append('get-updated-real-upstream')
            await database.delete(updated)
            assert await database.get(uuid.UUID(ids[0])) is None;checks.append('delete-and-negative-get-real-upstream')
        capture.finalize(control)
        package=capture.export_profile(Path(args.output)/'profile-source.json')
        receipt.update(status='producer-passed',passed=True,businessChecks=checks,sourcePackage=package,
            fullMappingCoverageAccepted=False,reason='Actual business/collector run only; independent MoonBit promotion has not run')
    finally:
        if engine is not None:await engine.dispose()
        if capture is not None:capture.close()
        setup.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream-root',required=True)
    parser.add_argument('--connection-file',default=os.environ.get('MTW_PG_CONNECTION_FILE'))
    parser.add_argument('--output',required=True)
    args=parser.parse_args();output=Path(args.output).resolve();output.mkdir(parents=True,exist_ok=False)
    receipt={'schema':1,'kind':'actual-upstream-base-user-profile','status':'not-executed',
        'actualDatabaseExecution':False,'formalPerformanceMeasurement':False,'upstreamCommit':COMMIT,
        'handwrittenHistory':False,'fullMappingCoverageAccepted':False}
    code=1
    try:
        if not args.connection_file:
            receipt['reason']='Explicit owned database configuration required';return 3
        receipt['upstreamFiles']=upstream(args.upstream_root)
        kwargs=json.loads(Path(args.connection_file).read_text(encoding='utf8'))
        kwargs.setdefault('connect_timeout',5);kwargs['options']='-c statement_timeout=10000 -c lock_timeout=5000'
        if sys.platform=='win32':
            with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:runner.run(run(args,kwargs,receipt))
        else:asyncio.run(run(args,kwargs,receipt))
        code=0
    except ImportError as error:
        receipt.update(status='not-executed',reason='Optional pinned business dependency missing',errorClass=type(error).__name__);code=3
    except BaseException as error:
        import traceback
        receipt.update(status='failed',passed=False,errorClass=type(error).__name__,sqlstate=getattr(error,'sqlstate',None),
            assertion=str(error) if isinstance(error,AssertionError) else None,
            frames=[{'file':Path(frame.filename).name,'line':frame.lineno} for frame in traceback.extract_tb(error.__traceback__)]);code=1
    finally:(output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
    return code


if __name__=='__main__':raise SystemExit(main())
