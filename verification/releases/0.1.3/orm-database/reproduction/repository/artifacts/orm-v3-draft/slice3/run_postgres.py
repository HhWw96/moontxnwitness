"""Actual strictly owned PG18 source rehearsal; still no public core proof."""
from __future__ import annotations
import bootstrap
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import traceback
import uuid

import psycopg
from psycopg import sql
from sqlalchemy import MetaData, event, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm.attributes import flag_modified
from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTableUUID, SQLAlchemyUserDatabase
from provenance_policy import UserScope, build, FIELDS
from install import install, qualified, finalize
from control_log import ControlConnection
from source_sink import SourceSink, verify as verify_sources
from async_adapter import ProvenanceObserver

IDS = tuple("00000000-0000-4000-8000-00000000000" + str(i) for i in (1, 2, 3))


def bindings():
    paths = [p for p in bootstrap.DRAFT.glob("*.py")]
    paths += [bootstrap.DRAFT / "contract-v2.json"]
    paths += [bootstrap.PARENT / name for name in ("async_adapter.py", "bootstrap.py", "local_postgres.py", "provenance_policy.py", "relation_contract.py")]
    paths += [bootstrap.ROOT / "integrations/python/moontxnwitness_capture" / name for name in ("capture.py", "capture_v3.py", "journal_v3.py", "__init__.py")]
    return {p.relative_to(bootstrap.ROOT).as_posix(): {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size} for p in paths}


class RecordingCursor(psycopg.AsyncCursor):
    async def execute(self, *args, **kwargs):
        try: return await super().execute(*args, **kwargs)
        except BaseException as error:
            self.connection._orm_native_error = error
            raise
    async def fetchone(self):
        try: return await super().fetchone()
        except BaseException as error:
            self.native_fetch_error = error
            raise


def models(schema):
    class Base(DeclarativeBase): metadata = MetaData(schema=schema)
    class Plain(SQLAlchemyBaseUserTableUUID, Base): __tablename__ = "plain_user"
    class Observed(SQLAlchemyBaseUserTableUUID, Base): __tablename__ = "observed_user"
    return Base, Plain, Observed


async def work(engine, model, details):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        database = SQLAlchemyUserDatabase(session, model)
        assert (await database.get(uuid.UUID(IDS[2]))).email == "legacy@example.invalid"
        await session.rollback()
        user = await database.create({"id": uuid.UUID(IDS[0]), "email": "fixture@example.invalid", "hashed_password": "controlled-fixture"})
        assert session.in_transaction() and isinstance(user.id, uuid.UUID)
        assert await database.get(user.id) is user
        physical = (await (await session.connection()).get_raw_connection()).driver_connection
        try:
            await database.create({"id": uuid.UUID(IDS[1]), "email": user.email, "hashed_password": "controlled-fixture"})
        except IntegrityError as error:
            assert error.orig.sqlstate == "23505" and error.orig is physical._orm_native_error
            details["duplicateEmail"] = {"sqlstate": error.orig.sqlstate, "identity": True}
        else: raise AssertionError("Duplicate email accepted")
        await session.rollback()
        user = await database.get(uuid.UUID(IDS[0]))
        physical = (await (await session.connection()).get_raw_connection()).driver_connection
        try:
            await database.update(user, {"hashed_password": None})
        except IntegrityError as error:
            assert error.orig.sqlstate == "23502" and error.orig.diag.column_name == "hashed_password"
            assert error.orig is physical._orm_native_error
            details["nullHash"] = {"sqlstate": error.orig.sqlstate, "column": error.orig.diag.column_name, "identity": True}
        else: raise AssertionError("NULL hash accepted")
        await session.rollback()
        user = await database.get(uuid.UUID(IDS[0]))
        user.is_active = False; await session.flush()
        nested = await session.begin_nested()
        user.email = "discarded@example.invalid"; await session.flush()
        await nested.rollback(); await session.refresh(user)
        assert user.email == "fixture@example.invalid" and not user.is_active
        flag_modified(user, "email"); await session.flush()  # Real same-value UPDATE.
        await session.commit()
        user = await database.get(uuid.UUID(IDS[0]))
        updated = await database.update(user, {"email": "changed@example.invalid"})
        assert updated is user and session.in_transaction()
        assert await database.delete(user) is None
        assert await database.get(uuid.UUID(IDS[0])) is None
        await session.rollback()
        again = await database.create({"id": uuid.UUID(IDS[0]), "email": "reinsert@example.invalid", "hashed_password": "controlled-fixture"})
        assert isinstance(again.id, uuid.UUID)
        await session.rollback()
    await engine.dispose()
    async with factory() as session:
        assert (await SQLAlchemyUserDatabase(session, model).get(uuid.UUID(IDS[0]))).email == "reinsert@example.invalid"
        await session.rollback()
    await engine.dispose()
    return {"getCreateUpdateDelete": True, "commitRefreshNewTransaction": True,
        "nestedRollback": True, "sameValueUpdate": True, "deleteReinsert": True,
        "preexistingRow": True, "poolDisposeReconnect": True, "UUIDReturn": True}


