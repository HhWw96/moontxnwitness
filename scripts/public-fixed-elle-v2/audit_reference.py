#!/usr/bin/env python3
"""Read-only audit/export of the retained 2026-10-25 actual Elle campaign.

No SDK import, SDK verdict, checker execution, or old normalized reference is used.
The command requires exact original bytes and a fresh destination directory.
"""
from __future__ import annotations

import argparse
import collections
from dataclasses import dataclass
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import re
import zipfile

CONTRACT = "fixed-elle-serializable-original-capture-reference/v2"
AUDITOR = "original-capture-to-retained-elle-audit/v2"
REFERENCE_REVISION = "parser-boundary-hardening-r2"
PREVIOUS_REFERENCE_SHA = "bb5ac45ab5a24a3bd3c08e27b19b2883caabb06bd86f1bad97d8178e1742a0bb"
ELLE = "4e359e597c52938b0afebb8bc42273914d68a424"
JOB_SHA = "3b78df6d0eb7d74be56cd6946231d52778b3c0159ba40c9bb00a90ce3ac6b338"
INPUTS_SHA = "4b7ef85eb4a2f4a74020d6e6c65f5345f7c4c3b576afbe02b3f7a0cfc6033507"
ZIP_SHA = "9f7953e5715eb2813e8b4db7c59429a7d7f2880b3475a080634a0b0875dead91"
RUNTIME_ZIP_SHA = "2743c7e87adf2155fb20b737eada555ef3cd45f6e3f7ce956079175f979d3731"
RUNTIME_MANIFEST_SHA = "921768885e9203bbc39324f752b644e01fa2b19f701ebe5fe5e2714ebbaf036a"
MISSING_V1_SHA = "cd03c00a5c14c8ede612fdc1e15c40d35e0229c980ba2d08c651a15b7f2dc860"
CAMPAIGN_SHA = "24ebfd4e0a483ec06b0fcd29273a39456be0da40058f953ae48a9e2ba2cfebcb"
PREFIX = "mtw-elle-v028-campaign-first/"
RUNTIME_ZIP_MEMBER = "mtw-elle-v028-campaign-runtime.original.zip"
LIMIT = 8 * 1024 * 1024
SOURCE_PINS = {
    "elle_batch_r4.clj": "533670da2f176194cfe4776309c7b6e42dc543dcf3e43109585b10c82346bf3b",
    "original-r3/result_summary.clj": "28cc491ea897d7191ea6305219abdd1009d53b822a79cfccbac3d79dfdf1709c",
    "original-r3/transport.clj": "0664577c850598ac683f2c31f33c86e8da27a2011f694a8b147f1f91632964f0",
    "r4_controller.py": "4f9a73a5fe82478d913cb751ab68714d4ba0558c85b45a3933c6eb9a6c3078ef",
    "campaign-plan-final2.json": CAMPAIGN_SHA,
}
ELLE_SOURCE_PINS = {
    "src/elle/core.clj": "396fcbd5683787366f3bf111f512aa4f7976e0d48414f8939e3e71edeeddff98",
    "src/elle/graph.clj": "9cbe589d740593671cd02ee48300a929b9bb863ffe4da506b906eebbb222ea3f",
    "src/elle/rw_register.clj": "9ad17da5b86e6e25fe66b77e0deab9000265901a1bedd5045dbba98c7dddd1ce",
    "src/elle/list_append.clj": "f4bfeee8afef994e662a4f5e2d36219ddd714254a9590f6bc36ca0b52bf3d2e7",
    "src/elle/txn.clj": "8c3c87062d518cc7ba9cee49408fe552e8057a59e5b2068f4f8aa0bf6421a5a6",
    "src/elle/consistency_model.clj": "f909f517351081001054bef461fcdec709f6bd2d2c058955777e68033d4fb10b",
    "project.clj": "d4608919c02b20de53cb017467e54c4b8267c4f146619a612a1a585f42f7c89f",
    "LICENSE": "721c2da257578bace3332b14d8ea06643d7d26753e7ef25a837b4e904edc0bf5",
}
OPTIONS = {"consistency-models": ["serializable"], "additional-graphs": [],
           "linearizable-keys?": False, "sequential-keys?": False,
           "wfr-keys?": False, "directory": None, "cycle-search-timeout": 10000}


class AuditError(ValueError):
    pass


def require(test, message):
    if not test:
        raise AuditError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def strict_json(data):
    def pairs(items):
        out = {}
        for k, v in items:
            require(k not in out, "duplicate JSON field: " + k)
            out[k] = v
        return out
    def constant(value):
        raise AuditError("nonfinite JSON number: " + value)
    def finite_float(token):
        value = float(token)
        require(math.isfinite(value), "nonfinite JSON float: " + token)
        return value
    return json.loads(data, object_pairs_hook=pairs, parse_constant=constant, parse_float=finite_float)


def bound(data):
    return {"bytes": len(data), "sha256": sha(data)}


def check_binding(data, expected, name):
    require(bound(data) == expected, "binding differs: " + name)


@dataclass(frozen=True)
class Keyword:
    """Non-evaluated EDN keyword; distinct from a string in duplicate checks."""
    name: str

    def __str__(self):
        return self.name


class EdnList(tuple):
    pass


class EdnSet(tuple):
    pass


