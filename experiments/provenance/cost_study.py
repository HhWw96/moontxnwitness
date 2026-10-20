"""Controlled plain/column/sidecar provenance path study, never full capture C/A.

Do not run alongside another benchmark. This script creates a new explicitly
named fixture schema and compares every candidate, preserving all raw samples.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import random
import statistics
import time
import traceback
from pathlib import Path

from prototype import controlled_schema, identifier, install, qualified, uninstall, verify_audit


MODES = ("plain", "column", "sidecar")
GENERATOR = "python-random-choices-point-v1"


def workloads(seed, count, keys, missing_keys=8):
    randomizer = random.Random(seed)
    return [{"read": "key-" + str(randomizer.randrange(keys)),
             "otherRead": "key-" + str(randomizer.randrange(keys)),
             "missingRead": "missing-" + str(randomizer.randrange(missing_keys)),
             "delta": randomizer.choice((-3, -1, 1, 3))} for _ in range(count)]


def oracle(operations, initial):
    values = dict(initial)
    for operation in operations:
        values[operation["read"]] += operation["delta"]
    return values


def nearest_rank(samples, fraction):
    if not samples or not 0 < fraction <= 1:
        raise ValueError("Provide samples and a fraction in (0,1]")
    return sorted(samples)[max(0, math.ceil(len(samples) * fraction) - 1)]


def canonical_hash(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def batch_orders():
    # Latin rotation: each candidate occupies each execution position once.
    return [list(MODES[offset:] + MODES[:offset]) for offset in range(3)]


def summarize(samples):
    summaries = {}
    for mode in MODES:
        matching = [sample for sample in samples if sample["mode"] == mode and sample["status"] == "passed"]
        if len(matching) != 3:
            raise ValueError("Do not summarize an incomplete set of three batches")
        delays = [delay for sample in matching for delay in sample["transactionLatencyNs"]]
        total_count = sum(sample["transactions"] for sample in matching)
        total_wall = sum(sample["measurementWallNs"] for sample in matching)
        summaries[mode] = {"batches": 3, "transactions": total_count,
                           "aggregateTps": total_count * 1_000_000_000 / total_wall,
                           "p50TxnNs": statistics.median(delays),
                           "p95TxnNs": nearest_rank(delays, 0.95),
                           "walLsnDeltaBytes": sum(sample["walLsnDeltaBytes"] for sample in matching)}
    ratios = {}
    for mode in ("column", "sidecar"):
        pairs = []
        for batch in range(3):
            plain = next(sample for sample in samples if sample["batch"] == batch and sample["mode"] == "plain")
            candidate = next(sample for sample in samples if sample["batch"] == batch and sample["mode"] == mode)
            pairs.append({"batch": batch, "tpsRatio": candidate["tps"] / plain["tps"],
                          "p50Ratio": candidate["p50TxnNs"] / plain["p50TxnNs"],
                          "p95Ratio": candidate["p95TxnNs"] / plain["p95TxnNs"],
                          "walRatio": (candidate["walLsnDeltaBytes"] / plain["walLsnDeltaBytes"])
                          if plain["walLsnDeltaBytes"] else None})
        ratios[mode] = {"pairedBatches": pairs,
                       "tpsRatioGeomean": math.exp(sum(math.log(pair["tpsRatio"]) for pair in pairs) / 3),
                       "p95RatioGeomean": math.exp(sum(math.log(pair["p95Ratio"]) for pair in pairs) / 3)}
    return {"modes": summaries, "candidateOverPlain": ratios,
            "interpretation": "B/A provenance SQL paths only; tpsRatio<1 and latencyRatio>1 are regressions; no samples omitted"}


def connect_factory(psycopg):
    defaults = {"connect_timeout": 5, "options": "-c statement_timeout=15000 -c lock_timeout=5000"}
    if os.environ.get("MTW_PG_CONNECTION_FILE"):
        config = json.loads(Path(os.environ["MTW_PG_CONNECTION_FILE"]).read_text(encoding="utf-8"))
        return lambda **extra: psycopg.connect(**(defaults | config | extra))
    if os.environ.get("MTW_PG_DSN"):
        return lambda **extra: psycopg.connect(os.environ["MTW_PG_DSN"], **(defaults | extra))
    return None


def run_operations(connection, target, provenance, operations, expected, *, measure):
    """One connection, three point reads + one point update + commit per tx."""
    latencies = []
    point_read = "SELECT value FROM " + target + " WHERE id=%s"
    write = "UPDATE " + target + " SET value=%s WHERE id=%s"
    started = time.perf_counter_ns()
    try:
        for operation in operations:
            transaction_start = time.perf_counter_ns()
            key, other, missing = operation["read"], operation["otherRead"], operation["missingRead"]
            if provenance is None:
                value = connection.execute(point_read, (key,)).fetchone()
                other_value = connection.execute(point_read, (other,)).fetchone()
                missing_value = connection.execute(point_read, (missing,)).fetchone()
                if value != (expected[key],) or other_value != (expected[other],) or missing_value is not None:
                    raise AssertionError("Plain point reads disagree with the frozen workload oracle")
                next_value = value[0] + operation["delta"]
            else:
                value = provenance.observe(connection, key)
                other_value = provenance.observe(connection, other)
                missing_value = provenance.observe(connection, missing)
                if (not value.exists or value.value != expected[key] or not other_value.exists
                        or other_value.value != expected[other] or missing_value.exists):
                    raise AssertionError("Provenance point reads disagree with the frozen workload oracle")
                next_value = value.value + operation["delta"]
            result = connection.execute(write, (next_value, key))
            if result.rowcount != 1:
                raise AssertionError("Point update affected an unexpected row count")
            connection.commit()
            elapsed = time.perf_counter_ns() - transaction_start
            expected[key] = next_value
            if measure:
                latencies.append(elapsed)
        return latencies, time.perf_counter_ns() - started
    except BaseException as error:
        # Preserve valid completed samples and the original business exception.
        try:
            error.provenance_partial_latencies = list(latencies)
        except Exception:
            pass
        try:
            connection.rollback()
        except Exception:
            pass
        raise


def run_sample(connect, setup, *, schema, mode, batch, operations, warmup, keys, output):
    table = "study_" + str(batch) + "_" + mode
    target = qualified(schema, table)
    receipt = {"batch": batch, "mode": mode, "status": "started",
               "transactions": len(operations), "warmupTransactions": len(warmup),
               "workloadSha256": canonical_hash(operations), "transactionLatencyNs": []}
    destination = output / ("batch-" + str(batch) + "-" + mode + ".json")
    provenance = None
    try:
        setup.execute("CREATE TABLE " + target + " (id text PRIMARY KEY,value integer NOT NULL)")
        initial = {"key-" + str(index): 100_000 for index in range(keys)}
        with setup.cursor() as cursor:
            cursor.executemany("INSERT INTO " + target + " VALUES(%s,%s)", list(initial.items()))
        if mode != "plain":
            begin_install = time.perf_counter_ns()
            provenance = install(setup, schema=schema, table=table, mode=mode,
                                 missing_keys=tuple("missing-" + str(index) for index in range(8)))
            receipt["installSmokeNs"] = time.perf_counter_ns() - begin_install
        expected = dict(initial)
        with connect() as connection:
            run_operations(connection, target, provenance, warmup, expected, measure=False)
            before_lsn = setup.execute("SELECT pg_catalog.pg_current_wal_insert_lsn()::text").fetchone()[0]
            delays, wall_ns = run_operations(connection, target, provenance, operations, expected, measure=True)
            receipt.update({"transactionLatencyNs": delays, "measurementWallNs": wall_ns})
            after_lsn = setup.execute("SELECT pg_catalog.pg_current_wal_insert_lsn()::text").fetchone()[0]
            wal_delta = setup.execute(
                "SELECT pg_catalog.pg_wal_lsn_diff(%s::pg_catalog.pg_lsn,%s::pg_catalog.pg_lsn)",
                (after_lsn, before_lsn)).fetchone()[0]
        final = dict(setup.execute("SELECT id,value FROM " + target + " ORDER BY id").fetchall())
        independent_final = oracle(operations, oracle(warmup, initial))
        if final != expected or final != independent_final:
            raise AssertionError("Final business values disagree with the independent workload oracle")
        if provenance is not None:
            receipt["sourceCheck"] = verify_audit(provenance.audit(setup))
        receipt.update({"status": "passed", "transactionLatencyNs": delays,
                        "measurementWallNs": wall_ns, "tps": len(delays) * 1_000_000_000 / wall_ns,
                        "p50TxnNs": statistics.median(delays), "p95TxnNs": nearest_rank(delays, 0.95),
                        "walStartLsn": before_lsn, "walEndLsn": after_lsn,
                        "walLsnDeltaBytes": int(wal_delta), "finalBusinessValues": final,
                        "finalBusinessSha256": canonical_hash(final), "businessValuesVerified": True})
        if provenance is not None:
            begin_uninstall = time.perf_counter_ns()
            uninstall(setup, provenance)
            receipt["uninstallSmokeNs"] = time.perf_counter_ns() - begin_uninstall
        after_uninstall = dict(setup.execute("SELECT id,value FROM " + target).fetchall())
        if after_uninstall != final:
            raise AssertionError("Uninstall changed business values")
        setup.execute("DROP TABLE " + target)
        return receipt
    except BaseException as error:
        receipt.update({"status": "failed", "errorClass": type(error).__name__,
                        "sqlstate": getattr(error, "sqlstate", None),
                        "transactionLatencyNs": getattr(error, "provenance_partial_latencies", receipt["transactionLatencyNs"]),
                        "frames": [{"file": Path(frame.filename).name, "line": frame.lineno, "function": frame.name}
                                   for frame in traceback.extract_tb(error.__traceback__)]})
        raise
    finally:
        destination.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", required=True, help="new controlled mtw_provenance_* schema")
    parser.add_argument("--output", required=True, help="new directory, never overwritten")
    parser.add_argument("--quick", action="store_true", help="smoke only, never formal acceptance")
    parser.add_argument("--transactions", type=int)
    parser.add_argument("--warmup", type=int)
    parser.add_argument("--keys", type=int, default=32)
    parser.add_argument("--seed", type=int, default=20261020)
    parser.add_argument("--exclusive-cluster", action="store_true",
                        help="assert no other workload uses the dedicated cluster; required for attributing WAL delta")
    args = parser.parse_args()
    controlled_schema(args.schema)
    count = args.transactions if args.transactions is not None else 20 if args.quick else 1000
    warmup_count = args.warmup if args.warmup is not None else 3 if args.quick else 100
    if count < 1 or (not args.quick and count < 1000) or warmup_count < 0 or not 2 <= args.keys <= 1000:
        parser.error("formal runs require >=1000 tx/mode/batch; positive quick count; warmup>=0; keys=2..1000")
    try:
        import psycopg
    except ModuleNotFoundError:
        print(json.dumps({"status": "not-executed", "actualDatabaseExecution": False, "reason": "optional psycopg is missing"}))
        return 3
    connect = connect_factory(psycopg)
    if connect is None:
        print(json.dumps({"status": "not-executed", "actualDatabaseExecution": False, "reason": "no controlled database configured"}))
        return 3
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    workload_batches = [workloads(args.seed + batch, count, args.keys) for batch in range(3)]
    warmup_batches = [workloads(args.seed + 1_000_000 + batch, warmup_count, args.keys) for batch in range(3)]
    manifest = {"generator": GENERATOR, "seed": args.seed, "keys": args.keys,
                "transactionsPerModePerBatch": count, "warmupPerModePerBatch": warmup_count,
                "modeOrders": batch_orders(), "batches": workload_batches, "warmups": warmup_batches}
    (output / "workload.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    samples = []
    receipt = {"status": "started", "actualDatabaseExecution": False,
               "study": "provenance-single-statement-read-path-B-over-A-v1",
               "fullCaptureComparison": False, "quick": args.quick,
               "formalProtocolCompleted": False, "workloadSha256": canonical_hash(manifest),
               "studySourceSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "prototypeSourceSha256": hashlib.sha256(Path(__file__).with_name("prototype.py").read_bytes()).hexdigest(),
               "walAttribution": "dedicated cluster asserted" if args.exclusive_cluster else "unverified shared cluster counter",
               "walCounter": "pg_current_wal_insert_lsn position difference; includes WAL padding/background activity",
               "unmeasured": ["CPU", "RSS", "lock wait duration", "deadlock rate under contention",
                              "application integration cost", "retention/vacuum cost", "full capture C/A"]}
    try:
        with connect(autocommit=True) as setup:
            receipt.update({"server": setup.execute("SELECT version()").fetchone()[0],
                            "driver": psycopg.__version__, "python": platform.python_version(),
                            "platform": platform.platform(), "actualDatabaseExecution": True,
                            "databaseSettings": dict(setup.execute(
                                "SELECT name,setting FROM pg_catalog.pg_settings WHERE name IN "
                                "('synchronous_commit','fsync','full_page_writes','shared_buffers','max_connections')"
                            ).fetchall())})
            if not 180000 <= setup.info.server_version < 190000:
                raise ValueError("This controlled study targets PostgreSQL 18")
            setup.execute("CREATE SCHEMA " + identifier(args.schema))
            try:
                for batch, order in enumerate(batch_orders()):
                    for mode in order:
                        samples.append(run_sample(connect, setup, schema=args.schema, mode=mode, batch=batch,
                                                  operations=workload_batches[batch], warmup=warmup_batches[batch],
                                                  keys=args.keys, output=output))
            finally:
                # Only the new schema successfully created by this invocation.
                setup.execute("DROP SCHEMA " + identifier(args.schema) + " CASCADE")
        receipt.update({"status": "smoke-passed" if args.quick else "passed",
                        "formalProtocolCompleted": not args.quick and args.exclusive_cluster,
                        "samples": [{key: value for key, value in sample.items() if key != "transactionLatencyNs"}
                                    for sample in samples], "summary": summarize(samples),
                        "scope": "one serial client; identical generated data, operations and transaction count; full raw latency arrays retained"})
        return_code = 0
    except BaseException as error:
        receipt.update({"status": "failed", "formalProtocolCompleted": False, "errorClass": type(error).__name__,
                        "sqlstate": getattr(error, "sqlstate", None),
                        "completedSamples": len(samples), "allSamplesRetained": True,
                        "frames": [{"file": Path(frame.filename).name, "line": frame.lineno, "function": frame.name}
                                   for frame in traceback.extract_tb(error.__traceback__)]})
        return_code = 1
    (output / "study.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "actualDatabaseExecution": receipt["actualDatabaseExecution"],
                      "formalProtocolCompleted": receipt["formalProtocolCompleted"], "fullCaptureComparison": False,
                      "completedSamples": len(samples)}))
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
