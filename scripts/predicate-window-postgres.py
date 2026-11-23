"""Collect configured range observations from an isolated PostgreSQL 18.6 server."""

import argparse
import json
import os
from pathlib import Path
import secrets
import sys

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "integrations/python"))
from moontxnwitness_capture.configured_predicate_window import ConfiguredPredicateWindow
from moontxnwitness_capture.configured_source_v2 import SourceInstallPolicy, install_configured_source_v2
from moontxnwitness_capture.configured_sql_v2 import (
    ColumnConfig, PrimaryKeyConfigV2, SQLCaptureConfigV2, TableConfigV2, TEXT_COMPARISON,
)
from moontxnwitness_capture.configured_window_v2 import SourceInputsV2


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def prepare(admin, control, output, connect):
    suffix = secrets.token_hex(5)
    owner, writer, schema = (name + suffix for name in ("range_owner_", "range_writer_", "range_app_"))
    password = secrets.token_hex(20)
    admin.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(owner)))
    admin.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(writer), sql.Literal(password)))
    admin.execute(sql.SQL("GRANT CREATE ON DATABASE {} TO {}").format(
        sql.Identifier(admin.info.dbname), sql.Identifier(owner)))
    admin.execute(sql.SQL("CREATE SCHEMA {} AUTHORIZATION {}").format(sql.Identifier(schema), sql.Identifier(owner)))
    control.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(owner)))
    target = sql.Identifier(schema, "bookings")
    control.execute(sql.SQL("CREATE TABLE {} (label text COLLATE pg_catalog.\"C\" NOT NULL, id bigint PRIMARY KEY)").format(target))
    control.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(sql.Identifier(schema), sql.Identifier(writer)))
    control.execute(sql.SQL("GRANT SELECT, INSERT ON {} TO {}").format(target, sql.Identifier(writer)))
    control.execute(sql.SQL("INSERT INTO {} (id, label) VALUES (-3, 'outside'), (0, 'initial'),"
                            " (10, 'upper'), (9223372036854775806, 'maximum')").format(target))
    config = SQLCaptureConfigV2(TableConfigV2(schema, "bookings", PrimaryKeyConfigV2("id", "int64"),
                                            (ColumnConfig("label", "text", TEXT_COMPARISON),)))
    policy = SourceInstallPolicy("mtw_source_range_" + suffix, (writer,))
    install_configured_source_v2(control, output / "source", config, policy, opt_in=True)
    installed = SourceInputsV2.from_directory(output / "source")
    write(output / "config.json", config.to_dict())
    write(output / "policy.json", policy.to_dict())

    def window(name):
        return ConfiguredPredicateWindow(output / name, config, control, policy, installed, opt_in=True)

    def client():
        return connect(user=writer, password=password)

    return target, window, client


def cases(control, target, window, client):
    records = []
    bounded = window("bounded")
    reader = bounded.begin(client())
    require(reader.select_range(0, 10) == [{"id": 0, "label": "initial"}], "Half-open SQL result changed")
    require(reader.select_range(4, 9) == [], "Expected an empty native range read")
    writer = bounded.begin(client(), isolation="serializable")
    row = {"id": 5, "label": "committed"}
    require(writer.insert(row) == row, "Original SQL insert result differs")
    require(writer.select_range(0, 10) == [{"id": 0, "label": "initial"}, row], "Read-your-writes differs")
    writer.commit()
    require(reader.select_range(0, 10) == [{"id": 0, "label": "initial"}], "Repeatable Read snapshot changed")
    reader.commit()
    follower = bounded.begin(client(), isolation="serializable")
    require(follower.select_range(0, 10) == [{"id": 0, "label": "initial"}, row], "New snapshot misses commit")
    require(follower.select_range(9223372036854775805, 9223372036854775807)
            == [{"id": 9223372036854775806, "label": "maximum"}], "Int64 range lost exactness")
    follower.commit()
    records.append({"case": "bounded", "file": bounded.seal().relative_to(bounded.output.parent).as_posix(),
                    "status": "admitted", "reads": 6})

    missing = window("unobserved")
    reader = missing.begin(client())
    require(reader.select_range(30, 40) == [], "Unexpected row before out-of-scope operation")
    reader.commit()
    with client() as unobserved:
        unobserved.execute(sql.SQL("INSERT INTO {} (id, label) VALUES (31, 'unobserved')").format(target))
    records.append({"case": "unobserved", "file": missing.seal().relative_to(missing.output.parent).as_posix(),
                    "status": "unknown", "reason": "predicate-unobserved-write"})

    rolled_back = window("rolled-back")
    tx = rolled_back.begin(client())
    tx.insert({"id": 41, "label": "rolled back"})
    require(tx.select_range(40, 50) == [{"id": 41, "label": "rolled back"}], "Own insert observation differs")
    tx.rollback()
    require(control.execute(sql.SQL("SELECT id FROM {} WHERE id=41").format(target)).fetchone() is None,
            "Original rollback did not remove the inserted row")
    records.append({"case": "rolled-back", "file": rolled_back.seal().relative_to(rolled_back.output.parent).as_posix(),
                    "status": "unknown", "reason": "predicate-transaction-outcome"})
    return records