@dataclass(frozen=True)
class EllipsisSymbol:
    """Elle uses literal ... as data inside diagnostic :expected vectors."""
    name: str


def freeze(value):
    if isinstance(value, dict):
        return ("map", tuple((freeze(k), freeze(v)) for k, v in value.items()))
    if isinstance(value, (list, tuple)):
        return (type(value).__name__, tuple(map(freeze, value)))
    return (type(value).__name__, value)


class EdnReader:
    """Bounded data-only EDN. No tags, dispatch readers, evaluation, or symbols.

    Prepared/control inputs accept only JSON-like EDN. Raw checker output can
    additionally contain keywords, lists and sets. No code is loaded/executed.
    """
    def __init__(self, text, raw=False):
        require(len(text.encode("utf-8")) <= LIMIT, "EDN byte limit")
        self.text, self.i, self.tokens, self.raw = text, 0, 0, raw

    def ws(self):
        while self.i < len(self.text) and self.text[self.i] in " \t\r\n,":
            self.i += 1

    def value(self, depth=0):
        require(depth <= 64, "EDN nesting limit")
        self.tokens += 1
        require(self.tokens <= 100000, "EDN token limit")
        self.ws()
        require(self.i < len(self.text), "unexpected EDN EOF")
        c = self.text[self.i]
        if c == '"':
            try:
                value, end = json.JSONDecoder().raw_decode(self.text, self.i)
            except ValueError as exc:
                raise AuditError("invalid EDN string") from exc
            require(not any(0xD800 <= ord(x) <= 0xDFFF for x in value), "lone surrogate")
            self.i = end
            return value
        if c in "[{(" or (c == "#" and self.raw and self.text.startswith("#{", self.i)):
            is_set = c == "#"
            if is_set:
                self.i += 1
                c = "{"
            require(c != "(" or self.raw, "EDN lists not allowed in request")
            self.i += 1
            close = {"[": "]", "{": "}", "(": ")"}[c]
            values = []
            while True:
                self.ws()
                require(self.i < len(self.text), "unclosed EDN container")
                if self.text[self.i] == close:
                    self.i += 1
                    break
                values.append(self.value(depth + 1))
            if is_set:
                require(len(set(map(freeze, values))) == len(values), "duplicate EDN set item")
                return EdnSet(values)
            if c == "{":
                require(len(values) % 2 == 0, "odd EDN map")
                out, keys = {}, set()
                for k, v in zip(values[0::2], values[1::2]):
                    require(self.raw or type(k) is str, "request EDN map keys must be strings")
                    # The retained corpus uses only strings and keywords as map
                    # keys. Reject other key types rather than permitting Python
                    # dictionary equality to merge distinct EDN true/1 or false/0.
                    require(type(k) in (str, Keyword), "EDN map key outside audited string/keyword subset")
                    fk = freeze(k)
                    require(fk not in keys, "duplicate EDN key")
                    keys.add(fk)
                    try:
                        out[k] = v
                    except TypeError as exc:
                        raise AuditError("unsupported EDN compound map key") from exc
                return out
            return EdnList(values) if c == "(" else values
        token = re.match(r"[^\s,\[\]{}()\";]+", self.text[self.i:])
        require(token is not None, "invalid EDN token")
        token = token.group()
        self.i += len(token)
        if token == "nil":
            return None
        if token in ("true", "false"):
            return token == "true"
        if re.fullmatch(r"-?(?:0|[1-9][0-9]*)", token):
            value = int(token)
            require(-(2**63) <= value < 2**63, "EDN int64 limit")
            return value
        if self.raw and re.fullmatch(r":[A-Za-z0-9_*!?+./<>=&%$:'-]+", token):
            return Keyword(token[1:])
        if self.raw and token == "...":
            return EllipsisSymbol(token)
        raise AuditError("unsupported EDN token: " + token[:60])

    def read(self):
        value = self.value()
        self.ws()
        require(self.i == len(self.text), "extra EDN form")
        return value


def edn(text, raw=False):
    return EdnReader(text, raw).read()


def wrapper_options(data):
    """Read only the fixed adapter's data literal; never evaluate Clojure."""
    matches = re.findall(r"\(def options (\{[^}]+\})\)", data.decode("utf-8"))
    require(len(matches) == 1, "one literal adapter options map required")
    value = edn(matches[0], raw=True)
    def plain(item):
        if type(item) is Keyword:
            return str(item)
        if type(item) is dict:
            require(all(type(k) is Keyword for k in item), "literal option key")
            return {str(k): plain(v) for k, v in item.items()}
        if type(item) is list:
            return [plain(v) for v in item]
        require(item is None or type(item) in (int, bool), "nonliteral checker option")
        return item
    parsed = plain(value)
    require(canonical(parsed) == canonical(OPTIONS), "checker options/extra assumptions differ")
    return parsed


EVENT_FIELDS = {
    "snapshot": {"kind", "seq", "time", "consistent", "initial"},
    "begin": {"kind", "seq", "time", "tx", "connection"},
    "read": {"kind", "seq", "time", "tx", "key", "version"},
    "write": {"kind", "seq", "time", "tx", "key", "version", "predecessor"},
    "append": {"kind", "seq", "time", "tx", "key", "id", "value"},
    "list_read": {"kind", "seq", "time", "tx", "key", "items"},
    "commit_request": {"kind", "seq", "time", "tx"},
    "commit_ok": {"kind", "seq", "time", "tx"},
}


