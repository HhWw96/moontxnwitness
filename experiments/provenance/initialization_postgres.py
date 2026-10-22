"""Actual PG setup confirmation/failure-lock supplement, not release acceptance."""
from pathlib import Path
import argparse
import json
import hashlib
import platform
import traceback
from unittest.mock import patch

import psycopg
from presence_profile import PresenceCapture, PresencePointProfile, verify_presence_installation
from moontxnwitness_capture.presence import implementation_bindings
from postgres_test import connection_factory
from prototype import ProvenanceError, controlled_schema, identifier


class Setup:
    """Delegate real setup operations; explicit, recorded fault injection only."""
    def __init__(self, raw, mode="normal"):
        self.raw, self.mode, self.calls = raw, mode, 0
        self.controls = []
        self.original_error = None

    def __getattr__(self, name):
        return getattr(self.raw, name)

    def execute(self, sql, params=None, **kwargs):
        self.calls += 1
        if sql != "COMMIT":
            return self.raw.execute(sql, params, **kwargs)
        before = int(self.raw.info.transaction_status)
        if self.mode == "rollback-tag":
            try:
                self.raw.execute("SELECT 1/0")
            except psycopg.errors.DivisionByZero as error:
                self.controls.append({"sql": "SELECT 1/0", "injected": True,
                                      "actualServerErrorSqlstate": error.sqlstate})
            else:
                raise AssertionError("Injected server statement did not abort setup")
        result = self.raw.execute(sql, params, **kwargs)
        self.controls.append({"sql": sql, "statusBeforeProxy": before,
                              "statusAtActualCommand": 3 if self.mode == "rollback-tag" else before,
                              "statusAfter": int(self.raw.info.transaction_status),
                              "commandTag": result.statusmessage,
                              "pgStatus": int(result.pgresult.status), "noRows": result.description is None})
        if self.mode == "discard-ack":
            self.original_error = psycopg.OperationalError("injected discarded setup COMMIT response")
            raise self.original_error
        return result


def profile_table(raw, schema, table):
    profile = PresencePointProfile(schema, table)
    raw.execute("CREATE TABLE " + profile.names.business + "(id text PRIMARY KEY,value text NOT NULL)")
    raw.execute("INSERT INTO " + profile.names.business + " VALUES('a','original')")
    return profile


def state(raw, profile):
    return {
        "versionColumns": raw.execute("SELECT count(*) FROM pg_catalog.pg_attribute WHERE attrelid=%s::regclass AND attname=%s AND NOT attisdropped",
                                      (profile.names.business, profile.names.version_column)).fetchone()[0],
        "ownedTables": {suffix: raw.execute("SELECT pg_catalog.to_regclass(%s)",
                                             (profile.names.object(suffix),)).fetchone()[0] is not None
                        for suffix in ("installation", "audit", "state")},
        "businessRows": raw.execute("SELECT id,value FROM " + profile.names.business + " ORDER BY id").fetchall(),
    }


def assert_locked(session, setup):
    assert not session._initialized and session.installation is None
    assert session.document()["presenceFacts"]["initial"] == []
    assert session.document()["events"] == []
    before = setup.calls
    try:
        session.initialize(setup)
    except ProvenanceError:
        pass
    else:
        raise AssertionError("Failed observer retried initialization")
    assert before == setup.calls
    try:
        session.wrap(setup.raw)
    except ProvenanceError:
        pass
    else:
        raise AssertionError("Failed observer admitted a business wrapper")
    return {"sameObserverRetryRejected": True, "retrySentNoSQL": True,
            "wrappingRejected": True, "initialFactsPublished": False}


def positive(connect, raw, schema, folder):
    profile = profile_table(raw, schema, "confirmed_crud")
    setup = Setup(raw)
    session = PresenceCapture(profile, keys=("a", "new", "never"), exclusive_writers=True)
    session.initialize(setup)
    acknowledgement = session._initialization_ack.copy()
    assert acknowledgement == {"sql": "COMMIT", "statusBefore": 2, "statusAfter": 0,
                               "commandTag": "COMMIT", "pgStatus": 1, "noRows": True,
                               "actualCommitConfirmed": True}
    results = []
    with connect() as business:
        wrapped = session.wrap(business)
        results.append(wrapped.execute(profile.read_sql, ("never",)).fetchone())
        wrapped.execute(profile.insert_sql, ("new", "created"))
        results.append(wrapped.execute(profile.read_sql, ("new",)).fetchone())
        wrapped.execute(profile.update_sql, ("created", "new"))
        wrapped.execute(profile.delete_sql, ("new",))
        results.append(wrapped.execute(profile.read_sql, ("new",)).fetchone())
        wrapped.execute(profile.insert_sql, ("new", "reinserted"))
        wrapped.commit()
        wrapped.close()
    session.close()
    document = session.document()
    assert results == [None, ("created",), None]
    assert not document["gaps"] and len(document["presenceFacts"]["writes"]) == 4
    with (folder / "confirmed-crud.trace.json").open("x", encoding="utf8") as stream:
        json.dump(document, stream, indent=2)
        stream.write("\n")
    return {"name": "actual-confirmed-commit-and-crud", "passed": True,
            "initializationAck": acknowledgement, "actualControlResults": setup.controls,
            "deliveredBusinessResults": results, "trace": "confirmed-crud.trace.json",
            "initialFacts": len(document["presenceFacts"]["initial"]),
            "readFacts": len(document["presenceFacts"]["reads"]), "writeFacts": 4,
            "databaseState": state(raw, profile)}


