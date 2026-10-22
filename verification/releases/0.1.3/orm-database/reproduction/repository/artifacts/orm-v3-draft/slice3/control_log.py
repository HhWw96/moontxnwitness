"""Only controlled synchronous setup SQL, never original business cursors."""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
import math
import uuid
from psycopg.types.json import Jsonb
from source_sink import _Encoder
from moontxnwitness_capture.capture import _Budget


class ControlCoverageError(ValueError): pass


class _ControlParameterEncoder(_Encoder):
    """Narrow typed observation; never replace objects passed to psycopg."""
    def _pure_json(self, value, budget, depth):
        if depth > 8:
            raise ValueError("Control JSON nesting budget")
        kind = type(value)
        if kind in (type(None), bool, str, int, float):
            if kind is int and not -9_007_199_254_740_991 <= value <= 9_007_199_254_740_991:
                raise ValueError("Control JSON integer is outside exact JSON range")
            if kind is float and not math.isfinite(value):
                raise ValueError("Control JSON non-finite number")
            return super()._value(value, budget, depth)
        budget.charge(nodes=1)
        if kind is list:
            budget.charge(2 + max(0, len(value) - 1))
            return [self._pure_json(item, budget, depth + 1) for item in value]
        if kind is dict:
            budget.charge(2 + max(0, len(value) - 1))
            result = {}
            for key, item in value.items():
                if type(key) is not str:
                    raise ValueError("Control JSON object keys must be plain strings")
                budget.charge(1, nodes=1); budget.text(key)
                result[key] = self._pure_json(item, budget, depth + 1)
            return result
        raise ValueError("Control Jsonb contains a non-JSON value")

    def _value(self, value, budget, depth=0):
        if type(value) is Jsonb:
            if value.dumps is not json.dumps:
                raise ValueError("Only explicit stdlib json.dumps is observed")
            result = super()._value({"captureType": "psycopg-jsonb", "objectDumps": "stdlib-json-dumps"}, budget, depth)
            # Charge the third field before copying the bounded pure JSON tree.
            budget.charge(2, nodes=1); budget.text("value")
            result["value"] = self._pure_json(value.obj, budget, depth + 1)
            return result
        return super()._value(value, budget, depth)


class ControlCursor:
    def __init__(self, raw, rows, seq):
        self.raw, self.rows, self.position, self.control_query_seq = raw, rows, 0, seq
    def fetchone(self):
        if self.raw.description is None: return self.raw.fetchone()
        if self.position >= len(self.rows): return None
        value = self.rows[self.position]; self.position += 1; return value
    def fetchall(self):
        if self.raw.description is None: return self.raw.fetchall()
        value = self.rows[self.position:]; self.position = len(self.rows); return value
    def __getattr__(self, name): return getattr(self.raw, name)


class ControlConnection:
    def __init__(self, raw, sink):
        self.raw, self.sink = raw, sink
        self.connection = "setup-" + uuid.uuid4().hex
        self.transaction, self.transaction_number = None, 0
        self.query_sequences, self.gaps, self.last_query_seq = [], [], None

    def __getattr__(self, name): return getattr(self.raw, name)

    def _gap(self, code, message, sql):
        gap = {"code": code, "message": message, "sqlSha256": hashlib.sha256(sql.encode()).hexdigest()}
        if len(self.gaps) < 64: self.gaps.append(gap)
        try: self.sink.append({"kind": "source-gap", "controlConnection": self.connection, **gap})
        except BaseException: self.sink.failed = True

    def execute(self, query, parameters=None):
        actual_sql = query if isinstance(query, str) else query.as_string(self.raw)
        before = self.raw.info.transaction_status.name
        candidate = self.transaction
        if actual_sql == "BEGIN":
            self.transaction_number += 1
            candidate = self.connection + "-tx-" + str(self.transaction_number)
        identity = {"kind": "control-query", "connection": self.connection,
            "backendPid": self.raw.info.backend_pid, "transaction": candidate,
            "sql": actual_sql, "parameters": parameters, "transactionStatusBefore": before}
        try:
            cursor = self.raw.execute(query, parameters)
        except BaseException as error:
            record = {**identity, "transactionStatusAfter": self.raw.info.transaction_status.name,
                "error": {"class": type(error).__name__, "sqlstate": getattr(error, "sqlstate", None),
                    "diagnosticSqlstate": getattr(getattr(error, "diag", None), "sqlstate", None),
                    "hasServerResult": getattr(error, "pgresult", None) is not None}}
            try:
                record["parameters"] = _ControlParameterEncoder()._value(parameters, _Budget(4096, self.sink.max_record))
                self.sink.append(record)
            except ValueError:
                self._gap("control_query_source_unretained", "Actual failing control query parameters could not be retained completely.", actual_sql)
            except BaseException: self.sink.failed = True
            raise  # Original driver exception identity.
        result = cursor.pgresult
        if actual_sql == "BEGIN": self.transaction = candidate
        elif actual_sql in ("COMMIT", "ROLLBACK"): self.transaction = None
        try:
            if result is None or result.ntuples > 512 or result.nfields > 32:
                raise ControlCoverageError("Control result row/column budget")
            if result.ntuples * result.nfields > 512:
                raise ControlCoverageError("Control result combined raw/native node budget")
            raw_rows, raw_bytes = [], 0
            for row in range(result.ntuples):
                values = []
                for col in range(result.nfields):
                    value = result.get_value(row, col)
                    raw_bytes += 0 if value is None else len(value)
                    if raw_bytes > 32 * 1024:
                        raise ControlCoverageError("Control result aggregate raw byte budget")
                    values.append(value)
                raw_rows.append(values)
            rows = cursor.fetchall() if cursor.description is not None else []
            if len(rows) != result.ntuples:
                raise ControlCoverageError("Control native/raw result row count differs")
            record = {**identity, "transactionStatusAfter": self.raw.info.transaction_status.name,
                "result": {"status": int(result.status), "commandTag": cursor.statusmessage,
                    "rowcount": cursor.rowcount,
                    "columns": None if cursor.description is None else [{"name": c.name, "typeCode": c.type_code} for c in cursor.description],
                    "rows": rows, "complete": True,
                    "actualPGresult": {"status": int(result.status), "commandTag": result.command_status,
                        "commandTuples": result.command_tuples, "ntuples": result.ntuples, "nfields": result.nfields,
                        "fields": [{"oid": result.ftype(i), "format": result.fformat(i), "typmod": result.fmod(i)} for i in range(result.nfields)],
                        "rawRows": raw_rows}}}
            record["parameters"] = _ControlParameterEncoder()._value(parameters, _Budget(4096, self.sink.max_record))
            # Shared node/byte preview before retaining the record. On exhaustion
            # preserve a bounded gap rather than truncating a complete catalog.
            self.sink.preview(record)
            seq = self.sink.append(record)
        except BaseException as error:
            self._gap("control_query_source_unretained", "Actual control query result could not be retained completely (" + type(error).__name__ + ").", actual_sql)
            if isinstance(error, (ValueError, ControlCoverageError)):
                raise ControlCoverageError("Control source coverage failed; no truncated proof") from error
            raise
        self.query_sequences.append(seq); self.last_query_seq = seq
        return ControlCursor(cursor, deepcopy(rows), seq)

    def references_since(self, offset): return list(self.query_sequences[offset:])