def name(value):
    require(type(value) is str and 0 < len(value) <= 512, "bounded nonempty identity required")
    return value


def expected_request(row):
    """Independent full projection of all original observations in this corpus.

    Deliberately rejects any extra order/client/model facts or unsupported event;
    does not infer commit order/version order, heal gaps, or consume SDK results.
    """
    source = row["input"]
    require(set(source) == {"clockDomain", "dataModel", "events", "gaps", "scope", "traceSchema"},
            "unmapped root fact (including order/session facts)")
    require(type(source["traceSchema"]) is int and source["traceSchema"] == 3 and source["gaps"] == [], "schema or coverage gap")
    require(type(source["scope"]) is dict and set(source["scope"]) == {"exclusiveWriters"}
            and source["scope"]["exclusiveWriters"] is True, "unmapped/insufficient scope")
    name(source["clockDomain"])
    model = source["dataModel"]
    require(model in ("point-register-v1", "append-list-v1"), "unsupported model")
    events = source["events"]
    require(type(events) is list and 1 <= len(events) <= 512, "event bound")
    require(events[0].get("kind") == "snapshot", "first consistent snapshot required")
    initial = events[0].get("initial")
    require(type(initial) is dict and initial, "initial map required")
    for k, v in initial.items():
        name(k)
        if model == "point-register-v1":
            name(v)
        else:
            require(v == [], "nonempty list initial state not shared by this converter")
    states, programs, begins, producer, append_ids, writers = {}, {}, {}, {}, {}, set()
    previous_time = -(2**63)
    for position, event in enumerate(events, 1):
        kind = event.get("kind")
        require(kind in EVENT_FIELDS and set(event) == EVENT_FIELDS[kind], "unmapped event fact")
        require(type(event["seq"]) is int and event["seq"] == position, "event seq not dense")
        t = event["time"]
        require(type(t) is int and -(2**63) <= t < 2**63 and t >= previous_time, "event clock")
        previous_time = t
        if kind == "snapshot":
            require(position == 1 and event["consistent"] is True, "extra/inconsistent snapshot")
            continue
        tx = name(event["tx"])
        if kind == "begin":
            require(tx not in states, "duplicate transaction identity")
            name(event["connection"])
            begins[tx] = len(begins)
            states[tx], programs[tx] = "active", []
        elif kind == "commit_request":
            require(states.get(tx) == "active", "commit request lifecycle")
            states[tx] = "requested"
        elif kind == "commit_ok":
            require(states.get(tx) == "requested", "unconfirmed/missing commit request")
            states[tx] = "committed"
        else:
            require(states.get(tx) == "active", "operation outside active transaction")
            key = name(event["key"])
            require(key in initial, "key missing from consistent snapshot")
            if kind == "write":
                require(model == "point-register-v1", "mixed model")
                version = name(event["version"])
                require(key not in writers and version not in producer and version not in initial.values(),
                        "unsupported repeat register write/version identity")
                require(event["predecessor"] == initial[key], "noninitial predecessor loses order fact")
                writers.add(key)
                producer[version] = (key, tx)
            elif kind == "read":
                require(model == "point-register-v1", "mixed model")
                name(event["version"])
            elif kind == "append":
                require(model == "append-list-v1", "mixed model")
                identity = name(event["id"])
                require(identity not in append_ids, "duplicate append identity")
                require(type(event["value"]) is str, "unmapped append business type")
                append_ids[identity] = (key, event["value"], tx)
            elif kind == "list_read":
                require(model == "append-list-v1" and type(event["items"]) is list, "list read")
                ids = []
                for item in event["items"]:
                    require(type(item) is dict and set(item) == {"id", "value"}, "unmapped list item fact")
                    ids.append(name(item["id"]))
                # Repeated identities in an observed result are anomaly input,
                # not duplicate producer declarations. Preserve every position;
                # never heal the original observation by deduplicating it.
            programs[tx].append(event)
    require(states and all(s == "committed" for s in states.values()), "unconfirmed transaction outcome")
    values = {}
    for tx, program in programs.items():
        mops = []
        for event in program:
            kind, key = event["kind"], event["key"]
            if kind == "read":
                version = event["version"]
                if version == initial[key]:
                    value = None
                else:
                    require(version in producer and producer[version][0] == key, "missing/wrong-key read source")
                    value = version
                mops.append(["r", key, value])
            elif kind == "write":
                mops.append(["w", key, event["version"]])
            elif kind == "append":
                mops.append(["append", key, event["id"]])
            else:
                for item in event["items"]:
                    require(item["id"] in append_ids and append_ids[item["id"]][:2] == (key, item["value"]),
                            "missing/mismatched list source/business value")
                mops.append(["r", key, [item["id"] for item in event["items"]]])
        values[tx] = mops
    operations, mapping = [], []
    for event in events:
        if event["kind"] not in ("begin", "commit_ok"):
            continue
        tx = event["tx"]
        invoke = event["kind"] == "begin"
        mops = [[f, k, None if invoke and f == "r" else v] for f, k, v in values[tx]]
        index = len(operations)
        operations.append({"index": index, "process": begins[tx], "type": "invoke" if invoke else "ok",
                           "f": "txn", "value": mops})
        mapping.append({"checkerIndex": index, "rawSeq": event["seq"], "tx": tx})
    return {"id": row["id"], "inputSha256": row["inputSha256"], "model": model,
            "operations": operations, "originalSeqMapping": mapping,
            "initialRegisterVersionRenaming": initial if model == "point-register-v1" else None}


