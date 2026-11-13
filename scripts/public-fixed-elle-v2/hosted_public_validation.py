#!/usr/bin/env python3
"""Read-only anonymous public-download validation of the fixed Elle v2 corpus.

Runs only trusted, source-commit-bound verification tools and the SHA-pinned
published SDK. No author SDK, original campaign ZIP, JAR, token or cookie is used.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import ssl
import stat
import subprocess
import sys
import urllib.parse
import urllib.request
import zipfile

REPOSITORY = "HhWw96/moontxnwitness"
VERSION = "0.5.0"
LIBRARY_SOURCE = "6fd3410b6eae0efd399ba23f459c37ce29e6c46a"
DATA_TAG = "validation-elle-fixed2000-v2"
DATA_URL = f"https://github.com/{REPOSITORY}/releases/download/{DATA_TAG}/data.zip"
PORTABLE_URL = f"https://github.com/{REPOSITORY}/releases/download/v{VERSION}/MoonTxnWitness-v{VERSION}-portable.zip"
DATA_BYTES, DATA_SHA = 6288335, "5ba35b53d4e26abc2b7d8c76a82020fab64ea31b627b19c47e62dbb5128c0c91"
PORTABLE_BYTES, PORTABLE_SHA = 109323134, "c1203f3a9880f41e1c639aed58860008094bc02b15332a28e3f9a376237f66e1"
BUNDLE_SHA = "f3a46e697c74a1ef03e33d2803adbc495040e274f3a315a00cf2002dd3d8b89d"
REFERENCE_SHA = "d3ebd816971668eb4b7347987b73bc05bf959bc93d2d58e789afc44892acae97"
JOB_SHA = "3b78df6d0eb7d74be56cd6946231d52778b3c0159ba40c9bb00a90ce3ac6b338"
TRUSTED_TOOLS = {
    "verify_offline_bundle.py": "17cd1c91f7c8ad74448fd16d7e3bab5bb26decd70ce2a416a69072486594b491",
    "compare_sdk_v2.mjs": "4f2537a6946284c86f3d085d3d05eb295c572178358241425b6d14b0fd23635f",
    "compare_sdk_v2_worker.mjs": "391f38be5db88e9f2344369253c92d431e05e80247b110afe0c937f1c25cd09d",
}
ALLOWED_HOSTS = {"github.com", "api.github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}
MiB = 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(MiB), b""):
            value.update(chunk)
    return value.hexdigest()


def strict_json(data):
    def pairs(values):
        result = {}
        for key, value in values:
            require(key not in result, "duplicate JSON field")
            result[key] = value
        return result
    def number(text):
        value = float(text)
        require(math.isfinite(value), "nonfinite JSON float")
        return value
    def constant(text):
        raise ValueError("nonfinite JSON constant: " + text)
    return json.loads(data, object_pairs_hook=pairs, parse_float=number, parse_constant=constant)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as target:
        json.dump(value, target, sort_keys=True, indent=2, allow_nan=False)
        target.write("\n")


def checked_url(url):
    parsed = urllib.parse.urlsplit(url)
    require(parsed.scheme == "https" and parsed.hostname in ALLOWED_HOSTS
            and parsed.username is None and parsed.password is None and parsed.port in (None, 443),
            "HTTPS public GitHub destination required")
    require(not parsed.fragment, "URL fragment forbidden")
    return parsed


class PublicRedirects(urllib.request.HTTPRedirectHandler):
    max_redirections = 5
    max_repeats = 1

    def redirect_request(self, request, response, code, message, headers, newurl):
        checked_url(newurl)
        require(not any(key.lower() in {"authorization", "cookie", "proxy-authorization"} for key in request.headers),
                "authenticated redirect forbidden")
        return super().redirect_request(request, response, code, message, headers, newurl)


def public_opener():
    # No ambient proxy, cookie jar, authentication handler, netrc or gh client.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), PublicRedirects(),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    opener.addheaders = []
    return opener


def request(url, metadata=False):
    checked_url(url)
    return urllib.request.Request(url, headers={"User-Agent": "MoonTxnWitness-public-fixed2000-verifier",
        "Accept": "application/vnd.github+json" if metadata else "application/octet-stream", "Accept-Encoding": "identity"})


def download(url, target, expected_bytes, expected_sha, opener=None):
    require(not target.exists(), "fresh download target required")
    opener = opener or public_opener()
    value, length = hashlib.sha256(), 0
    target.parent.mkdir(parents=True, exist_ok=True)
    with opener.open(request(url), timeout=60) as response:
        require(response.status == 200, "complete HTTP 200 response required")
        final = checked_url(response.geturl())
        require(response.headers.get("Content-Encoding", "identity") == "identity", "unexpected transfer encoding")
        declared = response.headers.get("Content-Length")
        if declared is not None:
            require(re.fullmatch("[0-9]+", declared) and int(declared) == expected_bytes, "HTTP length differs")
        with target.open("xb") as output:
            while True:
                chunk = response.read(min(MiB, expected_bytes - length + 1))
                if not chunk:
                    break
                length += len(chunk)
                require(length <= expected_bytes, "download size budget exceeded")
                value.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
    require(length == expected_bytes and value.hexdigest() == expected_sha, "public download SHA/length differs")
    return {"url": url, "finalHost": final.hostname, "bytes": length, "sha256": value.hexdigest(),
            "anonymous": True, "authorizationSupplied": False, "cookiesSupplied": False}


def public_json(url, opener=None):
    opener = opener or public_opener()
    with opener.open(request(url, metadata=True), timeout=60) as response:
        require(response.status == 200, "public metadata HTTP status")
        checked_url(response.geturl())
        data = response.read(MiB + 1)
        require(len(data) <= MiB, "public metadata byte limit")
    return strict_json(data)


def verify_library_tag(opener=None):
    root = f"https://api.github.com/repos/{REPOSITORY}/git"
    ref = public_json(root + "/ref/tags/v" + VERSION, opener)
    require(ref.get("ref") == "refs/tags/v" + VERSION, "public library tag identity")
    obj, observed, seen = ref["object"], [ref], set()
    for _ in range(5):
        require(type(obj) is dict and re.fullmatch("[a-f0-9]{40}", obj.get("sha", "")), "tag object SHA")
        if obj.get("type") == "commit":
            require(obj["sha"] == LIBRARY_SOURCE, "public library tag moved")
            return {"tag": "v" + VERSION, "actualCommit": obj["sha"], "metadata": observed,
                    "dataReleaseTargetRequiredToEqualLibrarySource": False}
        require(obj.get("type") == "tag" and obj["sha"] not in seen, "unsupported/cyclic tag object")
        seen.add(obj["sha"])
        tag = public_json(root + "/tags/" + obj["sha"], opener)
        require(tag.get("sha") == obj["sha"], "annotated tag binding")
        observed.append(tag)
        obj = tag["object"]
    raise ValueError("annotated tag depth exceeded")


def member_path(name):
    require(type(name) is str and name and not name.startswith(("/", "\\"))
            and "\\" not in name and ":" not in name and "\0" not in name, "unsafe ZIP path")
    parts = name.split("/")
    require(all(part not in ("", ".", "..") and not part.endswith((".", " ")) for part in parts), "noncanonical ZIP path")
    require(not any(re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", p) for p in parts), "device ZIP path")
    return PurePosixPath(name)


class SafeZip:
    def __init__(self, path, expected_bytes, expected_sha, prefix, *, max_member=512 * MiB, max_expanded=4 * 1024 * MiB):
        require(path.stat().st_size == expected_bytes and file_digest(path) == expected_sha, "ZIP transport pin differs")
        self.zip = zipfile.ZipFile(path)
        self.prefix = prefix
        rows = self.zip.infolist()
        require(1 <= len(rows) <= 50000, "ZIP file-count budget")
        self.rows, expanded, folded = {}, 0, set()
        for info in rows:
            name = info.orig_filename
            member_path(name)
            require(name == info.filename and name.startswith(prefix), "ZIP root/normalization differs")
            require(name not in self.rows and name.casefold() not in folded, "duplicate/case-colliding ZIP member")
            require(not info.is_dir() and not info.flag_bits & 1, "directory/encrypted ZIP member unsupported")
            mode = stat.S_IFMT(info.external_attr >> 16)
            require(mode in (0, stat.S_IFREG), "ZIP links/special files forbidden")
            require(info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED), "unsupported ZIP compression")
            require(0 <= info.file_size <= max_member, "ZIP member-size budget")
            expanded += info.file_size
            require(expanded <= max_expanded, "ZIP expansion budget")
            self.rows[name] = info
            folded.add(name.casefold())
        self.expanded = expanded
        self.inventory = {}
        for name, info in self.rows.items():
            value, count = hashlib.sha256(), 0
            with self.zip.open(info) as source:
                for chunk in iter(lambda: source.read(MiB), b""):
                    count += len(chunk)
                    require(count <= info.file_size, "ZIP member exceeded declared size")
                    value.update(chunk)
            require(count == info.file_size, "ZIP member truncated")
            self.inventory[name] = {"bytes": count, "sha256": value.hexdigest()}

    def read(self, name, limit=8 * MiB):
        require(name in self.rows and self.rows[name].file_size <= limit, "missing/oversized required ZIP member")
        data = self.zip.read(self.rows[name])
        require({"bytes": len(data), "sha256": digest(data)} == self.inventory[name], "ZIP re-read differs")
        return data

    def extract(self, names, output):
        require(not output.exists(), "fresh extraction root required")
        output.mkdir(parents=True)
        base = output.resolve()
        for name in names:
            require(name in self.rows, "extraction member missing")
            relative = name[len(self.prefix):]
            member_path(relative)
            target = (base / relative).resolve()
            require(target.is_relative_to(base), "extraction escaped root")
            target.parent.mkdir(parents=True, exist_ok=True)
            with self.zip.open(self.rows[name]) as source, target.open("xb") as dest:
                for chunk in iter(lambda: source.read(MiB), b""):
                    dest.write(chunk)
            require(file_digest(target) == self.inventory[name]["sha256"], "extracted bytes differ")


def validate_data(archive):
    prefix = archive.prefix
    manifest_bytes = archive.read(prefix + "bundle-manifest.json")
    require(digest(manifest_bytes) == BUNDLE_SHA, "sealed data manifest pin")
    manifest = strict_json(manifest_bytes)
    require(manifest["semanticContract"] == "retained-elle-reference-evidence-bundle/v1"
            and manifest["referenceSha256"] == REFERENCE_SHA, "sealed data contract/reference")
    require(archive.read(prefix + "bundle-manifest.sha256") == (BUNDLE_SHA + "  bundle-manifest.json\n").encode(), "sealed sidecar differs")
    expected = {prefix + path for path in manifest["files"]} | {prefix + "bundle-manifest.json", prefix + "bundle-manifest.sha256"}
    require(set(archive.rows) == expected, "data contains unindexed/missing files")
    for path, binding in manifest["files"].items():
        member_path(path)
        require(archive.inventory[prefix + path] == binding, "sealed data member binding differs")
    require(archive.inventory[prefix + "fixed2000-job.original.json"]["sha256"] == JOB_SHA, "original job pin")
    require(archive.inventory[prefix + "upstream-reference-v2.json"]["sha256"] == REFERENCE_SHA, "original reference pin")
    return manifest


def validate_portable(archive):
    prefix = archive.prefix
    package = strict_json(archive.read(prefix + "package.json", MiB))
    manifest = strict_json(archive.read(prefix + "dist/build-manifest.json", MiB))
    require(package.get("version") == VERSION and manifest.get("version") == VERSION, "public portable version differs")
    require(re.fullmatch("[a-f0-9]{64}", manifest.get("sourceSha256", "")), "portable source fingerprint")
    require(manifest.get("toolchain", {}).get("compiler") == "v0.10.16+b1a0e846e", "portable compiler differs")
    bindings = {"core.mjs": manifest.get("coreSha256"), "capture-core.mjs": manifest.get("captureCoreSha256")}
    configured = manifest.get("configuredCoreSha256")
    require(type(configured) is dict and configured, "configured core inventory required")
    bindings.update(configured)
    for name, expected in bindings.items():
        require(re.fullmatch(r"[a-z0-9-]+\.mjs", name) and type(expected) is str
                and re.fullmatch("[a-f0-9]{64}", expected), "invalid portable core binding")
        item = archive.inventory.get(prefix + "dist/" + name)
        require(item is not None and item["sha256"] == expected, "portable manifest/core SHA differs")
    require(prefix + "dist/models-v4.mjs" in archive.rows, "portable model SDK missing")
    return manifest


def tool_bindings(tools):
    result = {}
    for name, expected in TRUSTED_TOOLS.items():
        path = (tools / name).resolve(strict=True)
        require(path.parent == tools and file_digest(path) == expected, "trusted verifier tool differs: " + name)
        result[name] = expected
    result[Path(__file__).name] = file_digest(Path(__file__))
    return result


def subprocess_environment():
    return {k: os.environ[k] for k in os.environ
        if not re.search(r"TOKEN|SECRET|PASSWORD|CREDENTIAL|AUTH|COOKIE", k, re.I)
        and k not in {"NODE_OPTIONS", "NODE_PATH", "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP"}}


def run_command(argv, log, cwd, seconds):
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("xb") as output:
        result = subprocess.run([str(x) for x in argv], cwd=cwd, env=subprocess_environment(),
                                stdout=output, stderr=subprocess.STDOUT, timeout=seconds, check=False)
    require(result.returncode == 0, "verification command failed; retained log: " + log.name)


def validate_comparison(path, runtime_files, job, reference):
    summary = strict_json((path / "summary.json").read_bytes())
    require(summary["version"] == VERSION and summary["runtimeOrigin"] == "public-download"
            and summary["runtimeFilesUnchanged"] is True and summary["runtime"]["files"] == runtime_files,
            "actual public SDK/runtime binding differs")
    require(summary["referenceSha256"] == REFERENCE_SHA and summary["jobSha256"] == JOB_SHA
            and summary["models"] == ["serializable"] and summary["listProfile"] == "captured-list-original-serial/v1",
            "comparison caller scope differs")
    require(summary["completed"] == summary["classifications"] == summary["verifications"] == 2000
            and summary["upstreamEligible"] == 1997 and summary["upstreamNotComparable"] == 3, "comparison incomplete/denominator changed")
    items_bytes = (path / "items.jsonl").read_bytes()
    require(digest(items_bytes) == summary["itemSha256"] and len(items_bytes.splitlines()) == 2000, "complete item stream binding")
    items = [strict_json(line) for line in items_bytes.splitlines()]
    report_path = path / "reports.jsonl.gz"
    require(file_digest(report_path) == summary["reportsGzipSha256"], "complete retained report gzip binding")
    value, count, lines = hashlib.sha256(), 0, 0
    outcomes = {key: 0 for key in ["match", "difference", "sdkUnknown", "upstreamNotComparable", "timeout", "failure"]}
    eligible_outcomes = dict(outcomes)
    by_data_model = {"point-register-v1": dict(outcomes), "append-list-v1": dict(outcomes)}
    sdk_dispositions = {key: 0 for key in ["complete", "unknown", "timeout", "failure"]}
    with gzip.open(report_path, "rb") as stream:
        while line := stream.readline(64 * MiB + 1):
            require(len(line) <= 64 * MiB and line.endswith(b"\n"), "retained report line budget/truncation")
            count += len(line)
            require(count <= 1024 * MiB, "retained report expansion budget")
            value.update(line)
            entry = strict_json(line)
            require(lines < 2000, "extra retained report")
            item, original, upstream = items[lines], job[lines], reference["cases"][lines]
            require(entry["item"] == item and item["id"] == original["id"] == upstream["id"]
                    and item["inputSha256"] == original["inputSha256"] == upstream["inputSha256"]
                    and item["dataModel"] == original["input"]["dataModel"], "report/item original identity differs")
            require(entry["input"] == original["input"] and entry["upstreamReference"] == upstream
                    and digest(entry["sourceText"].encode()) == original["inputSha256"], "retained input/reference differs")
            require(digest(entry["upstreamRawEdn"].encode()) == upstream["raw"]["sha256"]
                    and digest(entry["upstreamSummaryText"].encode()) == upstream["summary"]["sha256"], "retained upstream raw/summary differs")
            require(item["referenceEligible"] is upstream["comparisonEligible"]
                    and item["upstreamValidity"] is upstream["validity"]
                    and item["upstreamCycleSearchTimeout"] is upstream["cycleSearchTimeout"]
                    and item["classificationAttempted"] is True and item["verificationAttempted"] is True,
                    "reference eligibility/actual SDK calls differ")
            options = {"models": ["serializable"], "maxSourceChecks": 1000000, "maxStates": 100000, "maxEdgeChecks": 1000000}
            if original["input"]["dataModel"] == "append-list-v1":
                options["listProfile"] = "captured-list-original-serial/v1"
            require(item["callerOptions"] == options, "actual independently supplied caller options differ")
            require(type(entry["sdkReportText"]) is str and digest(entry["sdkReportText"].encode()) == item["reportSha256"]
                    and entry["sdkVerification"]["valid"] is True, "complete verified SDK report required")
            report = strict_json(entry["sdkReportText"])
            require(report["format"] == "moontxnwitness-model-composition/v4" and report["schemaVersion"] == 4
                    and len(report["models"]) == 1 and report["models"][0]["model"] == "serializable", "actual SDK model scope differs")
            status = report["models"][0]["status"]
            require(status in ("checked-compatible", "refuted", "unknown", "pending"), "SDK model status outside contract")
            require(item["sdkStatus"] == status and item["sourceProfile"] == report["sourceProfile"], "actual SDK status/profile differs")
            profile = "captured-register-full-program/v2" if original["input"]["dataModel"] == "point-register-v1" else "captured-list-original-serial/v1"
            disposition = "unknown" if status in ("unknown", "pending") or report["sourceProfile"] != profile else "complete"
            require(item["sdkDisposition"] == disposition, "SDK disposition differs from actual model status/profile")
            if not upstream["comparisonEligible"]:
                expected_outcome = "upstreamNotComparable" if not upstream["cycleSearchTimeout"] else "timeout"
            elif status in ("unknown", "pending") or report["sourceProfile"] != profile:
                expected_outcome = "sdkUnknown"
            else:
                require(status in ("checked-compatible", "refuted"), "SDK model status")
                expected_outcome = "match" if (status == "checked-compatible") is upstream["validity"] else "difference"
            require(item["outcome"] == expected_outcome, "SDK outcome not derived from fixed upstream eligibility/judgment")
            outcomes[expected_outcome] += 1
            if upstream["comparisonEligible"]:
                eligible_outcomes[expected_outcome] += 1
            by_data_model[original["input"]["dataModel"]][expected_outcome] += 1
            sdk_dispositions[disposition] += 1
            lines += 1
    require(lines == 2000 and count == summary["reportUncompressedBytes"]
            and value.hexdigest() == summary["reportStreamSha256"], "complete report stream hash/count")
    require(outcomes == summary["totals"] and eligible_outcomes == summary["eligibleOutcomes"]
            and by_data_model == summary["byDataModel"] and sdk_dispositions == summary["sdkDispositions"],
            "independently recounted outcomes differ")
    require(outcomes["match"] == 1997 and outcomes["upstreamNotComparable"] == 3
            and all(outcomes[name] == 0 for name in ("difference", "sdkUnknown", "timeout", "failure"))
            and summary["fatal"] is None and summary["passed"] is True,
            "recounted SDK differences/unknowns/timeouts/failures retained; comparison did not pass")
    return summary


def run(args):
    tools, output = args.tools.resolve(strict=True), args.output.resolve()
    require(re.fullmatch("[a-f0-9]{40}", args.workflow_sha), "immutable workflow SHA required")
    require(not output.exists() and not output.is_relative_to(tools), "fresh external verification directory required")
    output.mkdir(parents=True)
    results = output / "results"
    results.mkdir()
    receipt = {"passed": False, "format": "moontxnwitness-hosted-public-fixed2000-v2/v1",
        "workflowSha": args.workflow_sha, "libraryVersion": VERSION, "librarySource": LIBRARY_SOURCE,
        "dataReleaseTag": DATA_TAG, "authorWorkspaceSdkUsed": False, "originalCampaignZipUsed": False,
        "jvmExecuted": False, "jarsDownloaded": False, "allHttpAnonymous": True}
    error = None
    try:
        before_tools = tool_bindings(tools)
        receipt["trustedToolsBefore"] = before_tools
        write_json(results / "public-library-tag.json", verify_library_tag())
        data_path, portable_path = output / "downloads/data.zip", output / "downloads/portable.zip"
        data_download = download(DATA_URL, data_path, DATA_BYTES, DATA_SHA)
        write_json(results / "data-download.json", data_download)
        portable_download = download(PORTABLE_URL, portable_path, PORTABLE_BYTES, PORTABLE_SHA)
        write_json(results / "portable-download.json", portable_download)
        data = SafeZip(data_path, DATA_BYTES, DATA_SHA, "sealed-reference/", max_member=8 * MiB, max_expanded=64 * MiB)
        validate_data(data)
        write_json(results / "data-zip-inventory.json", data.inventory)
        sealed = output / "data/sealed-reference"
        data.extract(data.rows, sealed)
        portable = SafeZip(portable_path, PORTABLE_BYTES, PORTABLE_SHA, "MoonTxnWitness-v0.5.0/")
        manifest = validate_portable(portable)
        write_json(results / "portable-zip-inventory.json", portable.inventory)
        package = results / "runtime-package"
        selected = [portable.prefix + name for name in ["package.json", "dist/core.mjs", "dist/models-v4.mjs", "dist/build-manifest.json"]]
        portable.extract(selected, package)
        runtime = package / "dist"
        runtime_files = {name: file_digest(runtime / name) for name in ["core.mjs", "models-v4.mjs", "build-manifest.json"]}
        write_json(results / "runtime-binding.json", {"publicPortableSha256": PORTABLE_SHA, "manifest": manifest,
            "actualRuntimeFiles": runtime_files, "librarySource": LIBRARY_SOURCE,
            "rootVerifiedFromActualPinnedCentralDirectory": portable.prefix,
            "onlySelectedRuntimeExtracted": True, "allPortableMembersCrcAndShaVerified": len(portable.rows)})
        run_command([sys.executable, "-I", "-B", tools / "verify_offline_bundle.py", "--bundle", sealed,
            "--expected-manifest-sha", BUNDLE_SHA, "--output", results / "offline-receipt.json"],
            results / "logs/offline.log", output, 300)
        offline = strict_json((results / "offline-receipt.json").read_bytes())
        require(offline["passed"] is True and offline["originalCasesVerified"] == 2000
                and offline["originalArtifactZipShaVerifiedInThisRun"] is False
                and offline["runtimeDependencyJarsRehashedInThisRun"] is False, "offline evidence scope differs")
        probe = "import{pathToFileURL}from'node:url';const c=await import(pathToFileURL(process.argv[1]));console.log(JSON.stringify({version:c.version()}));"
        run_command(["node", "--input-type=module", "-e", probe, runtime / "core.mjs"], results / "logs/runtime-version.json", output, 60)
        require(strict_json((results / "logs/runtime-version.json").read_bytes())["version"] == VERSION, "actual SDK version differs")
        comparison = results / "comparison"
        run_command(["node", tools / "compare_sdk_v2.mjs", "--job", sealed / "fixed2000-job.original.json",
            "--reference", sealed / "upstream-reference-v2.json", "--runtime", runtime,
            "--expected-version", VERSION, "--expected-core-sha", runtime_files["core.mjs"],
            "--runtime-origin", "public-download", "--output", comparison], results / "logs/comparison.log", output, 1800)
        job_bytes, reference_bytes = (sealed / "fixed2000-job.original.json").read_bytes(), (sealed / "upstream-reference-v2.json").read_bytes()
        require(digest(job_bytes) == JOB_SHA and digest(reference_bytes) == REFERENCE_SHA, "sealed inputs changed")
        summary = validate_comparison(comparison, runtime_files, strict_json(job_bytes), strict_json(reference_bytes))
        require(tool_bindings(tools) == before_tools, "trusted tools changed during validation")
        require({name: file_digest(runtime / name) for name in runtime_files} == runtime_files, "public runtime changed")
        require(file_digest(data_path) == DATA_SHA and file_digest(portable_path) == PORTABLE_SHA, "public archive changed")
        receipt.update(passed=True, trustedToolsAfter=before_tools, publicRuntimeFiles=runtime_files,
            classifications=summary["classifications"], verifications=summary["verifications"], totals=summary["totals"],
            immutableUpstreamEligible=summary["upstreamEligible"], upstreamElleReexecuted=False)
    except Exception as exc:
        error = exc
        receipt.update(errorType=type(exc).__name__, error=str(exc))
    finally:
        write_json(results / "hosted-receipt.json", receipt)
        bindings = {path.relative_to(results).as_posix(): {"bytes": path.stat().st_size, "sha256": file_digest(path)}
                    for path in results.rglob("*") if path.is_file()}
        write_json(results / "result-file-index.json", {"files": bindings})
    if error is not None:
        raise error
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tools", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workflow-sha", required=True)
    args = parser.parse_args()
    print(json.dumps(run(args)))


if __name__ == "__main__":
    main()
