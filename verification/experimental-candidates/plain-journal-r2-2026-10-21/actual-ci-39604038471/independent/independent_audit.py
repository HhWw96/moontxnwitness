"""Independent GPT acceptance: stdlib byte audit and raw-fact reconstruction only.

Does not import candidate modules, execute tests, connect to a database, compile,
or use the author's support audit result as an oracle. Run with python -B.
"""
from __future__ import annotations
import datetime
import hashlib
import json
import pathlib
import re
import subprocess
import traceback
import zipfile

OUT = pathlib.Path(__file__).resolve().parent
ROOT = OUT.parent.parent
SUPPORT = ROOT / "artifacts/remote-plain-journal-first-39604038471"
RAW = SUPPORT / "authorized-attempt2-raw"
WORK = RAW / "plain-journal-work-39604038471-1"
EVIDENCE = WORK / "evidence"
CONTEXT = RAW / "plain-journal-context-39604038471-1"
PUBLIC = "verification/experimental-candidates/plain-journal-r2-2026-10-21"
CANDIDATE = ROOT / PUBLIC
HEAD = "bb6409c7ad51d2b999cf80043d98572f3350616c"
ZIP_SHA = "81921da5ae1f4db2f4fe9b556e4cfe4c143b4f23c107b1968f6b8679c9e93253"
IMAGE = "postgres:18.6-bookworm@sha256:afc7e2d441324c0388fa80c3d24f733b4194a4eb7f47dd8ee2b08eb1a24a647c"
NAMES = ["command-and-read-surface", "same-value-and-self-read", "rollback-sources",
         "native-returning", "not-null-error", "unsupported-sql", "ledger-overflow"]
checks = []
hashes = {}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def binding(path):
    data = path.read_bytes()
    value = {"bytes": len(data), "sha256": sha(data)}
    hashes[path.relative_to(ROOT).as_posix()] = value
    return value


def load(path):
    binding(path)
    return json.loads(path.read_bytes())


def require(condition, label):
    checks.append({"check": label, "passed": bool(condition)})
    if not condition:
        raise AssertionError(label)


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def git_bytes(path, remote_blob=None):
    # Git-for-Windows `show revision:very-long-path` first stats its whole argument.
    # The fresh immutable API tree supplies the exact blob object ID instead.
    command = ["git", "cat-file", "blob", remote_blob] if remote_blob else ["git", "show", HEAD + ":" + path]
    result = subprocess.run(command, cwd=ROOT, capture_output=True)
    require(result.returncode == 0, "fixed git blob exists: " + path)
    return result.stdout


