"""Remote, generation-only wrapper for the frozen Elle expansion preregistration.

No checker, SDK, database, JavaScript runtime or compiler is imported or run.
The fixed independent smoke receipt is consumed, never rewritten or re-signed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = Path("verification/experimental-candidates/elle-expansion-generation-v2-2026-10-21")
WORKFLOW = Path(".github/workflows/experimental-elle-expansion-generation.yml")
INDEX = "preregistration/candidate-index-static-v2.json"
INDEX_BINDING = {"bytes": 1534, "sha256": "24c9bf6da3aa35ebfa01d590e21acde3c15ef041e78c944b1a33cf208f0096b1"}
SMOKE_BINDINGS = {
    "smoke/comparison-first.json": {"bytes": 60730, "sha256": "f6e6c5d60ca46a832ac91a77b417eddf587d28e601c0c88621f3f8d9d0db292c"},
    "smoke/independent-smoke-receipt-r2.json": {"bytes": 23020, "sha256": "0ccfadc06cc1418e12896256acde09fa6db0c09dd65df431b11c5e7b9f5e2a89"},
    "smoke/audit-smoke-r2.py": {"bytes": 34275, "sha256": "fc41c98a35b8ba5f7fca9dbfa8c1eaee7cb6968e1c53bb345a693b7bf7d97419"},
}
SEED = "MoonTxnWitness-Elle-common-raw-20261021-v1"
SDK_SOURCE = "b6638ee56395a14284d1440a92a0d975c4ea4073f42ccab6d8d39e359d928096"
PREREGISTERED_FILES = {
    "README.md", "REVISION2.md", "contract.json", "contract-amendment-v2.json",
    "original-generate-v1.py", "generate.py", "previous-index-static-v1.json",
}
FAMILIES = {
    "point-register-v1": ("suffix-points", "repeat-points", "prefix-and-suffix", "multi-key-owners", "alternating-sources"),
    "append-list-v1": ("source-subsets", "reversed-observations", "repeated-observed-identity", "prefix-and-suffix", "mixed-list-orders"),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def bounded_read(path, maximum):
    require(path.is_file() and not path.is_symlink(), "Expected regular input: " + str(path))
    require(path.stat().st_size <= maximum, "Input exceeds bound before read: " + str(path))
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    require(len(raw) <= maximum, "Input grew beyond bound: " + str(path))
    return raw


def binding(path, maximum=64 * 1024 * 1024):
    require(path.is_file() and not path.is_symlink(), "Expected regular file: " + str(path))
    require(path.stat().st_size <= maximum, "File exceeds bound before hash: " + str(path))
    digest, size = hashlib.sha256(), 0
    with path.open("rb") as stream:
        while block := stream.read(65536):
            size += len(block)
            require(size <= maximum, "File grew beyond hash bound: " + str(path))
            digest.update(block)
    return {"bytes": size, "sha256": digest.hexdigest()}


def write_new(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=True)
        stream.write("\n")


def checked_input(base, name, expected):
    parts = Path(name).parts
    require(not Path(name).is_absolute() and all(part not in ("", ".", "..") for part in parts), "Unsafe input name")
    path = base / name
    require(not any(parent.is_symlink() for parent in [path, *path.parents]), "Input symlink refused")
    raw = bounded_read(path, expected["bytes"])
    actual = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    require(actual == expected, "Frozen input binding differs: " + name)
    return raw


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--work", required=True, type=Path)
    args = parser.parse_args()
    # This is a hard remote-only guard, not an independent acceptance claim.
    require(os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("RUNNER_OS") == "Linux"
            and os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch", "Manual Linux GitHub Actions only")
    require(re.fullmatch(r"[0-9a-fA-F]{40}", args.source_ref) is not None, "source_ref must be a full immutable40-hex commit")
    require(re.fullmatch(r"[0-9a-fA-F]{40}", os.environ.get("GITHUB_WORKFLOW_SHA", "")) is not None,
            "Actual workflow source commit must be recorded separately")
    source_ref = args.source_ref.lower()
    work = args.work.resolve()
    require(work.parent == Path(os.environ["RUNNER_TEMP"]).resolve(), "Work must be a direct RUNNER_TEMP child")
    require(work.name == "mtw-elle-expansion-generation-" + os.environ["GITHUB_RUN_ID"] + "-" + os.environ["GITHUB_RUN_ATTEMPT"], "Unique run/attempt work name required")
    work.mkdir(exist_ok=True)
    evidence = work / "evidence"
    evidence.mkdir(exist_ok=True)
    receipt_path = evidence / "generation-ci-receipt.json"
    require(not receipt_path.exists(), "An execution receipt already exists; never overwrite a prior attempt")
    result = {
        "schema": 1, "kind": "remote-fixed-Elle-expansion-generation-only", "passed": False,
        "sourceRefRequested": source_ref, "workflowEventCommit": os.environ.get("GITHUB_SHA"),
        "workflowSourceCommit": os.environ.get("GITHUB_WORKFLOW_SHA"),
        "workflowRef": os.environ.get("GITHUB_WORKFLOW_REF"),
        "runId": os.environ.get("GITHUB_RUN_ID"), "runAttempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "repository": os.environ.get("GITHUB_REPOSITORY"),
        "runUrl": os.environ["GITHUB_SERVER_URL"] + "/" + os.environ["GITHUB_REPOSITORY"] + "/actions/runs/" + os.environ["GITHUB_RUN_ID"],
        "started": datetime.now(timezone.utc).isoformat(), "pythonVersion": sys.version,
        "seed": SEED, "generatorInvocations": 0, "failures": [], "sourceInputs": {},
        "actualElleExecuted": False, "actualMoonBitExecuted": False, "actualDatabaseExecuted": False,
        "formalPerformanceMeasurement": False, "actualExpansionEvaluatorExecuted": False,
        "independentInputAuditPerformed": False, "independentHumanAcceptanceClaimed": False,
        "evaluatorMayRun": False, "nextGate": "independent-frozen-input-dedup-and-domain-audit",
    }
    expected_inputs = {}
    frozen = evidence / "frozen-input-sources"
    output = evidence / "generated-input-freeze"
    bundle = ROOT / BUNDLE
    try:
        require(not frozen.exists() and not output.exists(), "Fresh source copy and generator output required; preserve existing paths")
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                              capture_output=True, text=True, timeout=15).stdout.strip()
        require(head == source_ref, "Actual checkout differs from full source_ref")
        result.update(sourceCommitActual=head, runnerBinding=binding(Path(__file__), 1024 * 1024),
                      sourceRefWorkflowBinding=binding(ROOT / WORKFLOW, 1024 * 1024),
                      sourceCommitEqualsWorkflowSourceCommit=head == result["workflowSourceCommit"])
        index = json.loads(checked_input(bundle, INDEX, INDEX_BINDING))
        require(index.get("fileCount") == 7 and set(index.get("files", {})) == PREREGISTERED_FILES
                and index.get("totalBytes") == 33684, "Fixed seven-file source preregistration required")
        expected_inputs = {INDEX: INDEX_BINDING, **SMOKE_BINDINGS,
                           **{"preregistration/" + name: expected for name, expected in index["files"].items()}}
        require(sum(item["bytes"] for item in index["files"].values()) == 33684, "Preregistration byte total differs")
        for name, expected in expected_inputs.items():
            checked_input(bundle, name, expected)
            result["sourceInputs"][name] = expected
        result.update(sourceInputCount=len(expected_inputs), sourceInputBytes=sum(row["bytes"] for row in expected_inputs.values()))
        require(result["sourceInputCount"] == 11 and result["sourceInputBytes"] == 153243, "Fixed input bundle count/size differs")
        acceptance = json.loads(checked_input(bundle, "smoke/independent-smoke-receipt-r2.json", SMOKE_BINDINGS["smoke/independent-smoke-receipt-r2.json"]))
        require(acceptance.get("passed") is True and acceptance.get("complete") is True
                and acceptance.get("run") == 39599513353 and acceptance.get("checksCount") == 95
                and len(acceptance.get("checks", [])) == 95
                and all(row.get("passed") is True for row in acceptance["checks"])
                and acceptance.get("independentAIReview") is True
                and acceptance.get("independentHumanReview") is False
                and acceptance.get("booleanAgreementCases") == 6
                and acceptance.get("unknownCoverageDifferences") == 2
                and acceptance.get("actualComparison") == SMOKE_BINDINGS["smoke/comparison-first.json"]
                and acceptance.get("auditSource") == SMOKE_BINDINGS["smoke/audit-smoke-r2.py"], "Frozen independent AI smoke prerequisite differs")
        result["acceptedSmokePrerequisite"] = {
            "receiptBinding": SMOKE_BINDINGS["smoke/independent-smoke-receipt-r2.json"],
            "reviewerAsRecorded": acceptance["reviewer"], "independentAIReviewAsRecorded": True,
            "independentHumanReviewAsRecorded": False, "auditScriptExecutedDuringGeneration": False,
            "booleanAgreementCases": 6, "unknownCoverageDifferencesRetained": 2,
        }
        for name, expected in expected_inputs.items():
            destination = frozen / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(bundle / name, destination)
            checked_input(frozen, name, expected)
        generator = frozen / "preregistration/generate.py"
        private = ("TOKEN", "SECRET", "PASSWORD", "AUTHORIZATION", "PRIVATE_KEY")
        environment = {key: value for key, value in os.environ.items() if not any(word in key.upper() for word in private)}
        environment.pop("PYTHONPATH", None)
        environment.update(PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
        result["generatorInvocations"] = 1
        result["generatorTimeoutSeconds"] = 300
        with (evidence / "generation-first.log").open("xb") as stream:
            process = subprocess.run([sys.executable, "-I", "-B", str(generator),
                                      "--smoke-comparison", str(frozen / "smoke/comparison-first.json"),
                                      "--output", str(output)], cwd=work, env=environment,
                                     stdout=stream, stderr=subprocess.STDOUT, timeout=300)
        result["generatorExitCode"] = process.returncode
        require(process.returncode == 0, "First generation failed; retain its partial files, receipt and log")
        generation = json.loads(bounded_read(output / "generation-receipt.json", 1024 * 1024))
        expected_families = {(model, family): 200 for model, families in FAMILIES.items() for family in families}
        require(len(generation.get("families", [])) == 10
                and {(row["model"], row["family"]): row["accepted"] for row in generation["families"]} == expected_families,
                "Preregistered ten family quotas not met")
        dataset = binding(output / "inputs.jsonl", 33554432)
        require(generation.get("passed") is True and generation.get("records") == 2000
                and generation.get("exactUnique") == 2000 and generation.get("alphaProgramShapeUnique") == 2000
                and generation.get("bytes") == dataset["bytes"] and generation.get("datasetSha256") == dataset["sha256"]
                and generation.get("seed") == SEED
                and generation.get("generatorSha256") == expected_inputs["preregistration/generate.py"]["sha256"]
                and generation.get("contractSha256") == expected_inputs["preregistration/contract.json"]["sha256"]
                and generation.get("contractAmendmentSha256") == expected_inputs["preregistration/contract-amendment-v2.json"]["sha256"]
                and generation.get("smokeComparisonSha256") == SMOKE_BINDINGS["smoke/comparison-first.json"]["sha256"]
                and generation.get("smokeSdkSourceFingerprint") == SDK_SOURCE
                and generation.get("actualElleExecutedDuringGeneration") is False
                and generation.get("actualMoonBitExecutedDuringGeneration") is False,
                "First generation receipt differs from frozen authoring contract")
        result.update(passed=True, datasetBinding=dataset, generatorReportedRecords=2000,
                      generatorReportedExactUnique=2000, generatorReportedAlphaProgramShapeUnique=2000,
                      generatorReportedFamilyQuotas=generation["families"])
    except Exception as error:
        result["failures"].append({"class": type(error).__name__, "message": str(error)})
        result["passed"] = False
    finally:
        for name, expected in expected_inputs.items():
            try:
                checked_input(bundle, name, expected)
                if frozen.exists():
                    checked_input(frozen, name, expected)
            except Exception as error:
                result["failures"].append({"class": type(error).__name__, "message": str(error)})
                result["passed"] = False
        inventory = {}
        for path in sorted(evidence.rglob("*")):
            # tee is still writing this outer log until this process exits.
            # The workflow seals it in a separate, generation-free final step.
            if path.is_file() and path != evidence / "runner-first.log":
                try:
                    inventory[path.relative_to(evidence).as_posix()] = binding(path)
                except Exception as error:
                    result["failures"].append({"class": type(error).__name__, "message": str(error)})
                    result["passed"] = False
        manifest_path = evidence / "generation-freeze-manifest.json"
        manifest = {
            "schema": 1, "kind": "author-generation-byte-freeze-before-independent-input-review",
            "passed": result["passed"], "sourceCommit": result.get("sourceCommitActual"),
            "workflowSourceCommit": result["workflowSourceCommit"], "workflowEventCommit": result["workflowEventCommit"],
            "sourceInputs": result["sourceInputs"], "files": inventory,
            "generatorInvocations": result["generatorInvocations"],
            "inputHashesAndShapeHashesLocation": "generated-input-freeze/inputs.jsonl",
            "shapeDefinition": "fixed-first-occurrence-alpha-program; not full graph isomorphism",
            "workflowLogBindingLocation": "workflow-log-bindings.json; written after the runner exits",
            "independentInputAuditPerformed": False, "actualExpansionEvaluatorExecuted": False,
            "evaluatorMayRun": False, "failures": result["failures"],
        }
        write_new(manifest_path, manifest)
        result["freezeManifestBinding"] = binding(manifest_path, 1024 * 1024)
        result["completed"] = datetime.now(timezone.utc).isoformat()
        write_new(receipt_path, result)
    print(json.dumps({"passed": result["passed"], "generatorInvocations": result["generatorInvocations"]}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