async def surface(config, scope, observer=None):
    raw = await psycopg.AsyncConnection.connect(**config, cursor_factory=RecordingCursor)
    connection = observer.wrap_async(raw) if observer else raw
    result = []
    try:
        plan = build(scope, "update", ("email",), scope.schema + "_" + scope.table + "_id")
        params = {"email": "reinsert@example.invalid", plan.key.pk_bind: IDS[0]}
        cursor = await connection.execute(plan.original_sql, params)
        before = {"description": cursor.description, "rownumber": cursor.rownumber,
            "rowcount": cursor.rowcount, "tag": cursor.statusmessage, "status": int(cursor.pgresult.status)}
        assert before == {"description": None, "rownumber": None, "rowcount": 1, "tag": "UPDATE 1", "status": 1}
        try: await cursor.fetchone()
        except psycopg.ProgrammingError as error:
            assert error is cursor.native_fetch_error
            before["fetchError"] = {"class": type(error).__name__, "message": str(error), "sqlstate": error.sqlstate, "identity": True}
        else: raise AssertionError("Original no-result fetch did not raise")
        result.append(before); await cursor.close(); await connection.commit()
        zero = build(scope, "delete", pk_bind="id")
        cursor = await connection.execute(zero.original_sql, {"id": IDS[1]})
        assert cursor.description is None and cursor.rowcount == 0 and cursor.rownumber is None and cursor.statusmessage == "DELETE 0"
        try: await cursor.fetchone()
        except psycopg.ProgrammingError as error:
            assert error is cursor.native_fetch_error
            result.append({"zeroCommand": True, "rowcount": 0, "tag": cursor.statusmessage,
                "fetchClass": type(error).__name__, "fetchMessage": str(error), "identity": True})
        else: raise AssertionError("Zero-row command exposed internal result")
        await cursor.close(); await connection.commit()
        for value, present in ((IDS[0], True), (IDS[1], False)):
            plan = build(scope, "get")
            cursor = await connection.execute(plan.original_sql, {"id_1": value})
            assert len(cursor.description) == 6 and cursor.rowcount == int(present) and cursor.rownumber == 0
            assert cursor.statusmessage == "SELECT " + str(int(present))
            row = await cursor.fetchone()
            assert (row is not None) == present
            if present: assert len(row) == 6 and row[0] == uuid.UUID(value)
            assert await cursor.fetchone() is None
            result.append({"pointRead": True, "present": present, "rowcount": cursor.rowcount,
                "rownumber": cursor.rownumber, "description": [(col.name, col.type_code) for col in cursor.description], "tag": cursor.statusmessage})
            await cursor.close(); await connection.rollback()
    finally: await connection.close()
    return result