def check_projection(row, actual):
    expected = expected_request(row)
    require(freeze(actual) == freeze(expected) or canonical(actual) == canonical(expected),
            "prepared EDN differs from original capture: " + row["id"])
    return {"originalEvents": len(row["input"]["events"]),
            "checkerOperations": len(expected["operations"]),
            "completedMicroOperations": sum(len(o["value"]) for o in expected["operations"] if o["type"] == "ok"),
            "repeatedObservedAppendIdentities": sum(len(e["items"]) - len({x["id"] for x in e["items"]})
                for e in row["input"]["events"] if e["kind"] == "list_read"),
            "extraUnmappedSemanticFacts": [],
            "factProjection": "single-writer-initial-register" if expected["model"] == "point-register-v1"
                              else "empty-initial-append-identities",
            "nonModelFields": ["clockDomain", "event.time", "begin.connection", "commit_request"],
            "nonModelFieldsReason": "serializable has no real-time/session requirement; only acknowledged commit_ok forms completion"}


def check_ledger(data, controls, run_id):
    rows = [strict_json(line) for line in data.splitlines()]
    require(len(rows) == len(controls) * 4, "ledger phase count")
    previous, completed = "0" * 64, {}
    phases = ["preparing", "invocation-intent", "returned", "completed"]
    for n, row in enumerate(rows):
        require(set(row) == {"body", "bodySha256", "previousSha256"}, "ledger envelope")
        require(type(row["body"]) is str and row["previousSha256"] == previous, "ledger previous")
        previous = sha(row["body"].encode("utf-8"))
        require(row["bodySha256"] == previous, "ledger body hash")
        body = strict_json(row["body"])
        ordinal, phase = n // 4, phases[n % 4]
        identity, digest = controls[ordinal]
        require(body.get("sequence") == n + 1 and body.get("runId") == run_id
                and body.get("ordinal") == ordinal and body.get("id") == identity
                and body.get("inputSha256") == digest and body.get("phase") == phase,
                "ledger original identity/order/phase")
        if phase == "completed":
            require(set(body) == {"sequence", "runId", "ordinal", "id", "inputSha256", "phase", "result", "raw", "summary"},
                    "unexpected completion fact")
            completed[identity] = body
        else:
            require(set(body) == {"sequence", "runId", "ordinal", "id", "inputSha256", "phase"}, "unexpected ledger fact")
    return completed


def check_result(raw_data, summary_data, completion, identity, digest):
    check_binding(raw_data, completion["raw"], "raw " + identity)
    check_binding(summary_data, completion["summary"], "summary " + identity)
    summary = strict_json(summary_data)
    require(summary == completion["result"], "summary differs from completed result")
    require(set(summary) == {"rawResultFile", "cycleSearchTimeout", "id", "valid", "inputSha256", "originalValidity", "anomalyTypes",
                             "actualElleResultReturned", "actualElleInvocationAttempted", "rawResultRetained"}, "summary fields")
    require(summary["id"] == identity and summary["inputSha256"] == digest and summary["rawResultFile"] == identity + ".edn", "summary identity")
    require(all(summary[k] is True for k in ("actualElleResultReturned", "actualElleInvocationAttempted", "rawResultRetained")), "actual invocation/return/raw absent")
    raw = edn(raw_data.decode("utf-8"), raw=True)
    require(type(raw) is dict and Keyword("valid?") in raw, "raw result fields")
    valid, anomalies = raw[Keyword("valid?")], raw.get(Keyword("anomaly-types"))
    # The pinned upstream summary uses (mapv name (:anomaly-types result)); nil
    # and the absent key both map to [], including Elle's {:valid? true} result.
    if anomalies is None:
        anomalies = []
    require(isinstance(anomalies, (list, EdnList)) and all(type(x) is Keyword for x in anomalies), "raw anomalies type")
    anomalies = [str(x) for x in anomalies]
    require(type(valid) is bool or type(valid) is Keyword and str(valid) == "unknown", "unsupported original validity")
    typed = {"kind": "boolean", "value": valid} if type(valid) is bool else {"kind": "keyword", "value": "unknown"}
    transported = valid if type(valid) is bool else "unknown"
    timeout = "cycle-search-timeout" in anomalies
    require(freeze(summary["originalValidity"]) == freeze(typed) and freeze(summary["valid"]) == freeze(transported)
            and summary["anomalyTypes"] == anomalies and summary["cycleSearchTimeout"] is timeout,
            "raw result transport semantic mismatch")
    eligible = type(valid) is bool and not timeout
    return {"validity": valid if type(valid) is bool else None, "originalValidity": typed,
            "anomalyTypes": anomalies, "cycleSearchTimeout": timeout,
            "comparisonEligible": eligible,
            "notComparableReasons": [] if eligible else ["upstream-cycle-timeout" if timeout else "upstream-unknown"]}