def reservation_case(name, control, target, window, client):
    capture = window("capture")
    lower, upper = 100, 110
    isolation = "repeatable read" if name == "before" else "serializable"
    aborted = []
    if name == "before":
        for _ in range(3):
            unrelated = capture.begin(client(), isolation=isolation)
            require(unrelated.select_range(800, 810) == [], "Unrelated native range returned a row")
            unrelated.commit()
    first = capture.begin(client(), isolation=isolation)
    require(first.select_range(lower, upper) == [], "The reservation interval must start empty")
    if name == "ordered":
        first.insert({"id": 101, "label": "first"})
        first.commit()
        second = capture.begin(client(), isolation=isolation)
        require(second.select_range(lower, upper) == [{"id": 101, "label": "first"}],
                "Ordered second transaction did not observe the existing reservation")
        second.commit()
    else:
        second = capture.begin(client(), isolation=isolation)
        require(second.select_range(lower, upper) == [], "Second transaction missed the concurrent empty observation")
        first.insert({"id": 101, "label": "first"})
        second.insert({"id": 102, "label": "second"})
        for participant in (first, second):
            try:
                participant.commit()
            except psycopg.errors.SerializationFailure as error:
                require(name == "retry" and error.sqlstate == "40001", "Unexpected native serialization failure")
                aborted.append(participant.id)
        if name == "retry":
            require(len(aborted) == 1, "A concurrent Serializable attempt must actually fail with 40001")
            retry = capture.begin(client(), isolation=isolation)
            require(len(retry.select_range(lower, upper)) == 1, "Fresh retry must see one committed reservation")
            retry.commit()
    bundle = capture.seal()
    final = control.execute(sql.SQL("SELECT id FROM {} WHERE id >= %s AND id < %s ORDER BY id").format(target),
                            (lower, upper)).fetchall()
    observed = [row[0] for row in final]
    require(len(observed) == (2 if name == "before" else 1), "Actual reservation constraint outcome changed")
    return {"name": name, "path": bundle.relative_to(capture.output.parent).as_posix(),
            "businessRows": observed, "rollbackSqlstate": "40001" if aborted else None,
            "abortedTransactions": aborted}


def reservation_campaign(open_connection, root):
    rounds = []
    for number in range(1, 6):
        runs = []
        for name in ("before", "ordered", "retry"):
            folder = root / f"round-{number}" / name
            folder.mkdir(parents=True)
            with open_connection() as admin, open_connection() as control:
                target, window, client = prepare(admin, control, folder, open_connection)
                result = reservation_case(name, control, target, window, client)
            runs.append({**result, "directory": folder.relative_to(root).as_posix()})
        rounds.append({"round": number, "cases": runs})
    return rounds


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--output", type=Path, required=True)
    cli.add_argument("--dsn-env", required=True)
    cli.add_argument("--owned-database", action="store_true")
    cli.add_argument("--reservation-campaign", action="store_true")
    args = cli.parse_args()
    if not args.owned_database or not os.environ.get(args.dsn_env):
        cli.error("Set the DSN environment variable for an owned disposable server")
    options = conninfo_to_dict(os.environ[args.dsn_env])

    def connect(**values):
        return psycopg.connect(**{**options, **values, "autocommit": True})

    args.output.mkdir(parents=True)
    with connect() as admin, connect() as control:
        require(psycopg.__version__ == "3.3.6" and admin.info.server_version == 180006,
                "Expected PostgreSQL 18.6 and psycopg 3.3.6")
        if not args.reservation_campaign:
            target, window, client = prepare(admin, control, args.output, connect)
            records = cases(control, target, window, client)
    observed = {"rounds": reservation_campaign(connect, args.output)} if args.reservation_campaign else {"cases": records}
    write(args.output / "receipt.json", {"passed": True, "actualDatabaseExecution": True,
                                        "postgres": "18.6", **observed})


if __name__ == "__main__":
    main()
