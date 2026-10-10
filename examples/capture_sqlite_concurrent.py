"""Actual two-connection WAL races, aborted snapshots and fresh retries.

Only completed SELECT/UPDATE operations are logged. Version order comes from an
audit table written in the same database transaction, never thread completion.
"""
import argparse
import json
import platform
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
from pathlib import Path


def capture(rounds=3):
    if not 1 <= rounds <= 10:
        raise ValueError("rounds must be 1..10")
    parent = Path(tempfile.gettempdir()).resolve()
    work = Path(tempfile.mkdtemp(prefix="moontxnwitness-sqlite-", dir=parent)).resolve()
    assert work.parent == parent and work.name.startswith("moontxnwitness-sqlite-")
    db = work / "race.sqlite"
    initial = {"x": "x0", "y": "y0"}
    setup = sqlite3.connect(db, isolation_level=None)
    mode = setup.execute("PRAGMA journal_mode=WAL").fetchone()[0]
    assert mode == "wal"
    setup.execute("CREATE TABLE kv (key TEXT PRIMARY KEY, version TEXT NOT NULL)")
    setup.executemany("INSERT INTO kv VALUES (?, ?)", initial.items())
    setup.execute("CREATE TABLE audit (seq INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT NOT NULL, version TEXT NOT NULL, tx TEXT NOT NULL)")
    setup.close()
    origin = time.monotonic_ns()
    transactions = []
    errors = []
    problems = []
    lock = threading.Lock()

    def attempt(tx_id, read_key, write_key, version, barrier=None):
        start = (time.monotonic_ns() - origin) // 1000
        connection = sqlite3.connect(db, timeout=0.2, isolation_level=None)
        ops = []
        status = "committed"
        error_name = None
        try:
            connection.execute("BEGIN DEFERRED")
            observed = connection.execute("SELECT version FROM kv WHERE key=?", (read_key,)).fetchone()[0]
            ops.append({"type": "read", "key": read_key, "version": observed})
            if barrier is not None:
                barrier.wait(timeout=5)
            changed = connection.execute("UPDATE kv SET version=? WHERE key=?", (version, write_key))
            assert changed.rowcount == 1
            ops.append({"type": "write", "key": write_key, "version": version})
            connection.execute("INSERT INTO audit (key, version, tx) VALUES (?, ?, ?)", (write_key, version, tx_id))
            connection.execute("COMMIT")
        except sqlite3.OperationalError as error:
            error_name = getattr(error, "sqlite_errorname", "")
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            if not (error_name.startswith("SQLITE_BUSY") or error_name.startswith("SQLITE_LOCKED")):
                raise
            status = "aborted"
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            end = (time.monotonic_ns() - origin) // 1000
            connection.close()
        result = {"id": tx_id, "status": status, "start": start, "end": end, "ops": ops}
        with lock:
            transactions.append(result)
            if error_name:
                errors.append({"transaction": tx_id, "sqliteError": error_name})
        return result

    try:
        for number in range(rounds):
            barrier = threading.Barrier(2)
            wave = []

            def worker(label, read_key, write_key):
                try:
                    result = attempt(f"r{number}-{label}", read_key, write_key, f"{write_key}:r{number}:{label}", barrier)
                    with lock:
                        wave.append((label, read_key, write_key, result))
                except BaseException as error:
                    with lock:
                        problems.append(repr(error))

            threads = [threading.Thread(target=worker, args=("A", "x", "y")), threading.Thread(target=worker, args=("B", "y", "x"))]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)
            assert all(not thread.is_alive() for thread in threads), "Capture thread did not complete"
            assert not problems, problems
            assert len(wave) == 2
            assert sum(item[3]["status"] == "committed" for item in wave) == 1, "Expected one successful writer in a shared-snapshot race"
            for label, read_key, write_key, result in wave:
                if result["status"] == "aborted":
                    retry = attempt(f"r{number}-{label}-retry", read_key, write_key, f"{write_key}:r{number}:{label}:retry")
                    assert retry["status"] == "committed"

        connection = sqlite3.connect(db)
        audit = connection.execute("SELECT key, version, tx FROM audit ORDER BY seq").fetchall()
        final = dict(connection.execute("SELECT key, version FROM kv"))
        connection.close()
        orders = {key: [version] for key, version in initial.items()}
        for key, version, _ in audit:
            orders[key].append(version)
        for key in initial:
            assert orders[key][-1] == final[key]
        committed_writes = {(op["key"], op["version"], tx["id"]) for tx in transactions if tx["status"] == "committed" for op in tx["ops"] if op["type"] == "write"}
        assert committed_writes == set(audit), "Audit and captured commits disagree"
        history = {"schemaVersion": 1, "name": "Actual concurrent SQLite WAL capture with aborted snapshots and retries", "model": "strict-serializable", "initial": initial, "versionOrders": orders, "transactions": transactions}
        metadata = {"actualDatabaseExecution": True, "sqliteVersion": sqlite3.sqlite_version, "pythonVersion": platform.python_version(), "journalMode": mode, "workers": 2, "rounds": rounds, "committed": sum(t["status"] == "committed" for t in transactions), "aborted": sum(t["status"] == "aborted" for t in transactions), "errors": errors, "versionOrderSource": "same-transaction SQLite audit sequence", "claim": "Observed history only; does not certify SQLite globally or reproduce an SQLite vulnerability"}
        return history, metadata
    finally:
        # Remove only the newly created task-owned directory after checking its
        # resolved absolute location. Never use a caller-provided database path.
        resolved = work.resolve()
        assert resolved.parent == parent and resolved.name.startswith("moontxnwitness-sqlite-")
        shutil.rmtree(resolved)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", nargs="?", default="-", help="New UTF-8 history file, or - for stdout")
    parser.add_argument("--rounds", type=int, default=3)
    args = parser.parse_args()
    history, metadata = capture(args.rounds)
    text = json.dumps(history, ensure_ascii=False, indent=2) + "\n"
    if args.output == "-":
        print(text, end="")
    else:
        with Path(args.output).open("x", encoding="utf-8") as output:
            output.write(text)
    print(json.dumps(metadata, ensure_ascii=False), file=sys.stderr)
