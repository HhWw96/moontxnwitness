#!/usr/bin/env python3
"""Verify the retained pure-data reference bundle without Java/JARs or an SDK.

The caller supplies an independently obtained manifest hash. The original large
artifact is optional; its absence is explicitly not counted as re-verification.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import sys

REFERENCE_SHA = "d3ebd816971668eb4b7347987b73bc05bf959bc93d2d58e789afc44892acae97"
AUDITOR_SHA = "10d67c8f3c446e03b9c01c29935a09f612cf66c3a8ea14706678578787eac26c"
CASE_CONTENT_SHA = "524819b2920f9ee005469e4a08a6a65ef1f25969d123346b9c3a45ecc46cb76f"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    h = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def safe_file(root, relative):
    require(type(relative) is str and relative and "\\" not in relative and ":" not in relative,
            "invalid bundle path")
    pure = PurePosixPath(relative)
    require(not pure.is_absolute() and ".." not in pure.parts, "unsafe bundle path")
    path = (root / relative).resolve(strict=True)
    require(path.is_relative_to(root) and path != root and path.is_file(), "bundle member escapes root")
    return path


def verify(bundle, expected_manifest_sha, original_artifact=None):
    root = bundle.resolve(strict=True)
    require(re.fullmatch("[a-f0-9]{64}", expected_manifest_sha), "independent manifest hash required")
    manifest_bytes = safe_file(root, "bundle-manifest.json").read_bytes()
    require(sha(manifest_bytes) == expected_manifest_sha, "bundle manifest hash differs")
    manifest = json.loads(manifest_bytes)
    require(manifest["semanticContract"] == "retained-elle-reference-evidence-bundle/v1", "bundle contract")
    require(manifest["referenceSha256"] == REFERENCE_SHA, "reference identity")
    require(safe_file(root, "bundle-manifest.sha256").read_text().split()[0] == expected_manifest_sha, "manifest sidecar")
    for relative, binding in manifest["files"].items():
        path = safe_file(root, relative)
        require(path.stat().st_size == binding["bytes"] and file_sha(path) == binding["sha256"], "file binding: " + relative)
    actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    require(actual == set(manifest["files"]) | {"bundle-manifest.json", "bundle-manifest.sha256"}, "unindexed/missing bundle file")
    auditor_path = safe_file(root, "tools/audit_reference.py")
    require(file_sha(auditor_path) == AUDITOR_SHA, "fixed auditor source hash")
    spec = importlib.util.spec_from_file_location("retained_elle_auditor", auditor_path)
    a = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = a
    old_bytecode = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(a)
    finally:
        sys.dont_write_bytecode = old_bytecode
    def read(relative):
        return safe_file(root, relative).read_bytes()
    reference_bytes, job_bytes = read("upstream-reference-v2.json"), read("fixed2000-job.original.json")
    require(sha(reference_bytes) == REFERENCE_SHA and sha(job_bytes) == a.JOB_SHA, "fixed reference/job bytes")
    ref, job = a.strict_json(reference_bytes), a.strict_json(job_bytes)
    require(ref["semanticContract"] == a.CONTRACT and ref["fixedElleCommit"] == a.ELLE and len(job) == 2000,
            "reference/corpus identity")
    jsonl = read("INPUTS.original.jsonl")
    require(sha(jsonl) == a.INPUTS_SHA and [a.strict_json(line) for line in jsonl.splitlines()] == job, "job/JSONL equality")
    for row in job:
        require(sha(a.canonical(row["input"])) == row["inputSha256"], "original capture hash")
    for relative, digest in a.SOURCE_PINS.items():
        require(sha(read("adapter/" + relative)) == digest, "fixed adapter source: " + relative)
    a.wrapper_options(read("adapter/elle_batch_r4.clj"))
    for relative, digest in a.ELLE_SOURCE_PINS.items():
        require(sha(read("runtime/upstream/" + relative)) == digest, "fixed Elle excerpt: " + relative)
    runtime_bytes = read("runtime/runtime-manifest.json")
    require(sha(runtime_bytes) == a.RUNTIME_MANIFEST_SHA, "retained runtime manifest pin")
    runtime = a.strict_json(runtime_bytes)
    require(runtime["fixedElleCommit"] == a.ELLE and runtime["additionalGraphs"] == []
            and runtime["java"] == 21 and runtime["clojure"] == "1.12.6", "runtime metadata identity")
    campaign = a.strict_json(read("adapter/campaign-plan-final2.json"))
    require(len(campaign["batches"]) == 40, "forty batches required")
    reconstructed, cursor, micro_ops = [], 0, 0
    for ordinal, batch in enumerate(campaign["batches"]):
        name = f"batch-{ordinal:03d}"
        require(batch["name"] == name, "batch order")
        plan_bytes = read("adapter/" + batch["planPath"])
        require(sha(plan_bytes) == batch["planSha256"], "plan SHA")
        plan = a.strict_json(plan_bytes)
        rows = job[cursor:cursor + 50]
        controls = [[row["id"], row["inputSha256"]] for row in rows]
        require(plan["cases"] == [{"id": i, "inputSha256": h} for i, h in controls], "plan original input identity")
        bp = "batches/" + name + "/"
        input_bytes = read(bp + "input.edn")
        a.check_binding(input_bytes, {"bytes": plan["batchBytes"], "sha256": plan["batchSha256"]}, "prepared batch")
        lines = input_bytes.decode().splitlines()
        require(len(lines) == 50 and a.edn(read(bp + "control.edn").decode()) == controls, "prepared/control counts")
        projections = [a.check_projection(row, a.edn(line)) for row, line in zip(rows, lines)]
        micro_ops += sum(p["completedMicroOperations"] for p in projections)
        reg_bytes, acc_bytes = read(bp + "registration.json"), read(bp + "accounting.json")
        reg, acc = a.strict_json(reg_bytes), a.strict_json(acc_bytes)
        require(acc["registrationSha256"] == sha(reg_bytes) and acc["transportIntegrity"] is True
                and acc["sourceBytesUnchanged"] is True and acc["issue"] is None, "retained accounting")
        require(reg["planSha256"] == batch["planSha256"] and reg["cases"] == plan["cases"]
                and reg["fixedElleCommit"] == a.ELLE and reg["runtimeManifestSha256"] == a.RUNTIME_MANIFEST_SHA,
                "retained registration input/source/runtime")
        require(acc["process"]["exitCode"] == 0 and acc["process"]["timedOut"] is False
                and acc["process"]["controllerErrors"] == [] and acc["process"]["stopReason"] is None,
                "retained successful execution evidence")
        completed = a.check_ledger(read(bp + "ledger.jsonl"), controls, reg["runId"])
        for row, projection in zip(rows, projections):
            identity = row["id"]
            raw_path, summary_path = bp + "raw/" + identity + ".edn", bp + "summaries/" + identity + ".json"
            raw_bytes, summary_bytes = read(raw_path), read(summary_path)
            result = a.check_result(raw_bytes, summary_bytes, completed[identity], identity, row["inputSha256"])
            reconstructed.append({"id": identity, "inputSha256": row["inputSha256"], "dataModel": row["input"]["dataModel"],
                "targetModel": "serializable", "batch": name, **result, "projection": projection,
                "raw": {"path": raw_path, **a.bound(raw_bytes)}, "summary": {"path": summary_path, **a.bound(summary_bytes)}})
        cursor += 50
    require(cursor == 2000 and a.canonical(reconstructed) == a.canonical(ref["cases"]), "all original facts/result reconstructions differ")
    require(sha(a.canonical(reconstructed)) == CASE_CONTENT_SHA == ref["casesContentSha256"], "cases content seal")
    previous_bytes = read("previous/upstream-reference-v2.bb5.json")
    require(sha(previous_bytes) == a.PREVIOUS_REFERENCE_SHA, "previous reference pin")
    require(a.canonical(a.strict_json(previous_bytes)["cases"]) == a.canonical(reconstructed), "old/new case equality")
    audit = a.strict_json(read("audit-summary.json"))
    require(audit["passed"] is True and audit["referenceSha256"] == REFERENCE_SHA and audit["toolSha256"] == AUDITOR_SHA,
            "retained full-audit receipt identity")
    original_checked = False
    if original_artifact is not None:
        require(file_sha(original_artifact) == a.ZIP_SHA, "optional original ZIP SHA differs")
        original_checked = True
    return {"passed": True, "format": "retained-elle-pure-data-offline-verification/v1",
            "referenceSha256": REFERENCE_SHA, "manifestSha256": expected_manifest_sha,
            "auditorSha256": AUDITOR_SHA, "offlineVerifierSha256": file_sha(Path(__file__)),
            "filesVerified": len(actual), "originalCasesVerified": 2000, "batchesVerified": 40,
            "completedMicroOperationsVerified": micro_ops, "casesContentSha256": CASE_CONTENT_SHA,
            "allPreparedOperationsAndRetainedResultsReconstructed": True,
            "upstreamElleReexecuted": False, "sdkExecuted": False, "referenceRegenerated": False,
            "originalArtifactZipShaVerifiedInThisRun": original_checked,
            "runtimeDependencyJarsRehashedInThisRun": False,
            "historicalFullAuditReceiptVerified": True,
            "retainedRuntimeManifestAndSourceExcerptsVerified": True,
            "originalArtifactNotSuppliedIsNotCountedAsVerified": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--expected-manifest-sha", required=True)
    parser.add_argument("--original-artifact", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    require(not args.output.exists(), "fresh receipt path required")
    require(not args.output.resolve().is_relative_to(args.bundle.resolve()), "receipt must be outside immutable evidence bundle")
    receipt = verify(args.bundle, args.expected_manifest_sha, args.original_artifact)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