def byte_and_run_audit():
    run = load(OUT / "run-api.json")
    require(run["id"] == 39604038471 and run["head_sha"] == HEAD and
            run["event"] == "workflow_dispatch" and run["status"] == "completed" and
            run["conclusion"] == "success" and run["run_attempt"] == 1 and
            run["path"] == ".github/workflows/experimental-plain-journal.yml", "live run identity and success")
    jobs = load(OUT / "jobs-api.json")["jobs"]
    require(len(jobs) == 1 and jobs[0]["id"] == 119235551030 and
            jobs[0]["head_sha"] == HEAD and jobs[0]["run_id"] == run["id"] and
            jobs[0]["run_attempt"] == 1 and jobs[0]["conclusion"] == "success" and
            all(step["conclusion"] == "success" for step in jobs[0]["steps"]), "live job and all 15 steps succeeded")
    artifacts = load(OUT / "artifacts-api.json")["artifacts"]
    require(len(artifacts) == 1, "one uploaded artifact")
    artifact = artifacts[0]
    require(artifact["id"] == 12347921707 and artifact["name"] == "plain-journal-r2-raw-evidence" and
            artifact["size_in_bytes"] == 379798 and artifact["digest"] == "sha256:" + ZIP_SHA and
            artifact["workflow_run"]["head_sha"] == HEAD and artifact["workflow_run"]["id"] == run["id"], "live artifact API binds fixed source and ZIP digest")
    archive = SUPPORT / "artifact-12347921707-authorized-attempt2.zip"
    require(binding(archive) == {"bytes": 379798, "sha256": ZIP_SHA}, "independent ZIP bytes equal API digest and size")
    with zipfile.ZipFile(archive) as z:
        files = [i for i in z.infolist() if not i.is_dir()]
        require(z.testzip() is None, "ZIP CRC valid")
        require(len(files) == len({i.filename for i in files}) == 251, "ZIP has 251 unique files")
        actual = {p.relative_to(RAW).as_posix() for p in RAW.rglob("*") if p.is_file()}
        require(actual == {i.filename for i in files}, "reused extraction has exactly ZIP file set")
        for info in files:
            name = pathlib.PurePosixPath(info.filename)
            require(not name.is_absolute() and ".." not in name.parts, "ZIP safe member: " + info.filename)
            path = RAW.joinpath(*name.parts)
            require(path.read_bytes() == z.read(info), "extracted member equals independently read ZIP: " + info.filename)
            binding(path)
    commit = load(OUT / "fixed-commit-api.json")
    require(commit["sha"] == HEAD, "live immutable commit API")
    top = load(OUT / "candidate-contents-api.json")
    tree = load(OUT / "candidate-bundle-tree-api.json")
    require(not tree.get("truncated", False), "public candidate tree not truncated")
    remote = {item["path"]: item["sha"] for item in top if item["type"] == "file"}
    remote.update({PUBLIC + "/bundle/" + item["path"]: item["sha"] for item in tree["tree"] if item["type"] == "blob"})
    local = {p.relative_to(ROOT).as_posix(): p for p in CANDIDATE.rglob("*") if p.is_file()}
    require(set(local) == set(remote) and len(local) == 69, "public fixed-commit candidate has exactly 69 files")
    for rel, path in local.items():
        data = git_bytes(rel, remote[rel])
        require(path.read_bytes() == data and git_blob(data) == remote[rel], "public API git blob/current candidate exact: " + rel)
        binding(path)
    workflow = git_bytes(".github/workflows/experimental-plain-journal.yml")
    require(workflow == (CANDIDATE / "manual-workflow.yml").read_bytes(), "actual fixed workflow equals frozen reviewed workflow")
    require(IMAGE.encode() in workflow and b"--require-hashes --only-binary=:all:" in workflow and
            b"python-version: '3.12.5'" in workflow, "fixed workflow pins image, hash installation and Python")
    manifest = load(CANDIDATE / "candidate-index.json")
    for rel, expect in manifest["fileBindings"].items():
        require(binding(CANDIDATE / rel) == expect, "frozen public outer manifest: " + rel)
    bundle = load(CANDIDATE / "bundle/bundle-index.json")
    execution = load(EVIDENCE / "execution-receipt.json")
    expected = {rel: {k: val[k] for k in ["bytes", "sha256"]} for rel, val in bundle["files"].items()}
    require(len(expected) == 62 and execution["restoredFilesBefore"] == expected and
            execution["restoredFilesAfter"] == expected, "all 62 pre/post CI source bindings equal frozen bundle")
    restored = WORK / "restored-repository"
    require({p.relative_to(restored).as_posix() for p in restored.rglob("*") if p.is_file()} == set(expected), "actual restored layout exact 62-file set")
    for rel, expect in expected.items():
        require(binding(restored / rel) == expect and binding(CANDIDATE / "bundle" / bundle["files"][rel]["bundleFile"]) == expect,
                "actual restored bytes match public bundle: " + rel)
    for rel, expect in execution["rawEvidenceBindings"].items():
        require(binding(EVIDENCE / rel) == expect, "CI raw evidence hash binding: " + rel)
    require(len(execution["rawEvidenceBindings"]) == 182, "182 CI evidence hashes checked")
    for key in ["workflowCommit", "requestedSourceRef", "checkedOutSourceCommit"]:
        require(execution[key] == HEAD, "execution immutable source: " + key)
    source = load(CONTEXT / "source-context.json")
    require(all(source[k] == HEAD for k in ["sourceCommit", "workflowCommit", "requestedRef"]) and source["image"] == IMAGE, "CI source context bound")
    require(source["actualDatabaseTestsExecuted"] is False, "pre-execution context is not misrepresented as final DB receipt")
    logfile = OUT / "job-119235551030-authorized.log"
    log = logfile.read_text(encoding="utf-8-sig")
    binding(logfile)
    for needle in [HEAD, IMAGE, "SHA256 digest of uploaded artifact is " + ZIP_SHA,
                   "Artifact ID 12347921707", "Final size is 379798 bytes", "Python 3.12.5"]:
        require(needle in log, "fresh authenticated job log binding: " + needle)
    server = (CONTEXT / "postgres-server.log").read_text()
    require("starting PostgreSQL 18.6" in server and "violates not-null constraint" in server and
            'UPDATE "mtw_provenance_plain_1a31862e8922_4"."items" SET "value"=$1' in server,
            "server log independently corroborates exact version and original NOT NULL SQL")
    require("Successfully installed psycopg-3.3.6 psycopg-binary-3.3.6" in (CONTEXT / "driver-install.log").read_text(), "pinned real driver installation log")
    pg = load(EVIDENCE / "postgres/postgres-receipt.json")
    unit_path = EVIDENCE / execution["runs"][0]["receipt"]
    unit = load(unit_path)
    require(pg["serverVersion"] == 180006 and pg["driver"] == execution["driver"] == "3.3.6", "actual exact PG180006 and psycopg3.3.6")
    for receipt in [pg, unit]:
        require(receipt["sourceBindingsBefore"] == receipt["sourceBindingsAfter"], "unit/PG source pre/post identical")
        for rel, expect in receipt["sourceBindingsBefore"].items():
            require(binding(restored / rel) == expect == expected[rel], "unit/PG source against public bytes: " + rel)
    require(unit["tests"] == 31 and unit["passed"] is True and not unit["skipped"] and not unit["failures"], "31 unit/FS/mock tests zero skip and failure")
    test_source = (restored / "artifacts/plain-v3-journal-r2-draft/test_profile.py").read_text()
    tests = re.findall(r"^    def (test_\w+)\(", test_source, re.M)
    unit_log = (EVIDENCE / "unit-31.log").read_text()
    require(len(tests) == 31 and all(re.search(r"^" + re.escape(name) + r" .* \.\.\. ok$", unit_log, re.M) for name in tests)
            and "Ran 31 tests" in unit_log and "\nOK\n" in unit_log, "all 31 frozen test names individually logged ok")
    require([c["name"] for c in pg["cases"]] == NAMES and pg["passed"] is True and execution["passed"] is True, "seven fixed scenarios reported with successful runner exit")
    for r in execution["runs"]:
        require(r["exitCode"] == 0 and r["executed"] is True and r["passed"] is True and
                binding(EVIDENCE / r["log"]) == r["logBinding"] and binding(EVIDENCE / r["receipt"]) == r["receiptBinding"], "bound CI subprocess exit/log/receipt: " + r["name"])
    for r in [execution, pg, unit]:
        require(r["coreProofImplemented"] is False and r["formalEligible"] is False and
                r["formalPerformanceMeasurement"] is False and r["independentAcceptance"] is False, "author receipts retain experimental boundaries")
    failure = load(SUPPORT / "download-attempt1-failure.json")
    require(binding(SUPPORT / "artifact-12347921707.zip") == failure["responseBinding"] and
            binding(SUPPORT / "download-stderr.log") == failure["stderrBinding"] and
            failure["failure"] == "GitHub HTTP401 Requires authentication", "original first-download HTTP401 bytes preserved")
    binding(SUPPORT / "author-support-readonly-audit.json")
    binding(SUPPORT / "read_only_audit.py")
    return execution, pg


