"""Capture actual SQLite serial transactions as versioned-register history.

This is a baseline integration, not an anomalous SQLite workload. It uses only
Python's standard library. Returned versions come from actual SELECT statements.
"""
import json
import sqlite3
import sys
import time
from pathlib import Path


def capture():
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE kv (key TEXT PRIMARY KEY, version TEXT NOT NULL)")
    initial = {"x": "x0", "y": "y0"}
    connection.executemany("INSERT INTO kv VALUES (?, ?)", initial.items())
    connection.commit()
    origin = time.monotonic_ns()
    transactions = []
    orders = {key: [version] for key, version in initial.items()}

    def transaction(tx_id, commands):
        start = (time.monotonic_ns() - origin) // 1000
        operations = []
        final_writes = {}
        connection.execute("BEGIN IMMEDIATE")
        try:
            for command in commands:
                kind, key, *value = command
                if kind == "read":
                    version = connection.execute("SELECT version FROM kv WHERE key = ?", (key,)).fetchone()[0]
                else:
                    version = value[0]
                    connection.execute("UPDATE kv SET version = ? WHERE key = ?", (version, key))
                    final_writes[key] = version
                operations.append({"type": kind, "key": key, "version": version})
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        end = (time.monotonic_ns() - origin) // 1000
        transactions.append({"id": tx_id, "status": "committed", "start": start, "end": end, "ops": operations})
        for key, version in final_writes.items():
            orders[key].append(version)

    transaction("sql-T1", [("read", "x"), ("write", "y", "y1")])
    transaction("sql-T2", [("read", "y"), ("write", "x", "x1")])
    transaction("sql-T3", [("read", "x"), ("read", "y"), ("write", "y", "y2")])
    final = dict(connection.execute("SELECT key, version FROM kv"))
    assert final == {"x": "x1", "y": "y2"}
    connection.close()
    return {"schemaVersion": 1, "name": "Actual SQLite sequential baseline", "model": "strict-serializable", "initial": initial, "versionOrders": orders, "transactions": transactions}


if __name__ == "__main__":
    result = json.dumps(capture(), ensure_ascii=False, indent=2) + "\n"
    if len(sys.argv) == 2:
        with Path(sys.argv[1]).open("x", encoding="utf-8") as output:
            output.write(result)
    else:
        print(result, end="")