def rollback_tag(raw, schema):
    profile = profile_table(raw, schema, "rollback_tag")
    setup = Setup(raw, "rollback-tag")
    session = PresenceCapture(profile, keys=("a", "new"), exclusive_writers=True)
    try:
        session.initialize(setup)
    except ProvenanceError:
        pass
    else:
        raise AssertionError("Real ROLLBACK result was accepted as COMMIT confirmation")
    locked = assert_locked(session, setup)
    after = state(raw, profile)
    assert session._initialization_ack["commandTag"] == "ROLLBACK"
    assert session._initialization_ack["actualCommitConfirmed"] is False
    assert after["versionColumns"] == 0 and not any(after["ownedTables"].values())
    assert after["businessRows"] == [("a", "original")]
    session.close()
    return {"name": "injected-precommit-error-actual-rollback-tag", "passed": True,
            "faultInjection": "Real SELECT 1/0 before actual COMMIT; actual server result is ROLLBACK",
            "initializationAck": session._initialization_ack, "actualControlResults": setup.controls,
            "databaseState": after, **locked}


def discard_ack(raw, schema):
    profile = profile_table(raw, schema, "discarded_ack")
    setup = Setup(raw, "discard-ack")
    session = PresenceCapture(profile, keys=("a", "new"), exclusive_writers=True)
    try:
        session.initialize(setup)
    except psycopg.OperationalError as error:
        assert error is setup.original_error
    else:
        raise AssertionError("Discarded acknowledgement unexpectedly enabled initialization")
    assert int(raw.info.transaction_status) == 0
    locked = assert_locked(session, setup)
    after = state(raw, profile)
    assert after["versionColumns"] == 1 and all(after["ownedTables"].values())
    assert session._initialization_ack is None
    session.close()
    return {"name": "actual-commit-then-injected-discarded-response", "passed": True,
            "faultInjection": "Proxy throws after real COMMIT; not a real network disconnection",
            "actualControlResults": setup.controls, "databaseState": after,
            "originalErrorIdentityPreserved": True, "idleRollbackDidNotHealUnknown": True,
            **locked}


def catalog_failure(raw, schema):
    profile = profile_table(raw, schema, "catalog_failure")
    setup = Setup(raw)
    session = PresenceCapture(profile, keys=("a", "new"), exclusive_writers=True)
    original = ProvenanceError("injected rejection after actual catalog verification")
    def reject(connection, installation):
        verify_presence_installation(connection, installation)
        raise original
    with patch("presence_profile.verify_presence_installation", side_effect=reject):
        try:
            session.initialize(setup)
        except ProvenanceError as error:
            assert error is original
        else:
            raise AssertionError("Injected owned catalog rejection was ignored")
    locked = assert_locked(session, setup)
    after = state(raw, profile)
    assert after["versionColumns"] == 0 and not any(after["ownedTables"].values())
    assert not setup.controls
    session.close()
    return {"name": "injected-rejection-after-real-catalog-verification", "passed": True,
            "faultInjection": "Actual DDL/catalog run, then explicit validator rejection",
            "originalErrorIdentityPreserved": True, "databaseState": after, **locked}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    controlled_schema(args.schema)
    args.output.mkdir(parents=True, exist_ok=False)
    connect = connection_factory(psycopg)
    if connect is None:
        raise ValueError("An owned controlled database must be configured")
    implementation_before = implementation_bindings()
    fixture_before = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    package_version = json.loads((Path(__file__).resolve().parents[2] / "package.json").read_text(encoding="utf8"))["version"]
    receipt = {"schema": 1, "passed": False, "actualDatabaseExecution": False,
               "packageVersion": package_version, "analysisRuntimeVersion": None,
               "analyzerExecuted": False, "releaseAcceptance": False,
               "coreProofImplemented": False, "sourceClosureVerified": False,
               "formalPerformanceMeasured": False, "cases": []}
    try:
        with connect(autocommit=True) as raw:
            receipt["actualDatabaseExecution"] = True
            receipt["serverVersion"] = raw.info.server_version
            assert 180000 <= raw.info.server_version < 190000 and psycopg.__version__ == "3.3.6"
            receipt.update(driver=psycopg.__version__, python=platform.python_version())
            raw.execute("CREATE SCHEMA " + identifier(args.schema))
            try:
                receipt["cases"].append(positive(connect, raw, args.schema, args.output))
                receipt["cases"].append(rollback_tag(raw, args.schema))
                receipt["cases"].append(discard_ack(raw, args.schema))
                receipt["cases"].append(catalog_failure(raw, args.schema))
            finally:
                raw.execute("DROP SCHEMA " + identifier(args.schema) + " CASCADE")
        receipt["passed"] = True
    except BaseException as error:
        receipt["failure"] = {"class": type(error).__name__, "sqlstate": getattr(error, "sqlstate", None),
                              "assertion": str(error) if isinstance(error, AssertionError) else None,
                              "frames": [{"file": Path(frame.filename).name, "line": frame.lineno,
                                          "function": frame.name} for frame in traceback.extract_tb(error.__traceback__)]}
    implementation_after = implementation_bindings()
    fixture_after = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    receipt["implementationSources"] = {"before": implementation_before, "after": implementation_after,
                                        "unchanged": implementation_before == implementation_after}
    receipt["fixtureSources"] = {"before": fixture_before, "after": fixture_after, "unchanged": fixture_before == fixture_after}
    if implementation_before != implementation_after or fixture_before != fixture_after:
        receipt["passed"] = False
        receipt["sourceBindingFailure"] = True
    with (args.output / "initialization-receipt.json").open("x", encoding="utf8") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"passed": receipt["passed"], "actualDatabaseExecution": receipt["actualDatabaseExecution"],
                      "initializationCases": len(receipt["cases"]), "releaseAcceptance": False}))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