def reconstruct(name, expected_case):
    folder = EVIDENCE / "postgres" / name
    case = load(folder / "case-receipt.json")
    require(case == expected_case, name + ": case standalone/aggregate identical")
    for rel, expect in case["rawFileBindings"].items():
        require(binding(folder / rel) == expect, name + ": raw case byte binding " + rel)
    jdir = folder / "capture/journal"
    index = load(jdir / "journal-index.json")
    canonical = json.dumps({k: v for k, v in index.items() if k != "indexSha256"}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    require(sha(canonical) == index["indexSha256"], name + ": journal index self hash")
    events = []
    for segment in index["segments"]:
        p = jdir / segment["name"]
        require(binding(p) == {k: segment[k] for k in ["bytes", "sha256"]}, name + ": segment hash")
        part = [json.loads(line) for line in p.read_bytes().splitlines()]
        require(len(part) == segment["eventCount"] and part[0]["seq"] == segment["firstSeq"] and part[-1]["seq"] == segment["lastSeq"], name + ": segment boundaries")
        events.extend(part)
    require([e["seq"] for e in events] == list(range(1, len(events) + 1)) and
            all(a["time"] <= b["time"] for a, b in zip(events, events[1:])) and
            len(events) == index["eventCount"] == index["durableSeq"], name + ": contiguous durable journal")
    sdir = folder / "capture/sources"
    sindex = load(sdir / "index.json")
    records_bytes = (sdir / "records.jsonl").read_bytes()
    require({"bytes": len(records_bytes), "sha256": sha(records_bytes)} == {k: sindex[k] for k in ["bytes", "sha256"]}, name + ": complete source byte digest")
    chain = "0" * 64
    sources = {}
    for seq, line in enumerate(records_bytes.splitlines(keepends=True), 1):
        record = json.loads(line)
        require(record["seq"] == seq and record["previous"] == chain and record["sourceSchema"] == 1, name + ": independent source chain " + str(seq))
        chain = sha(line)
        sources[seq] = record["payload"]
    require(chain == sindex["lastRecordSha256"] and len(sources) == sindex["records"] and sindex["closed"] is True, name + ": source footer integrity (not semantic closure)")
    installation = sources[1]
    require(installation["kind"] == "installation" and installation["serverVersion"] == 180006 and installation["coreProofImplemented"] is False, name + ": actual installation source")
    initial_rows = installation["initialRows"]
    require(len(initial_rows) == 2 and {r[0] for r in initial_rows} == {"k", "other"} and events[0]["initial"] == {r[0]: r[2] for r in initial_rows}, name + ": locked initial snapshot exact keys/tokens")
    require(installation["window"][0]["tag"] == "BEGIN" and installation["window"][1]["tag"] == "LOCK TABLE" and
            "ACCESS EXCLUSIVE MODE" in installation["window"][1]["sql"] and installation["window"][-1]["tag"] == "COMMIT", name + ": locked migration window acknowledged")
    expected_ledger = {r[2]: [r[2], r[0], "initial", True, None, None, r[1]] for r in initial_rows}
    committed = {r[0]: (r[2], r[1]) for r in initial_rows}
    all_tokens = set(expected_ledger)
    pending = {}
    working = {}
    statements = {}
    rows = {}
    writes = []
    reads = []
    outcomes = []
    for e in events[1:]:
        kind = e["kind"]
        tx = e.get("tx")
        if kind == "begin":
            require(tx not in working, name + ": transaction begins once")
            working[tx] = dict(committed)
            pending[tx] = []
        elif kind == "statement":
            require(tx in working, name + ": statement has open transaction")
            statements[e["seq"]] = e
        elif kind == "rows":
            require(e["statement"] in statements and statements[e["statement"]]["tx"] == tx, name + ": business rows bind statement")
            rows[e["seq"]] = e
            if "serverRows" in e:
                require(e["rows"] == [r[:1] for r in e["serverRows"]] and e["columns"] == [{"name": "value", "typeCode": 23}], name + ": business value projection hides only metadata")
        elif kind in ["write", "read"]:
            st = statements[e["statement"]]
            require(tx in working and st["tx"] == tx, name + ": fact binds open statement transaction")
            param = st["parameters"]
            key = param[0] if kind == "read" else param[1]
            require(e["key"] == key, name + ": key derives from original business parameters")
            if "sourceLogSeq" in e["evidence"]:
                source = sources[e["evidence"]["sourceLogSeq"]]
                pair = source["effectRows"][e["evidence"]["effectRow"]]
                business = rows[source["businessRowsEvent"]]
                require(source["kind"] == "command-effect" and source["statement"] == e["statement"] and source["tx"] == tx and
                        source["actualSql"] == st["executedSql"] and pair == [e["predecessor"], e["version"]] and
                        business["rows"] == [] and business["complete"] is True and
                        source["businessCommand"] == {"description": None, "rowcount": 1, "rownumber": None, "statusmessage": "UPDATE 1"}, name + ": internal same-statement source and original command surface")
            else:
                business = next(r for r in rows.values() if r["statement"] == e["statement"])
                server_row = business["serverRows"][e["evidence"]["serverRow"]]
                require(server_row[-1] == e["version"], name + ": delivered server token source")
                if kind == "write":
                    require(server_row[-2:] == [e["predecessor"], e["version"]], name + ": native RETURNING OLD/NEW sources")
            if kind == "write":
                previous, old_value = working[tx][key]
                require(e["predecessor"] == previous and e["version"] not in all_tokens, name + ": fresh token and actual predecessor")
                all_tokens.add(e["version"])
                value = param[0]
                pending[tx].append([e["version"], key, "UPDATE", True, previous, old_value, value])
                working[tx][key] = (e["version"], value)
                writes.append(e)
            else:
                require((e["version"], business["rows"][e["evidence"]["serverRow"]][0]) == working[tx][key], name + ": delivered read matches visible local source")
                reads.append(e)
        elif kind == "commit_request":
            require(tx in working, name + ": commit request on open transaction")
        elif kind in ["commit_ok", "rollback_ok"]:
            require(tx in working, name + ": actual outcome closes open transaction")
            if kind == "commit_ok":
                require(any(p["kind"] == "commit_request" and p["tx"] == tx and p["seq"] < e["seq"] for p in events), name + ": commit acknowledged after request")
                committed = working[tx]
                expected_ledger.update({r[0]: r for r in pending[tx]})
            del working[tx]
            del pending[tx]
            outcomes.append(kind)
    require(not working and not index["activeTransactions"] and not index["commitRequests"] and not any(index["references"].values()), name + ": no unresolved transaction or unread reference")
    ledger = [p for p in sources.values() if p["kind"] == "ledger-row"]
    ends = [p for p in sources.values() if p["kind"] == "ledger-end"]
    require([p["ordinal"] for p in ledger] == list(range(1, len(ledger) + 1)), name + ": streamed ledger ordinal continuity")
    require(len({p["row"][0] for p in ledger}) == len(ledger) and all(expected_ledger.get(p["row"][0]) == p["row"] for p in ledger), name + ": actual final/partial rows reconstruct without UUID ordering")
    positive = name in NAMES[:4]
    if positive:
        require(len(ends) == 1 and ends[0] == {"kind": "ledger-end", "rows": len(ledger), "commandTag": "COMMIT", "complete": True} and
                {p["row"][0]: p["row"] for p in ledger} == expected_ledger and index["gaps"] == [], name + ": complete final ledger equals committed reconstructed sources")
    else:
        require(not ends and bool(index["gaps"]), name + ": no complete ledger footer and explicit gap")
    closure = index["closed"] and index["sourceClosed"] and not index["gaps"] and len(ends) == 1 and ends[0]["complete"]
    require(bool(closure) == positive == case["rawJournal"]["complete"] and len(writes) == case["writeFacts"] and len(reads) == case["readFacts"], name + ": independently derived closure and fact counts")
    require(case["coreProofImplemented"] is False and case["formalEligible"] is False, name + ": proof/formal flags remain false")
    if name == "command-and-read-surface":
        require(case["actualFetchmanyZeroRows"] == 1 and len(reads) == 2 and all(r["version"] == initial_rows[0][2] for r in reads), name + ": actual fetchmany(0) delivers one row, no fabricated EOF or duplicate read")
    elif name == "same-value-and-self-read":
        require(len(writes) == 2 and writes[0]["version"] != writes[1]["version"] and writes[1]["predecessor"] == writes[0]["version"] and reads[0]["version"] == writes[1]["version"] and
                [statements[w["statement"]]["parameters"][0] for w in writes] == [5, 5], name + ": equal-value writes remain distinct and own read sees latest token")
    elif name == "rollback-sources":
        require(outcomes == ["rollback_ok"] and writes[0]["version"] not in expected_ledger and reads[0]["version"] == writes[0]["version"] and len(ledger) == 2, name + ": rolled back source retained in raw but excluded final ledger")
    elif name == "native-returning":
        require(len(writes) == 1 and any(r.get("rows") == [[8]] for r in rows.values()) and not any(p["kind"] == "command-effect" for p in sources.values()), name + ": original RETURNING value delivered with same-row source")
    elif name == "not-null-error":
        require(any(r.get("error") == {"class": "NotNullViolation", "sqlstate": "23502"} and r["complete"] is False and r["rows"] == [] for r in rows.values()) and
                case["sqlstate"] == "23502" and case["originalExceptionIdentity"] is True and outcomes == ["rollback_ok"] and not writes, name + ": real SQL23502 boundary and no invented source")
    elif name == "unsupported-sql":
        require(any(r.get("rows") == [[2]] for r in rows.values()) and not writes and not reads and "unknown_sql" in {g["code"] for g in index["gaps"]}, name + ": original unknown-SQL value preserved with gap")
    elif name == "ledger-overflow":
        require(len(ledger) == 1 and len(expected_ledger) == 3 and "ledger_incomplete" in {g["code"] for g in index["gaps"]} and case["ledgerOverflowClass"] == "ProvenanceError", name + ": bounded partial ledger cannot imply completion")
    return {"name": name, "events": len(events), "sourceRecords": len(sources), "writeFacts": len(writes), "readFacts": len(reads),
            "expectedCommittedLedgerRows": len(expected_ledger), "actualLedgerRows": len(ledger), "completeLedgerFooter": bool(ends),
            "independentlyReconstructedClosureComplete": bool(closure), "outcomes": outcomes,
            "gaps": [g["code"] for g in index["gaps"]], "finalVisibleBusinessValues": {k: v[1] for k, v in committed.items()},
            "coreProofImplemented": False, "formalEligible": False}


def main():
    result = {"schema": 1, "role": "independent-GPT-acceptance-of-fixed-actual-CI-raw-evidence", "passed": False,
              "runId": "39604038471", "sourceCommit": HEAD, "artifactId": 12347921707,
              "independentAIAcceptance": True, "humanAcceptance": False, "organizerAcceptance": False,
              "actualLocalDatabaseExecution": False, "actualLocalTestsOrBuildsExecuted": False,
              "actualDatabaseExecutionRecordedByBoundCI": True, "formalPerformanceMeasurement": False,
              "coreProofImplemented": False, "formalEligible": False,
              "method": "Independent stdlib ZIP/API/git-blob/hash-chain audit and raw replay. No candidate-module import and no support-result oracle."}
    try:
        execution, pg = byte_and_run_audit()
        result["caseSummaries"] = [reconstruct(name, pg["cases"][i]) for i, name in enumerate(NAMES)]
        result["passed"] = True
        result["sourceFilesBeforeAfter"] = 62
        result["unitTestsBound"] = 31
        result["unitSkipCount"] = 0
        result["actualPGScenariosBound"] = 7
        result["closureCompleteCases"] = NAMES[:4]
        result["incompleteCases"] = NAMES[4:]
        result["supportAuditBindingOnly"] = hashes[(SUPPORT / "author-support-readonly-audit.json").relative_to(ROOT).as_posix()]
        result["businessBoundaryEvidence"] = {
            "AandCComparison": "Frozen postgres.py executes native baseline and observed business reads/commands/RETURNING and asserts surface/value/error equality. Bound CI success establishes those assertions completed; raw events independently confirm value projection and source facts.",
            "fetchmanyZero": "Actual pinned psycopg fetchmany(0) returns one row for this fixture, matched against native baseline. No empty-batch assumption was substituted.",
            "noResultFetch": "Synthetic pinned ProgrammingError/closed InterfaceError class-message-sqlstate are compared against native cursor; they are not claimed to be native exception objects.",
            "originalExecuteError": "Frozen ExecuteProbe verifies the real 23502 exception is rethrown by Python object identity. JSON alone cannot independently prove object identity; this conclusion depends on frozen assertion source plus bound successful CI execution.",
            "notANewExperiment": "This audit did not rerun PostgreSQL or the native baseline."}
        result["limits"] = ["Independent GPT acceptance, not human or organizer acceptance.",
                            "Controlled generated SELECT/UPDATE/UPDATE RETURNING existing-key fixture only; two keys in these actual cases.",
                            "No CRUD/negative-read coverage, over-64-key support, actual multi-window handoff, analyzer proof, or complete C/A cost result.",
                            "Snapshot/table lock and single business connection per case do not establish arbitrary SQL, concurrent schedule semantics, or a six-model proof.",
                            "Complete source-log integrity is distinct from complete capture closure; diagnostics correctly remain incomplete.",
                            "Pre-execution source-context actualDatabaseTestsExecuted=false is preserved; final execution/PG receipts and raw data establish actual CI DB execution."]
    except BaseException as error:
        result["failure"] = {"class": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}
    result["checks"] = len(checks)
    result["failedChecks"] = [c for c in checks if not c["passed"]]
    result["timestampUTC"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    hashes[pathlib.Path(__file__).relative_to(ROOT).as_posix()] = {"bytes": pathlib.Path(__file__).stat().st_size, "sha256": sha(pathlib.Path(__file__).read_bytes())}
    for file in OUT.iterdir():
        if file.is_file() and file.suffix in [".json", ".log"] and file.name not in ["independent-receipt.json", "raw-hashes.json", "check-results.json"]:
            binding(file)
    (OUT / "raw-hashes.json").write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")
    (OUT / "check-results.json").write_text(json.dumps(checks, indent=2) + "\n", encoding="utf-8")
    result["rawHashesBinding"] = {"bytes": (OUT / "raw-hashes.json").stat().st_size, "sha256": sha((OUT / "raw-hashes.json").read_bytes())}
    result["checkResultsBinding"] = {"bytes": (OUT / "check-results.json").stat().st_size, "sha256": sha((OUT / "check-results.json").read_bytes())}
    (OUT / "independent-receipt.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ["passed", "checks", "failedChecks"]}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