class Archive:
    def __init__(self, archive, label):
        self.z = zipfile.ZipFile(archive)
        names = self.z.namelist()
        require(len(names) == len(set(names)), label + " duplicate member")
        # On Windows ZipInfo.filename normalizes backslashes; reject the actual
        # unnormalized central-directory name rather than trusting that rewrite.
        for info in self.z.infolist():
            n = info.orig_filename
            require(not n.startswith(("/", "\\")) and "\\" not in n and ":" not in n
                    and ".." not in PurePosixPath(n).parts and n == info.filename, label + " unsafe member")
        self.opened = []

    def read(self, name, limit=LIMIT):
        # Auditing the complete ZIP hash does not open SDK member contents.
        require(not any(x in name.lower() for x in ("sdk-collection", "comparison.json", "/sdk/", "public-sdk")), "SDK verdict/member forbidden")
        info = self.z.getinfo(name)
        require(not info.is_dir() and info.file_size <= limit, "archive member limit: " + name)
        data = self.z.read(name)
        require(len(data) == info.file_size, "archive length")
        self.opened.append({"path": name, **bound(data)})
        return data


def save(output, name, data):
    p = output / name
    require(".." not in PurePosixPath(name).parts and not p.exists(), "fresh output required: " + name)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)


def check_runtime(archive, output):
    runtime_bytes = archive.read(RUNTIME_ZIP_MEMBER, 48 * 1024 * 1024)
    require(sha(runtime_bytes) == RUNTIME_ZIP_SHA, "runtime ZIP hash")
    runtime = Archive(io.BytesIO(runtime_bytes), "runtime")
    manifest_bytes = runtime.read("runtime/runtime-manifest.json")
    require(sha(manifest_bytes) == RUNTIME_MANIFEST_SHA, "runtime manifest pin")
    manifest = strict_json(manifest_bytes)
    require(manifest["fixedElleCommit"] == ELLE and manifest["additionalGraphs"] == []
            and manifest["java"] == 21 and manifest["clojure"] == "1.12.6"
            and manifest["classpathFromActualLein"] is True, "runtime version/options")
    save(output, "runtime/runtime-manifest.json", manifest_bytes)
    for path, digest in ELLE_SOURCE_PINS.items():
        data = runtime.read("runtime/upstream/" + path)
        require(sha(data) == digest, "fixed Elle source differs: " + path)
        save(output, "runtime/upstream/" + path, data)
    dependencies = manifest["original141DependencyBindings"]
    require(len(dependencies) == 141, "original dependency count")
    for path, expected in dependencies.items():
        check_binding(runtime.read("runtime/" + path, 24 * 1024 * 1024), expected, path)
    require(dependencies["lein-home/self-installs/leiningen-2.11.2-standalone.jar"]["sha256"]
            == "7d31ae23ae769e927438b0cd55d15a93e7dabab09fd4fc15877979161e108774", "Lein pin")
    prefix = manifest["upstreamRoot"].rsplit("/runtime/upstream", 1)[0] + "/"
    for entry in manifest["classpath"]:
        require(entry["path"].startswith(prefix), "classpath outside fixed runtime")
        local = entry["path"][len(prefix):]
        if "files" in entry:
            for rel, expected in entry["files"].items():
                check_binding(runtime.read(local + "/" + rel), expected, "classpath " + rel)
        else:
            check_binding(runtime.read(local, 24 * 1024 * 1024), {"bytes": entry["bytes"], "sha256": entry["sha256"]}, "classpath " + local)
    before_bytes = archive.read(PREFIX + "RUNTIME-BEFORE.json")
    after_bytes = archive.read(PREFIX + "runtime-audits/final/RUNTIME-AFTER.json")
    delta_bytes = archive.read(PREFIX + "runtime-audits/final/RUNTIME-DELTA.json")
    before, after, delta = map(strict_json, (before_bytes, after_bytes, delta_bytes))
    require(delta["originalRuntimeFilesUnchanged"] is True, "runtime original source modified")
    require(all(after["files"].get(k) == v for k, v in before["files"].items()), "runtime before/after differs")
    added = {k: v for k, v in after["files"].items() if k not in before["files"]}
    require(added == delta["generatedFiles"] and len(added) == 2 and all(
        k.startswith("runtime/upstream/classes/dom_top/core/MutableAcc-") and k.endswith(".class") for k in added),
        "unexplained generated runtime file")
    for path, data in [("before.json", before_bytes), ("after.json", after_bytes), ("delta.json", delta_bytes)]:
        save(output, "runtime/" + path, data)
    return {"originalDependenciesVerified": len(dependencies), "classpathEntriesVerified": len(manifest["classpath"]),
            "originalRuntimeFilesUnchanged": True, "generatedRuntimeFiles": added,
            "newJVMExecuted": False}