async def run(args):
    if not re.fullmatch(r"mtw_orm_v3_[a-f0-9]{12}", args.schema): raise ValueError("Controlled fresh schema required")
    output = Path(args.output); output.mkdir(parents=True, exist_ok=False)
    config = json.loads(Path(os.environ["MTW_PG_CONNECTION_FILE"]).read_text(encoding="utf-8"))
    config = {"connect_timeout": 5, "options": "-c statement_timeout=10000 -c lock_timeout=5000"} | config
    Base, Plain, Observed = models(args.schema)
    receipt = {"schema": 1, "draft": True, "passed": False, "actualPostgresExecution": False,
        "coreProofAccepted": False, "completeCapture": False, "sourceSchema": "orm-source-draft/2",
        "sourceBindings": bindings(), "upstream": bootstrap.verify_upstream()}
    observer = sink = None
    controls = []
    async def creator(): return await psycopg.AsyncConnection.connect(**config, cursor_factory=RecordingCursor)
    plain_engine = create_async_engine("postgresql+psycopg://", async_creator=creator, pool_size=1, max_overflow=0)
    observed_engine = None
    try:
        with psycopg.connect(**(config | {"autocommit": True})) as setup:
            setup.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(args.schema)))
            receipt["actualPostgresExecution"], receipt["serverVersion"] = True, setup.info.server_version
        async with plain_engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            for model in (Plain, Observed):
                await connection.execute(insert(model).values(id=uuid.UUID(IDS[2]), email="legacy@example.invalid", hashed_password="controlled-fixture"))
        await plain_engine.dispose()
        scope = UserScope(args.schema, "observed_user", IDS)
        sink = SourceSink(output / "source-observations.jsonl")
        with psycopg.connect(**(config | {"autocommit": True})) as raw_setup:
            setup = ControlConnection(raw_setup, sink); controls.append(setup)
            installed = install(setup, scope, diagnostic_path=output / "pre-migration-catalog.json")
        (output / "installation.json").write_text(json.dumps(installed.metadata, indent=2) + "\n", encoding="utf-8")
        receipt["plainDetails"] = {}; receipt["plain"] = await work(plain_engine, Plain, receipt["plainDetails"])
        observer = ProvenanceObserver(output / "journal", installed, sink)
        observed_engine = create_async_engine("postgresql+psycopg://", async_creator=creator, pool_size=1, max_overflow=0)
        counts = {name: 0 for name in ("connect", "checkout", "checkin", "reset", "invalidate")}
        def wrap(dbapi, record): dbapi._connection = observer.wrap_async(dbapi.driver_connection)
        event.listen(observed_engine.sync_engine, "connect", wrap)
        def counter(name):
            def count(*args, **kwargs): counts[name] += 1
            return count
        for name in counts: event.listen(observed_engine.sync_engine, name, counter(name))
        receipt["observedDetails"] = {}; receipt["observed"] = await work(observed_engine, Observed, receipt["observedDetails"])
        receipt["plainSurface"] = await surface(config, UserScope(args.schema, "plain_user", IDS))
        receipt["observedSurface"] = await surface(config, scope, observer)
        assert receipt["plain"] == receipt["observed"] and receipt["plainSurface"] == receipt["observedSurface"]
        await observed_engine.dispose()
        with psycopg.connect(**(config | {"autocommit": True})) as raw_setup:
            setup = ControlConnection(raw_setup, sink); controls.append(setup)
            final_record = finalize(setup, installed)
            ledger, state = final_record["ledger"], final_record["state"]
        assert not any(row["key"] == IDS[1] for row in ledger), "Failed unique INSERT created an actual effect"
        assert any(row["action"] == "DELETE" for row in ledger) and len(ledger) >= 6
        sink.append(final_record)
        receipt["ledgerCount"], receipt["poolCounts"] = len(ledger), counts
        (output / "effect-ledger.json").write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
        receipt["journal"] = observer.close(source_closed=False).as_dict()
        receipt["diagnostic"] = observer.export_diagnostic(output / "diagnostic-trace.json")
        receipt["sourceObservations"] = sink.close()
        assert verify_sources(sink.path)["sha256"] == receipt["sourceObservations"]["sha256"]
        receipt["passed"] = True
    except BaseException as error:
        receipt["failure"] = {"class": type(error).__name__, "message": str(error) if isinstance(error, (ValueError, TypeError, AttributeError, AssertionError)) else None,
            "sqlstate": getattr(error, "sqlstate", None), "frames": [{"file": Path(f.filename).name, "line": f.lineno, "function": f.name} for f in traceback.extract_tb(error.__traceback__)]}
    finally:
        await plain_engine.dispose()
        if observed_engine: await observed_engine.dispose()
        if observer:
            try: receipt.setdefault("journal", observer.close(source_closed=False).as_dict())
            except BaseException as error: receipt["storageFailureClass"] = type(error).__name__
        if sink:
            try: receipt.setdefault("sourceObservations", sink.close())
            except BaseException as error: receipt["sourceFailureClass"] = type(error).__name__
        receipt["sourceBindingsAfter"] = bindings()
        receipt["controlCoverageGaps"] = [gap for control in controls for gap in control.gaps]
        if receipt["controlCoverageGaps"]: receipt["passed"] = False
        receipt["sourceBindingsUnchanged"] = receipt["sourceBindings"] == receipt["sourceBindingsAfter"]
        if not receipt["sourceBindingsUnchanged"]: receipt["passed"] = False
        (output / "database-draft-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print("ORM source slice " + ("passed" if receipt["passed"] else "failed"))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--schema", required=True); parser.add_argument("--output", required=True)
    if os.name == "nt": asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    raise SystemExit(asyncio.run(run(parser.parse_args())))
