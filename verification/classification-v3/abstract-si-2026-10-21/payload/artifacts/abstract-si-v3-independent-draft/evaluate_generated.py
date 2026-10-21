"""Evaluate every frozen case once and retain all output statuses and witnesses."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from oracle import analyze, verify_witness


ROOT = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def factual_features(record):
    value = record["input"]
    final, sources = {}, {}
    total_ops, writes, repeated_reads, future_reads = 0, 0, 0, 0
    for key, version in value["initial"].items():
        sources[(key, version)] = (None, None)
    for tx in value["transactions"]:
        last_read = {}
        for index, op in enumerate(tx["ops"]):
            total_ops += 1
            if op["type"] == "write":
                writes += 1
                sources[(op["key"], op["version"])] = (tx["id"], index)
                final[(tx["id"], op["key"])] = op["version"]
            else:
                repeated_reads += op["key"] in last_read
                last_read[op["key"]] = op["version"]
    for tx in value["transactions"]:
        for index, op in enumerate(tx["ops"]):
            if op["type"] == "read":
                writer, producer = sources.get((op["key"], op["version"]), (None, None))
                future_reads += writer == tx["id"] and producer > index
    if set(value["versionOrders"]) != set(value["initial"]):
        raise ValueError("Generated history has a missing key order")
    for key, order in value["versionOrders"].items():
        expected = {value["initial"][key]} | {version for (_, k), version in final.items() if k == key}
        if not order or order[0] != value["initial"][key] or len(order) != len(set(order)) or set(order) != expected:
            raise ValueError("Generated history lacks complete factual final-write order")
    return {"operations": total_ops, "transactions": len(value["transactions"]),
        "keys": len(value["initial"]), "intermediateWrites": writes - len(final),
        "repeatedReads": repeated_reads, "ownFutureReadSources": future_reads,
        "repeatedPayloadSidecar": bool(record["businessValueFacts"])}


def main():
    output = ROOT / "generated-evaluation-v1.jsonl"
    receipt_file = ROOT / "generated-evaluation-v1-receipt.json"
    if output.exists() or receipt_file.exists():
        raise SystemExit("Refusing to replace prior generated evaluation")
    inputs = ROOT / "generated-inputs-v1.jsonl"
    manifest = json.loads((ROOT / "generated-inputs-v1-manifest.json").read_text())
    amendment = json.loads((ROOT / "generation-plan-amendment-v2.json").read_text())
    plan = json.loads((ROOT / "generation-plan-v1.json").read_text())
    if sha(inputs) != manifest["sha256"] or sha(inputs) != amendment["inputSha256"]:
        raise SystemExit("Frozen inputs changed")
    records = [json.loads(line) for line in inputs.read_text().splitlines()]
    quotas = {row["family"]: row["count"] for row in plan["quotas"]}
    actual_quotas = dict(Counter(record["family"] for record in records))
    if actual_quotas != quotas or len(records) != amendment["correction"]["corrected"]:
        raise SystemExit("Registered amended count/quota mismatch")
    frozen_names = ("contract-v1.json", "preregistration-v1.json", "generation-plan-v1.json",
        "generation-plan-first-inconsistency.json", "generation-plan-amendment-v2.json",
        "oracle.py", "generate_histories.py", "evaluate_generated.py", "generated-inputs-v1.jsonl",
        "generated-inputs-v1-manifest.json", "frozen-boundaries-v1.json")
    source_bindings = {name: sha(ROOT / name) for name in frozen_names}
    counts = {model: Counter() for model in ("si", "serial")}
    family_counts = {model: defaultdict(Counter) for model in counts}
    bases = {model: Counter() for model in counts}
    budget_unknowns = {model: 0 for model in counts}
    findings = {model: Counter() for model in counts}
    witnesses = {model: 0 for model in counts}
    unresolved = {model: 0 for model in counts}
    feature_totals, feature_histories = Counter(), Counter()
    maxima = Counter()
    max_states, max_checks = Counter(), Counter()
    errors, construction_checks = [], 0
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        for record in records:
            text = canonical(record["input"])
            if hashlib.sha256(text.encode()).hexdigest() != record["inputSha256"]:
                raise ValueError("Per-input digest changed: " + record["id"])
            features = factual_features(record)
            for key, value in features.items():
                if key in ("operations", "transactions", "keys"):
                    maxima[key] = max(maxima[key], value)
                else:
                    feature_totals[key] += value
                    feature_histories[key] += bool(value)
            item = {"id": record["id"], "inputSha256": record["inputSha256"],
                "family": record["family"], "features": features, "results": {}}
            if record["constructionWitness"] is not None:
                construction_checks += 1
                valid = verify_witness(text, record["constructionWitness"],
                    model="serial" if record["family"] == "constructed-serial" else "si")
                item["constructionWitnessValid"] = valid
                if not valid:
                    errors.append({"id": record["id"], "kind": "invalid-construction-witness"})
            for model, expected_field in (("si", "expectedSi"), ("serial", "expectedSerial")):
                report = analyze(text, model=model, **record["options"])
                status, expected = report["status"], record[expected_field]
                counts[model][status] += 1
                family_counts[model][record["family"]][status] += 1
                bases[model][report["execution"]["decisionBasis"]] += 1
                max_states[model] = max(max_states[model], report["execution"]["states"])
                max_checks[model] = max(max_checks[model], report["execution"]["semanticChecks"])
                budget_unknown = status == "inconclusive" and report["execution"]["budgetExhausted"]
                budget_unknowns[model] += budget_unknown
                evidence_valid = None
                if status == "satisfiable":
                    witnesses[model] += 1
                    evidence_valid = verify_witness(text, report["witness"], model=model)
                    if model == "serial":
                        evidence_valid = evidence_valid and verify_witness(text, report["witness"], model="si")
                    if not evidence_valid:
                        errors.append({"id": record["id"], "model": model, "kind": "invalid-returned-witness"})
                elif report["witness"] is not None:
                    errors.append({"id": record["id"], "model": model, "kind": "witness-on-non-satisfiable"})
                for finding in report["findings"]:
                    findings[model][finding["kind"]] += 1
                if expected is not None and status != expected:
                    if budget_unknown and expected in ("satisfiable", "unsatisfiable"):
                        unresolved[model] += 1
                    else:
                        errors.append({"id": record["id"], "model": model, "kind": "preregistered-expectation-mismatch",
                            "expected": expected, "actual": status})
                if status == "invalid":
                    errors.append({"id": record["id"], "model": model, "kind": "invalid-supported-generated-input"})
                if report["execution"]["states"] > report["execution"]["maxStates"] or report["execution"]["semanticChecks"] > report["execution"]["maxSemanticChecks"]:
                    errors.append({"id": record["id"], "model": model, "kind": "counter-exceeds-budget"})
                item["results"][model] = {"expected": expected, "witnessVerified": evidence_valid,
                    "unresolvedExpectedTruthByBudget": budget_unknown and expected in ("satisfiable", "unsatisfiable"),
                    "report": report}
            stream.write(canonical(item) + "\n")
    source_changes = [name for name, digest in source_bindings.items() if sha(ROOT / name) != digest]
    if source_changes:
        errors.append({"kind": "source-changed-during-functional-evaluation", "files": source_changes})
    receipt = {"schema": 1, "phase": "private-reference-generated-functional-evaluation",
        "passed": not errors, "histories": len(records), "modelInvocations": 2 * len(records),
        "uniqueInputHashes": len({record["inputSha256"] for record in records}),
        "uniqueProgramShapes": len({record["programShapeSha256"] for record in records}),
        "statusCounts": {model: dict(value) for model, value in counts.items()},
        "familyStatusCounts": {model: {family: dict(value) for family, value in rows.items()}
            for model, rows in family_counts.items()},
        "decisionBasisCounts": {model: dict(value) for model, value in bases.items()},
        "findingCounts": {model: dict(value) for model, value in findings.items()},
        "budgetExhaustedUnknowns": budget_unknowns, "unresolvedExpectedTruthByBudget": unresolved,
        "verifiedReturnedWitnesses": witnesses, "verifiedConstructedWitnesses": construction_checks,
        "featuresSummed": dict(feature_totals), "historiesWithFeatures": dict(feature_histories),
        "maximumInputDimensions": dict(maxima), "maximumStates": max_states,
        "maximumSemanticChecks": max_checks, "errors": errors,
        "inputManifest": "generated-inputs-v1-manifest.json", "sourceSha256": source_bindings,
        "output": {"path": output.name, "bytes": output.stat().st_size, "sha256": sha(output)},
        "productionOutputsConsulted": False, "databaseExecuted": False,
        "elleExecuted": False, "formalPerformanceMeasured": False,
        "independentPeerReviewCompleted": False, "productionModelCoverageAccepted": False,
        "limits": "All unknowns and outputs retained; this author-written reference/self-check is not an independent audit of the production classifier."}
    receipt_file.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(receipt, sort_keys=True))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