def audit(job_path, zip_path, source_root, output, previous_reference=None):
    require(not output.exists(), "destination must not exist")
    require(file_sha(job_path) == JOB_SHA, "original job SHA")
    require(file_sha(zip_path) == ZIP_SHA, "original artifact ZIP SHA")
    output.mkdir(parents=True)
    job_bytes = job_path.read_bytes()
    job = strict_json(job_bytes)
    require(type(job) is list and len(job) == 2000, "original job count")
    require([x["id"] for x in job] == [f"register-{i}" for i in range(1000)] + [f"list-{i}" for i in range(1000, 2000)], "original case IDs/order")
    for row in job:
        require(sha(canonical(row["input"])) == row["inputSha256"], "original input canonical hash")
    save(output, "fixed2000-job.original.json", job_bytes)
    for path, digest in SOURCE_PINS.items():
        data = (source_root / path).read_bytes()
        require(sha(data) == digest, "original adapter/source pin: " + path)
        save(output, "adapter/" + path, data)
    campaign = strict_json((source_root / "campaign-plan-final2.json").read_bytes())
    require(campaign["fixedElleCommit"] == ELLE and campaign["expectedInputCount"] == 2000
            and campaign["datasetSha256"] == INPUTS_SHA and len(campaign["batches"]) == 40, "campaign identity")
    archive = Archive(zip_path, "original")
    original_inputs = archive.read(PREFIX + "INPUTS.original.jsonl")
    require(sha(original_inputs) == INPUTS_SHA, "original JSONL SHA")
    require([strict_json(line) for line in original_inputs.splitlines()] == job, "original job vs archived JSONL differs")
    save(output, "INPUTS.original.jsonl", original_inputs)
    attest_bytes = archive.read(PREFIX + "SOURCE-ATTESTATION.json")
    attest = strict_json(attest_bytes)
    require(attest["head"] == "be08ec7d639acbcdd8120e752758eb3c539f45e7" and attest["parent"] == "947719688dbcd96213283499747b38b3ccfe6fde"
            and attest["runId"] == "40139252465" and attest["attempt"] == 1 and attest["original106And53R4Unchanged"] is True, "source attestation")
    manifest_bytes = archive.read(PREFIX + "SOURCE-MANIFEST.original.json")
    require(sha(manifest_bytes) == attest["manifestSha256"], "source manifest attestation")
    for path, data in [("SOURCE-ATTESTATION.json", attest_bytes), ("SOURCE-MANIFEST.original.json", manifest_bytes)]:
        save(output, path, data)
    runtime_audit = check_runtime(archive, output)
    cases, batches, cursor = [], [], 0
    for ordinal, batch in enumerate(campaign["batches"]):
        batch_name = f"batch-{ordinal:03d}"
        require(batch["name"] == batch_name and batch["planPath"] == "plans-final2/" + batch_name + ".json", "batch order/path")
        plan_bytes = (source_root / batch["planPath"]).read_bytes()
        require(sha(plan_bytes) == batch["planSha256"], "batch plan hash")
        plan = strict_json(plan_bytes)
        require(plan["controllerSha256"] == SOURCE_PINS["r4_controller.py"] and plan["wrapperSha256"] == SOURCE_PINS["elle_batch_r4.clj"]
                and all(plan[k] is False for k in ("expectedTruthSupplied", "inferredVersionOrderSupplied", "originalRulesChanged")), "batch adapter assumptions")
        original_rows = job[cursor:cursor + 50]
        controls = [[r["id"], r["inputSha256"]] for r in original_rows]
        require(plan["cases"] == [{"id": i, "inputSha256": h} for i, h in controls], "plan original input binding")
        bp = PREFIX + "elle/actual-outputs/" + batch_name + "/"
        data = archive.read(bp + "input.edn")
        check_binding(data, {"bytes": plan["batchBytes"], "sha256": plan["batchSha256"]}, "prepared batch")
        lines = data.decode("utf-8").splitlines()
        require(len(lines) == 50 and all(len(l.encode()) <= 1048576 for l in lines), "prepared batch count/line bound")
        projections = [check_projection(row, edn(line)) for row, line in zip(original_rows, lines)]
        control_data = archive.read(bp + "control.edn")
        require(edn(control_data.decode()) == controls, "original control differs")
        reg_data, acc_data = archive.read(bp + "registration.json"), archive.read(bp + "accounting.json")
        reg, acc = strict_json(reg_data), strict_json(acc_data)
        require(reg["planSha256"] == batch["planSha256"] and reg["controllerSha256"] == SOURCE_PINS["r4_controller.py"]
                and reg["fixedElleCommit"] == ELLE and reg["runtimeManifestSha256"] == RUNTIME_MANIFEST_SHA
                and reg["cases"] == plan["cases"], "registration source/runtime/input identity")
        require(acc["registrationSha256"] == sha(reg_data) and acc["transportIntegrity"] is True
                and acc["sourceBytesUnchanged"] is True and acc["SDKExecutedByController"] is False
                and acc["inputsAccounted"] == 50 and acc["actualElleReturnedInputs"] == 50
                and acc["issue"] is None, "actual batch accounting")
        process = acc["process"]
        require(process["exitCode"] == 0 and process["timedOut"] is False and process["stopReason"] is None
                and process["controllerErrors"] == [] and process["rawStreamsMayBeTruncated"] is False
                and process["argv"] == reg["argv"], "actual JVM process incomplete")
        argv = reg["argv"]
        require(argv[:4] == ["/usr/bin/xvfb-run", "-a", "-e", argv[3]]
                and argv[4] == "/usr/lib/jvm/temurin-21-jdk-amd64/bin/java"
                and argv[5] == "-Xmx1024m" and argv[6].startswith("-Djava.io.tmpdir=")
                and argv[7] == "-cp" and argv[9:11] == ["clojure.main", "-"], "actual JVM launch shape")
        # Classpath entries and order are bound to the independently retained
        # fixed runtime; the only dynamic VM flag is its separate temporary dir.
        runtime_manifest = strict_json((output / "runtime/runtime-manifest.json").read_bytes())
        require(argv[8].split(":") == [entry["path"] for entry in runtime_manifest["classpath"]], "actual fixed classpath differs")
        wrapper = archive.read(bp + "wrapper.stdin.clj")
        require(sha(wrapper) == SOURCE_PINS["elle_batch_r4.clj"], "actual wrapper stdin")
        wrapper_options(wrapper)
        check_binding(wrapper, reg["wrapperStdin"], "wrapper registration")
        delivery = process["stdinDelivery"]
        require(delivery["fullyDelivered"] is True and delivery["writtenBytes"] == len(wrapper)
                and delivery["bytes"] == len(wrapper) and delivery["sha256"] == sha(wrapper), "actual adapter stdin delivery")
        for local, pin_path in [("summary.clj", "original-r3/result_summary.clj"), ("transport.clj", "original-r3/transport.clj")]:
            require(sha(archive.read(bp + local)) == SOURCE_PINS[pin_path], "actual source helper " + local)
        for stream, binding in process["logBindings"].items():
            require(stream in ("stderr.raw", "stdout.raw"), "unknown process stream")
            check_binding(archive.read(bp + stream), binding, "actual JVM stream")
            require(process["streams"][stream.split(".")[0]]["complete"] is True, "stream incomplete")
        ledger = archive.read(bp + "ledger.jsonl")
        completed = check_ledger(ledger, controls, reg["runId"])
        save(output, "adapter/" + batch["planPath"], plan_bytes)
        for path, raw in [("input.edn", data), ("control.edn", control_data), ("registration.json", reg_data),
                          ("accounting.json", acc_data), ("ledger.jsonl", ledger)]:
            save(output, "batches/" + batch_name + "/" + path, raw)
        require(len(acc["cases"]) == 50, "case accounting count")
        for index, (row, projection) in enumerate(zip(original_rows, projections)):
            identity = row["id"]
            raw_data = archive.read(bp + "raw/" + identity + ".edn")
            summary_data = archive.read(bp + "summaries/" + identity + ".json")
            result = check_result(raw_data, summary_data, completed[identity], identity, row["inputSha256"])
            account = acc["cases"][index]
            require(account["id"] == identity and account["inputSha256"] == row["inputSha256"]
                    and account["actualCheckerInvocationAttempted"] is True and account["actualCheckerReturned"] is True
                    and account["originalValidity"] == result["originalValidity"]
                    and account["comparisonEligible"] is result["comparisonEligible"]
                    and account["cycleSearchTimeout"] is result["cycleSearchTimeout"]
                    and account["phases"] == ["preparing", "invocation-intent", "returned", "completed"], "per-case accounting mismatch")
            save(output, "batches/" + batch_name + "/raw/" + identity + ".edn", raw_data)
            save(output, "batches/" + batch_name + "/summaries/" + identity + ".json", summary_data)
            cases.append({"id": identity, "inputSha256": row["inputSha256"], "dataModel": row["input"]["dataModel"],
                          "targetModel": "serializable", "batch": batch_name, **result,
                          "projection": projection,
                          "raw": {"path": "batches/" + batch_name + "/raw/" + identity + ".edn", **bound(raw_data)},
                          "summary": {"path": "batches/" + batch_name + "/summaries/" + identity + ".json", **bound(summary_data)}})
        batches.append({"id": batch_name, "input": bound(data), "plan": bound(plan_bytes), "ledger": bound(ledger),
                        "registration": bound(reg_data), "accounting": bound(acc_data), "projectionCases": 50})
        cursor += 50
    require(cursor == 2000 and len(cases) == 2000, "full campaign not covered")
    # The independent collector is upstream-only; it never evaluates a SDK result.
    collection_data = archive.read(PREFIX + "ELLE-COLLECTION.original.json")
    collection = strict_json(collection_data)
    require(collection["campaignSha256"] == CAMPAIGN_SHA and collection["runtimeManifestSha256"] == RUNTIME_MANIFEST_SHA
            and collection["actualElleReturnedInputs"] == 2000 and collection["inputsAccounted"] == 2000
            and collection["allBatchProcessesSucceeded"] is True and collection["allTransportIntegrity"] is True
            and collection["fullCampaignTransportComplete"] is True and collection["collectionIssues"] == [], "upstream collection")
    require(len(collection["cases"]) == 2000, "upstream collection case count")
    for item, case in zip(collection["cases"], cases):
        require(item["id"] == case["id"] and item["inputSha256"] == case["inputSha256"]
                and item["originalValidity"] == case["originalValidity"]
                and item["comparisonEligible"] is case["comparisonEligible"], "upstream collector differs")
    save(output, "ELLE-COLLECTION.original.json", collection_data)
    counts = dict(collections.Counter("unknown" if c["validity"] is None else str(c["validity"]).lower() for c in cases))
    cases_content_sha = sha(canonical(cases))
    previous_check = None
    if previous_reference is not None:
        previous_bytes = previous_reference.read_bytes()
        require(sha(previous_bytes) == PREVIOUS_REFERENCE_SHA, "previous upstream reference pin")
        previous = strict_json(previous_bytes)
        require(previous["semanticContract"] == CONTRACT and previous["source"]["jobSha256"] == JOB_SHA,
                "previous reference contract/input identity")
        require(canonical(previous["cases"]) == canonical(cases), "case facts/judgments changed during reseal")
        save(output, "previous/upstream-reference-v2.bb5.json", previous_bytes)
        previous_check = {"previousReferenceSha256": PREVIOUS_REFERENCE_SHA,
                          "previousCasesContentSha256": sha(canonical(previous["cases"])),
                          "newCasesContentSha256": cases_content_sha,
                          "all2000CasesExactlyUnchanged": True,
                          "usedOnlyForPostGenerationEqualityCheck": True}
    reference = {"semanticContract": CONTRACT, "auditor": AUDITOR, "fixedElleCommit": ELLE,
                 "referenceRevision": REFERENCE_REVISION, "casesContentSha256": cases_content_sha,
                 "previousReferenceCheck": previous_check,
                 "v1ReferenceMissing": True, "missingV1ReferenceSha256": MISSING_V1_SHA,
                 "upstreamElleReexecuted": False, "sdkResultsRead": False,
                 "referenceGenerationPolicy": {"sdkVerdictsReadByGenerator": False,
                     "sdkVerdictsUsedToDeriveExpected": False, "humanBlindingClaimed": False,
                     "priorHumanContext": "Old v0.4.1 aggregate counts were seen while locating files; the generator does not consume them."},
                 "source": {"jobSha256": JOB_SHA, "originalJsonlSha256": INPUTS_SHA, "originalArtifactZipSha256": ZIP_SHA,
                            "runtimeZipSha256": RUNTIME_ZIP_SHA, "runtimeManifestSha256": RUNTIME_MANIFEST_SHA,
                            "runId": "40139252465", "jobId": "121007283470", "artifactId": "12578114941", "attempt": 1,
                            "sourceHead": attest["head"], "sourceAttestationSha256": sha(attest_bytes),
                            "campaignPlanSha256": CAMPAIGN_SHA},
                 "options": OPTIONS, "scope": {"models": ["serializable"], "dataModels": ["point-register-v1", "append-list-v1"],
                            "profile": "original pure-client observations; no extra graphs or per-key assumptions",
                            "registerPredecessors": "one writer per key; predecessor is initial, hence no discarded writer/writer ordering",
                            "listBusinessValues": "each value independently bound to original unique append identity before projecting identities",
                            "sessionOrRealtimeClaims": False, "extraUnmappedSemanticFacts": [],
                            "comparisonPolicy": "full projection audited; boolean upstream result without timeout; unknown remains not comparable"},
                 "counts": {"cases": 2000, "batches": 40, "actualUpstreamResults": counts,
                            "comparisonEligible": sum(c["comparisonEligible"] for c in cases)},
                 "batches": batches, "cases": cases}
    reference_bytes = canonical(reference) + b"\n"
    save(output, "upstream-reference-v2.json", reference_bytes)
    save(output, "upstream-reference-v2.sha256", (sha(reference_bytes) + "  upstream-reference-v2.json\n").encode())
    require(file_sha(job_path) == JOB_SHA and file_sha(zip_path) == ZIP_SHA, "source changed during audit")
    for path, digest in SOURCE_PINS.items():
        require(file_sha(source_root / path) == digest, "adapter changed during audit")
    evidence_files = {p.relative_to(output).as_posix(): bound(p.read_bytes()) for p in sorted(output.rglob("*")) if p.is_file()}
    save(output, "evidence-index.json", canonical({"files": evidence_files}) + b"\n")
    audit_summary = {"passed": True, "semanticContract": CONTRACT, "auditor": AUDITOR,
                     "referenceSha256": sha(reference_bytes), "counts": reference["counts"], "runtimeAudit": runtime_audit,
                     "v1ReferenceMissing": True, "upstreamElleReexecuted": False, "sdkResultMembersOpened": 0,
                     "casesContentSha256": cases_content_sha, "previousReferenceCheck": previous_check,
                     "referenceGenerationPolicy": reference["referenceGenerationPolicy"],
                     "originalInputsUnchanged": True, "allPreparedOperationsCompared": True,
                     "allRawSummaryLedgerBindingsCompared": True, "openedOriginalMembers": archive.opened,
                     "publicEvidenceSource": {"originalArtifact": "https://github.com/HhWw96/moontxnwitness/actions/runs/40139252465/artifacts/12578114941",
                         "originalArtifactAvailabilityReverified": False, "derivedEvidenceNeedsPublicAttachment": True},
                     "toolSha256": file_sha(Path(__file__))}
    save(output, "audit-summary.json", canonical(audit_summary) + b"\n")
    return audit_summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", required=True, type=Path)
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--previous-reference", type=Path,
                        help="optional exact bb5 upstream-only reference for post-generation case-equality proof")
    args = parser.parse_args()
    try:
        result = audit(args.job, args.artifact, args.source_root, args.output, args.previous_reference)
    except Exception as exc:
        if args.output.is_dir() and not (args.output / "audit-failure.json").exists():
            save(args.output, "audit-failure.json", canonical({"passed": False, "errorType": type(exc).__name__,
                "error": str(exc), "upstreamElleReexecuted": False, "sdkResultsRead": False}) + b"\n")
        raise
    print(json.dumps({k: result[k] for k in ("passed", "referenceSha256", "counts", "v1ReferenceMissing", "upstreamElleReexecuted")}))


if __name__ == "__main__":
    main()
