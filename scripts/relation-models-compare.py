"""Compare supplied SDK reports with the independent original-program reference.

This stage does not authenticate an SDK execution. The JavaScript runner runs
and verifies the public SDK separately, then binds these exact report bytes.
Pending weak-model decisions and premise-only checks never count as parity.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys


SEED = 20261113
MAX_CASES = 1000
MAX_REPORT_LINE = 40 * 1024 * 1024
FROZEN_1000_SHA256 = "b6e7d376c4a4b4664c3f728b0a57ca9171399cbbc42088082ebdbd3871037a9a"
REFERENCE_COMMIT = "4e359e597c52938b0afebb8bc42273914d68a424"
BASE = Path(__file__).resolve().parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_binding(path):
    digest, size = hashlib.sha256(), 0
    with path.open("rb") as stream:
        while block := stream.read(65536):
            digest.update(block)
            size += len(block)
    return {"bytes": size, "sha256": digest.hexdigest()}


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def decode_json(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "Duplicate JSON field: " + key)
            result[key] = value
        return result

    def constant(value):
        raise ValueError("Non-JSON numeric constant: " + value)

    return json.loads(text, object_pairs_hook=unique, parse_constant=constant)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def canonical_options(case):
    return {"models": "elle-core", **case["options"]}


def translate_certificate(certificate, program):
    """Keep the selected order/cuts; never search for a replacement certificate."""
    kind = certificate["kind"]
    order = certificate["commitOrder"]
    if kind == "original-serial":
        return {"kind": "original-program-serial", "commitOrder": order}
    require(kind in ("original-fixed-snapshot", "original-committed-query-prefixes"), "Unsupported original-program certificate")
    programs = []
    for row in certificate["programs"]:
        tx = row["transaction"]
        require(tx in program.txs, "Certificate names an unknown transaction")
        indices = [i for i, event in enumerate(program.txs[tx]["ops"])
                   if event["kind"] in ("row_read", "row_write")]
        if kind == "original-fixed-snapshot":
            cut = row["snapshotPrefix"]
            programs.append({"transaction": tx, "prefixes": [cut] * len(indices), "snapshot": cut})
        else:
            require([p["actionIndex"] for p in row["statementPrefixes"]] == indices,
                    "Certificate statement positions differ from the original program")
            programs.append({"transaction": tx, "prefixes": [p["prefix"] for p in row["statementPrefixes"]], "snapshot": None})
    return {"kind": "snapshot-prefix" if kind == "original-fixed-snapshot" else "committed-query-prefixes",
            "commitOrder": order, "programs": programs}


def compare_case(case, row, oracle):
    """Return accounting and genuine contradictions for one original history."""
    require(row.get("id") == case["id"], "SDK history identity differs")
    require(not row.get("error") and row.get("verified") is True, "SDK execution or source recomputation failed")
    source_digest = sha(compact(case["source"]).encode("utf8"))
    options_digest = sha(compact(canonical_options(case)).encode("utf8"))
    require(row.get("sourceSha256") == source_digest, "Original source bytes differ")
    require(row.get("options") == canonical_options(case), "Independently supplied options differ")
    # Earlier frozen receipts did not include this field. Their original options
    # are still compared above and independently bound in every new output row.
    if "optionsSha256" in row:
        require(row["optionsSha256"] == options_digest, "SDK options digest differs")
    report = row["report"]
    require(report.get("format") == "moontxnwitness-relation-model-composition/v4"
            and report.get("schemaVersion") == 4
            and report.get("referenceCommit") == REFERENCE_COMMIT
            and report.get("semanticContract") == "relation-predicate-models/v1", "Unsupported SDK relation report identity")
    models = report["models"]
    require(len(models) == len(oracle.MODELS) and {r["model"] for r in models} == set(oracle.MODELS),
            "SDK model universe is missing, duplicated or different")
    program = oracle.Program(oracle.decode(case["source"]))
    counts, categories, items, failures = Counter(), Counter(), [], []
    for modelrow in models:
        model, sdk_status = modelrow["model"], modelrow["status"]
        require(sdk_status in ("checked-compatible", "refuted", "unknown", "pending"), "Unsupported SDK model status")
        reference = oracle.analyze(case["source"], model, case["options"])
        reference_status = reference["status"]
        require(reference_status == case["expectedReferenceStatuses"][model], "Frozen independent expectation changed")
        counts[model + "/" + sdk_status + "/" + reference_status] += 1
        if sdk_status == "refuted" and reference_status == "checked-compatible":
            category = "contradiction"
            failures.append({"id": case["id"], "model": model, "kind": "sdk-refutation-conflicts-with-independent-certificate", "reference": reference, "sdk": modelrow})
        elif sdk_status == "checked-compatible" and reference_status == "refuted":
            category = "contradiction"
            failures.append({"id": case["id"], "model": model, "kind": "sdk-positive-conflicts-with-independent-refutation", "reference": reference, "sdk": modelrow})
        elif sdk_status in ("refuted", "checked-compatible") and sdk_status == reference_status:
            category = "determinate-agreement"
        elif sdk_status in ("unknown", "pending") and reference_status in ("checked-compatible", "refuted"):
            category = "conservative-sdk-unknown"
        elif sdk_status in ("unknown", "pending") and reference_status in ("unknown", "pending"):
            category = "both-undecided"
        else:
            category = "independent-reference-undecided"
        categories[category] += 1
        proof_status, proof_model = "not-positive", None
        if sdk_status == "checked-compatible":
            certificates = [r.get("evidence", {}).get("certificate") for r in modelrow["rules"] if r["status"] == "checked-compatible"]
            certificates = [c for c in certificates if isinstance(c, dict)]
            require(certificates, "SDK positive lacks an original-program certificate")
            priority = {"original-serial": 0, "original-fixed-snapshot": 1, "original-committed-query-prefixes": 2}
            require(all(c.get("kind") in priority for c in certificates), "Unsupported SDK certificate kind")
            certificate = min(certificates, key=lambda c: priority[c["kind"]])
            converted = translate_certificate(certificate, program)
            premise_only = certificate["kind"] == "original-committed-query-prefixes" and model not in oracle.RU_MODELS | oracle.RC_MODELS
            proof_model = "read-committed" if premise_only else model
            replay = oracle.verify_certificate(case["source"], proof_model, converted, case["options"])
            proof_status = "semantic-premises-only" if premise_only else "full-sufficient-certificate"
            categories["premise-certificate-replays" if premise_only else "model-certificate-replays"] += 1
            if not replay["valid"]:
                failures.append({"id": case["id"], "model": model, "kind": "independent-certificate-replay-failed", "certificate": converted, "replay": replay})
        items.append({"id": case["id"], "family": case["family"], "model": model,
                      "sourceSha256": source_digest, "optionsSha256": options_digest,
                      "sdkStatus": sdk_status, "referenceStatus": reference_status,
                      "referenceExactDecision": reference["exactDecision"], "referenceReason": reference.get("reason"),
                      "category": category, "independentCertificateScope": proof_status, "independentCertificateModel": proof_model})
    return items, counts, categories, failures


def compare_files(histories, sdk_results, output, *, count=None):
    oracle_path, generator_path = BASE / "relation-models-oracle.py", BASE / "relation-models-corpus.py"
    oracle = load_module(oracle_path, "maintained_independent_relation_reference")
    generator = load_module(generator_path, "maintained_frozen_relation_generator")
    original_bytes = histories.read_bytes()
    cases = decode_json(original_bytes)
    require(isinstance(cases, list) and 1 <= len(cases) <= MAX_CASES, "Frozen corpus must contain 1..1000 histories")
    expected_cases = [generator.generate(i, SEED) for i in range(len(cases))]
    expected_bytes = (json.dumps(expected_cases, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf8")
    require(original_bytes == expected_bytes, "Frozen source corpus bytes or seed differ")
    if len(cases) == MAX_CASES:
        require(sha(original_bytes) == FROZEN_1000_SHA256, "Frozen thousand-history digest differs")
    count = len(cases) if count is None else count
    require(type(count) is int and 1 <= count <= len(cases), "Comparison count is outside the frozen corpus")
    output.mkdir(exist_ok=False)
    tracked = {"histories": histories, "sdkResults": sdk_results, "oracle": oracle_path,
               "generator": generator_path, "comparisonDriver": Path(__file__).resolve()}
    before = {name: file_binding(path) for name, path in tracked.items()}
    counts, categories, failure_count, judged, legacy_options = Counter(), Counter(), 0, 0, 0
    with sdk_results.open("rb") as source, (output / "independent-comparison-items.jsonl").open("xb") as target, (output / "independent-failures.jsonl").open("xb") as failures:
        for index in range(count):
            line = source.readline(MAX_REPORT_LINE + 1)
            require(line and len(line) <= MAX_REPORT_LINE, "Missing or oversized SDK report row")
            row = decode_json(line)
            legacy_options += "optionsSha256" not in row
            items, pairs, current, errors = compare_case(cases[index], row, oracle)
            counts.update(pairs)
            categories.update(current)
            for item in items:
                target.write((compact(item) + "\n").encode("utf8"))
            for error in errors:
                failures.write((compact(error) + "\n").encode("utf8"))
            failure_count += len(errors)
            judged += len(items)
        require(source.read(1) == b"", "Unexpected extra SDK histories cannot be silently skipped")
    for name, path in tracked.items():
        require(before[name] == file_binding(path), "Comparison input changed: " + name)
    for name in ("relation-models-compare.py", "relation-models-oracle.py", "relation-models-corpus.py"):
        shutil.copyfile(BASE / name, output / name)
    summary = {"format": "moontxnwitness-original-program-independent-sdk-comparison/v2", "passed": failure_count == 0,
               "sdkExecutionVerifiedHere": False, "publicPackageVerified": False,
               "histories": count, "frozenInputHistories": len(cases), "seed": SEED, "judgments": judged,
               "failures": failure_count, "categories": dict(categories), "statusPairs": dict(counts),
               "legacyRowsWithoutOptionsDigest": legacy_options, "fullFourteenModelParity": False,
               "scope": "Exact original serial decisions, direct source findings and sufficient RC/SI certificates. Nonserial RR/CV prefixes replay RC semantic premises only; pending and unknown are not model parity.",
               "inputs": before, "independentResultsSha256": sha((output / "independent-comparison-items.jsonl").read_bytes())}
    (output / "independent-summary.json").write_text(json.dumps(summary, indent=2) + "\n", "utf8")
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--histories", type=Path, required=True)
    parser.add_argument("--sdk-results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="new output directory; originals are never overwritten")
    parser.add_argument("--count", type=int, help="explicit smoke subset; all supplied SDK rows must still be accounted for")
    args = parser.parse_args(argv)
    result = compare_files(args.histories.resolve(strict=True), args.sdk_results.resolve(strict=True), args.output.resolve(), count=args.count)
    print(json.dumps({k: result[k] for k in ("passed", "histories", "judgments", "failures", "categories", "fullFourteenModelParity")}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
