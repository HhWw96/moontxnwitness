"""Exact SQL/source registry for the frozen dislock component, not a parser.

Only RETURNING/SELECT projections are extended. WHERE, ON CONFLICT, NOW(),
interval multiplication, parameter order and business prefix are unchanged.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "integrations/python"))
from moontxnwitness_capture.capture_v3 import SQLMapping
from business import COMMIT, load_upstream

PROFILE = "dislock-f9946f0-v3/1"


def identifier(value):
    if not isinstance(value, str) or not value or "\x00" in value or len(value.encode("utf-8")) > 63:
        raise ValueError("Invalid PostgreSQL identifier")
    return '"' + value.replace('"', '""') + '"'


def registry(schema, table="key_value", version_column="_mtw_v3_version",
             predecessor_function="_mtw_v3_predecessor"):
    upstream = load_upstream()
    token = identifier(version_column)
    helper = identifier(schema) + "." + identifier(predecessor_function)
    common = ("OLD." + token + "::text,NEW." + token
              + "::text,OLD.value,OLD.expire_at,NOW()")
    definitions = []
    for short, function, marker, business, columns in (
        ("acquire-schedule", upstream.queries.acquire_lock_query, "RETURNING key, expire_at;", 2,
         ["key", "newExpire", "oldToken", "newToken", "oldOwner", "oldExpire", "serverNow", "actualPredecessor", "action"]),
        ("acquire-run", upstream.queries.acquire_run_lock_query, "RETURNING key, expire_at;", 2,
         ["key", "newExpire", "oldToken", "newToken", "oldOwner", "oldExpire", "serverNow", "actualPredecessor", "action"]),
        ("read-current", upstream.queries.read_current_query, "SELECT expire_at, value", 2,
         ["expireAt", "owner", "token"]),
        ("renew", upstream.queries.renew_lease_query, "RETURNING expire_at;", 1,
         ["newExpire", "oldToken", "newToken", "oldOwner", "oldExpire", "serverNow"]),
        ("expire", upstream.queries.expire_lock_query, "RETURNING key;", 1,
         ["key", "oldToken", "newToken", "oldOwner", "oldExpire", "serverNow"]),
    ):
        original = function([schema, table]).as_string(None)
        if original.count(marker) != 1:
            raise ValueError("Pinned upstream projection changed")
        if short.startswith("acquire-"):
            replacement = ("RETURNING key, expire_at," + common + "," + helper
                           + "(NEW." + token + "::text),CASE WHEN OLD.key IS NULL THEN 'INSERT' ELSE 'UPDATE' END;")
        elif short == "read-current":
            replacement = marker + "," + token + "::text"
        elif short == "renew":
            replacement = "RETURNING expire_at," + common + ";"
        else:
            replacement = "RETURNING key," + common + ";"
        definitions.append({"mappingId": "dislock." + short + "/1", "originalSql": original,
            "executedSql": original.replace(marker, replacement, 1), "businessColumns": business,
            "serverColumns": columns})
    definitions.append({"mappingId": "dislock.server-now/1", "originalSql": "SELECT NOW();",
        "executedSql": "SELECT NOW();", "businessColumns": 1, "serverColumns": ["serverNow"]})
    return {"profile": PROFILE, "upstreamCommit": COMMIT, "schema": schema, "table": table,
        "versionColumn": version_column, "predecessorFunction": predecessor_function,
        "timestampEncoding": {"captureType": "datetime", "value": "actual aware datetime str, microseconds and offset retained"},
        "templates": definitions}


def mappings(manifest):
    result = []
    for entry in manifest["templates"]:
        short = entry["mappingId"].split(".", 1)[1].split("/", 1)[0]
        def bind(params, short=short):
            if short == "server-now":
                return {}
            if not isinstance(params, (tuple, list)):
                raise ValueError("Frozen dislock positional parameters required")
            key_index = 1 if short == "renew" else 0
            if not isinstance(params[key_index], str) or len(params[key_index].encode("utf-8")) > 512:
                raise ValueError("Bounded text lease key required")
            bound = {"key": params[key_index]}
            if short != "read-current":
                bound["owner"] = params[2 if short == "renew" else 1]
            return bound
        def on_rows(cursor, rows, exhausted, short=short):
            if short == "server-now":
                return
            bound = cursor._bound
            key = bound.get("key")
            if not key:
                raise ValueError("Missing fixed-profile key binding")
            if len(rows) > 1:
                raise ValueError("Point SQL returned multiple rows")
            for index, row in enumerate(rows):
                index += cursor._batch_start
                if short == "read-current":
                    cursor.fact("read", key=key, version=row[2], evidence={"serverRow": index})
                    continue
                upsert = short.startswith("acquire-")
                old_token, new_token = row[2:4] if upsert else row[1:3]
                old_owner, old_expire, now = row[4:7] if upsert else row[3:6]
                predecessor, action = (row[7], row[8]) if upsert else (old_token, "UPDATE")
                cursor.fact("write", key=key, version=new_token, predecessor=predecessor,
                    evidence={"serverRow": index, "action": action})
                # INSERT has no row-level conflict guard to assert. Its absence
                # predecessor must be established by the installation proof.
                if not upsert or action == "UPDATE":
                    cursor.fact("condition", predicate="lease-expired" if upsert else "owner-equals",
                        matched=True, sourceVersion=old_token, evidence={"serverRow": index,
                        "key": key, "owner": bound.get("owner"), "oldOwner": old_owner,
                        "oldExpireAt": old_expire, "serverNow": now, "oldToken": old_token,
                        "newToken": new_token, "action": action})
            if exhausted and cursor._server_rows_seen == 0:
                cursor.fact("condition", predicate="row-exists" if short == "read-current" else
                    "lease-expired" if short.startswith("acquire-") else "owner-equals",
                    matched=False, evidence={"key": key, "owner": bound.get("owner"),
                                            "sourceUnavailable": True})
        result.append(SQLMapping(entry["originalSql"], entry["mappingId"], entry["executedSql"],
                                 entry["businessColumns"], on_rows, bind))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", default="__SCHEMA__")
    parser.add_argument("--table", default="__TABLE__")
    parser.add_argument("--version-column", default="__VERSION_COLUMN__")
    parser.add_argument("--predecessor-function", default="__PREDECESSOR_FUNCTION__")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    text = json.dumps(registry(args.schema, args.table, args.version_column,
                               args.predecessor_function), indent=2, ensure_ascii=False) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8", newline="\n") as target:
            target.write(text)
    else:
        print(text, end="")
