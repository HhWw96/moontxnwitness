"""Read-only campaign collection. Recheck original ledgers/files, never call a checker."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

PIN = "4f9a73a5fe82478d913cb751ab68714d4ba0558c85b45a3933c6eb9a6c3078ef"



def completion_flags(report, results, directories, issues):
    all_present = directories == 40 and len(results) == 40
    returned = (all_present and not issues and all(r["transportIntegrity"] for r in results.values())
                and report["actualElleReturnedInputs"] == 2000)
    process_ok = all_present and all(r.get("process", {}).get("exitCode") == 0
                     and r.get("process", {}).get("stopReason") is None
                     and not r.get("process", {}).get("rawStreamsMayBeTruncated")
                     and not r.get("process", {}).get("controllerErrors")
                     for r in results.values())
    terminal = {"returned-true", "returned-false", "returned-unknown",
                "returned-true-with-cycle-timeout", "returned-false-with-cycle-timeout"}
    return {"fullCampaignReturned": returned, "allBatchProcessesSucceeded": process_ok,
            "fullCampaignTransportComplete": returned and process_ok
                and all(r["status"] in terminal for r in report["cases"])}


def main():
    parser = argparse.ArgumentParser()
    for name in ("campaign", "campaign-sha256", "controller", "outputs-root", "output"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--runtime-sha256")
    args = parser.parse_args()
    source = Path(args.controller).read_bytes()
    if hashlib.sha256(source).hexdigest() != PIN:
        raise ValueError("Externally reviewed controller source differs")
    core = {"__name__": "verified_r4_collector_core", "__file__": args.controller,
            "__verified_source_sha256__": PIN}
    exec(compile(source, args.controller, "exec"), core)
    read = core["read_pinned"]
    campaign_raw = read(args.campaign, args.campaign_sha256, 2 * 1024 * 1024)
    campaign = core["decode"](campaign_raw)
    if campaign["controllerSha256"] != PIN or campaign["expectedInputCount"] != 2000:
        raise ValueError("Exact reviewed fixed2000 campaign required")
    root = Path(args.outputs_root)
    if root.is_symlink():
        raise ValueError("Owned output root cannot be a symlink")
    root = root.resolve()
    plans_root = Path(args.campaign).resolve().parent
    groups, results, issues = {}, {}, []
    actual_directories = 0
    for batch in campaign["batches"]:
        plan_path = (plans_root / batch["planPath"]).resolve()
        if not plan_path.is_relative_to(plans_root):
            raise ValueError("Plan escapes reviewed root")
        plan = core["decode"](read(plan_path, batch["planSha256"], 1024 * 1024))
        if plan["controllerSha256"] != PIN or plan["wrapperSha256"] != campaign["wrapperSha256"]:
            raise ValueError("Execution source binding differs")
        name, cases = batch["name"], plan["cases"]
        groups[name] = cases
        relative = Path(batch["outputDirectory"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Unsafe owned output path")
        output = root / relative
        if not output.exists():
            continue
        actual_directories += 1
        try:
            if output.is_symlink() or not output.resolve().is_relative_to(root):
                raise ValueError("Output path escapes owner")
            if not args.runtime_sha256 or len(args.runtime_sha256) != 64:
                raise ValueError("Actual externally frozen runtime pin required")
            registration = core["decode"]((output / "registration.json").read_bytes())
            if (registration["planSha256"] != batch["planSha256"]
                    or registration["cases"] != cases
                    or registration["controllerSha256"] != PIN
                    or registration["wrapperStdin"]["sha256"] != campaign["wrapperSha256"]
                    or registration["runtimeManifestSha256"] != args.runtime_sha256):
                raise ValueError("Actual execution registration differs")
            previous_raw = (output / "accounting.json").read_bytes()
            if len(previous_raw) > 4 * 1024 * 1024:
                raise ValueError("Accounting size budget")
            previous = core["decode"](previous_raw)
            if previous["registrationSha256"] != core["binding"](output / "registration.json")["sha256"]:
                raise ValueError("Registration bytes changed")
            process = previous["process"]
            for filename, expected in process.get("logBindings", {}).items():
                if filename not in ("stdout.raw", "stderr.raw"):
                    raise ValueError("Unexpected process stream")
                stream = read(output / filename, expected["sha256"], 8 * 1024 * 1024)
                if len(stream) != expected["bytes"]:
                    raise ValueError("Process stream size differs")
            results[name] = core["account"](cases, output / "ledger.jsonl", output / "summaries",
                                            output / "raw", registration["runId"], process)
        except (KeyError, TypeError, ValueError, OSError, UnicodeError) as error:
            issues.append({"batch": name, "class": type(error).__name__, "message": str(error)})
            results[name] = {"transportIntegrity": False, "cases": [
                dict(case, status="batch-collection-failure", actualCheckerReturned=False,
                     actualCheckerInvocationAttempted=False, comparisonEligible=False) for case in cases]}
    if len(groups) != 40:
        raise ValueError("All40 original batches must be enumerated")
    report = core["campaign_account"](groups, results)
    report.update(schema=1, kind="fixed2000-r4-retained-evidence-collection",
                  campaignSha256=args.campaign_sha256, actualOutputDirectories=actual_directories,
                  runtimeManifestSha256=args.runtime_sha256, collectionIssues=issues,
                  actualJVMExecutedByCollector=False, actualSDKExecuted=False,
                  semanticComparisonPerformed=False,
                  originalInputsGeneratedOrChanged=False,
                  allBatchesPresent=(actual_directories == 40),
                  allTransportIntegrity=all(r["transportIntegrity"] for r in results.values()))
    report.update(completion_flags(report, results, actual_directories, issues))
    core["write_new"](args.output, core["json_bytes"](report))
    print(json.dumps({k: report[k] for k in ("inputsAccounted", "actualOutputDirectories",
                     "actualElleReturnedInputs", "fullCampaignReturned")}))
    return 0 if report["fullCampaignTransportComplete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
