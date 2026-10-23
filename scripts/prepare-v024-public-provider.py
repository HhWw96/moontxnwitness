"""Prepare a frozen v0.2.4 provider; never downloads or publishes anything."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import zipfile

VERSION = "0.2.4"
REPOSITORY = "https://github.com/HhWw96/moontxnwitness"
MODULE = "HhWw96/moontxnwitness"
RUNTIME = ("core.mjs", "capture-core.mjs", "sdk.mjs", "evidence.mjs", "orm-profile.mjs",
           "build-manifest.json", "THIRD_PARTY_NOTICES.txt")
MAX_ENTRY = 32 * 1024 * 1024
sha = lambda raw: hashlib.sha256(raw).hexdigest()

def safe_name(name):
    if not isinstance(name, str) or not name or "\\" in name or ":" in name:
        raise ValueError("Unsafe provider path")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in ("", ".", "..") for part in name.split("/")):
        raise ValueError("Unsafe provider path")
    return path.as_posix()

def metadata(raw):
    return {"bytes": len(raw), "sha256": sha(raw)}

def esm_closure(read, entry):
    """Static relative ESM closure of these frozen self-contained modules."""
    pending, seen = [entry], set()
    pattern = re.compile(r"\b(?:import|export)\s*(?:\{[^}]*\}|[\w*$,\s]+)\s*from\s*['\"]([^'\"]+)['\"]")
    side = re.compile(r"\bimport\s*['\"]([^'\"]+)['\"]")
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        text = read(name).decode("utf8")
        if re.search(r"\bimport\s*\(", text):
            raise ValueError("Dynamic imports require a new dependency-closure review")
        for target in pattern.findall(text) + side.findall(text):
            if target.startswith("node:"):
                continue
            if not target.startswith("./") or not target.endswith(".mjs"):
                raise ValueError("Unreviewed runtime dependency: " + target)
            relative = safe_name((PurePosixPath(name).parent / target[2:]).as_posix())
            pending.append(relative)
    return sorted(seen)

def validate_publication(receipt, portable, registry, expected_source=None):
    if not isinstance(expected_source, str) or re.fullmatch(r"[0-9a-f]{40}", expected_source) is None:
        raise ValueError("An explicit reviewed expected public tag/source SHA is required")
    if receipt.get("passed") is not True or receipt.get("version") != VERSION or receipt.get("account") != "HhWw96":
        raise ValueError("A completed real public24 verification receipt is required")
    github, cakes = receipt["github"], receipt["mooncakes"]
    if github["repository"] != REPOSITORY or github["release"] != REPOSITORY + "/releases/tag/v" + VERSION:
        raise ValueError("Unexpected public repository/release")
    ci = github["ci"]
    if ci["headSha"] != expected_source or ci["conclusion"] != "success" or ci.get("linuxNativeExecuted") is not True:
        raise ValueError("Exact published source/native CI binding required")
    if github["postgresCi"]["sourceCommit"] != expected_source or github["postgresCi"]["conclusion"] != "success":
        raise ValueError("Exact PostgreSQL CI source binding required")
    name = "MoonTxnWitness-v" + VERSION + "-portable.zip"
    candidates = [row for row in github["assets"] if row["name"] == name]
    if len(candidates) != 1:
        raise ValueError("Exactly one portable asset required")
    asset = candidates[0]
    if asset["url"] != REPOSITORY + "/releases/download/v" + VERSION + "/" + name or asset.get("anonymousDownload") is not True:
        raise ValueError("Anonymous actual public download required")
    if portable.stat().st_size != asset["bytes"] or sha(portable.read_bytes()) != asset["sha256"]:
        raise ValueError("Portable archive differs from the public receipt")
    if cakes["module"] != MODULE or cakes["version"] != VERSION or cakes["download"] != "https://download.mooncakes.io/user/" + MODULE + "/" + VERSION + ".zip":
        raise ValueError("Unexpected actual Mooncakes source")
    if cakes.get("uploadedBytesMatchPublicDownload") is not True or cakes["registryOnlyConsumer"]["passed"] is not True or cakes["registryOnlyConsumer"]["workspaceOverride"] is not False:
        raise ValueError("Actual registry-only consumer verification required")
    if registry.stat().st_size != cakes["bytes"] or sha(registry.read_bytes()) != cakes["sha256"]:
        raise ValueError("Registry bytes differ from actual public verification")
    return asset, {k: cakes[k] for k in ("download", "sha256", "bytes")}

def prepare(read, output, origin, publication_raw=None):
    if output.exists():
        raise ValueError("Never overwrite a frozen provider")
    saved = {}
    def save(name, raw):
        safe_name(name)
        if name in saved:
            if saved[name] != raw:
                raise ValueError("Provider source changed during extraction")
            return
        saved[name] = raw
    def public(name):
        name = safe_name(name)
        raw = read(name)
        if len(raw) > MAX_ENTRY:
            raise ValueError("Bounded provider entry exceeded")
        save("package/" + name, raw)
        return raw
    runtime = {}
    for name in RUNTIME:
        raw = read("dist/" + name)
        save("runtime/" + name, raw)
        runtime[name] = metadata(raw)
    save("runtime/LICENSE", read("LICENSE"))
    runtime["LICENSE"] = metadata(saved["runtime/LICENSE"])
    manifest = json.loads(saved["runtime/build-manifest.json"])
    if manifest["version"] != VERSION or runtime["core.mjs"]["sha256"] != manifest["coreSha256"] or runtime["capture-core.mjs"]["sha256"] != manifest["captureCoreSha256"]:
        raise ValueError("Actual runtime/build manifest mismatch")
    raw_reader = lambda name: saved["runtime/" + safe_name(name)]
    minimum = esm_closure(raw_reader, "orm-profile.mjs")
    full = esm_closure(raw_reader, "sdk.mjs")
    if minimum != ["core.mjs", "orm-profile.mjs"] or full != sorted(n for n in RUNTIME if n.endswith(".mjs")):
        raise ValueError("Re-review changed public24 dependency closure")
    old_dir = "fixtures/compat-v023/"
    old = json.loads(public(old_dir + "manifest.json"))
    if old.get("actualPublishedProducer") is not True or old["producerEngineVersion"] != "0.2.3" or len(old["cases"]) != 8:
        raise ValueError("Eight original common input cases required")
    common = []
    for row in old["cases"]:
        name = old_dir + safe_name(row["input"]["file"])
        raw = public(name)
        if metadata(raw) != {k: row["input"][k] for k in ("bytes", "sha256")}:
            raise ValueError("Original common raw facts changed")
        common.append({"name": row["name"], "type": row["type"], "inputPath": name,
                       "expectedStatus": row["expectedStatus"], "originalInputUnchanged": True})
    acceptance = json.loads(public("verification/releases/" + VERSION + "/acceptance.json"))
    database_name = "verification/releases/" + VERSION + "/" + safe_name(acceptance["databaseEvidence"])
    database = json.loads(public(database_name))
    ref = database["receipts"]["configuredUserBusiness"]
    business_parent = "verification/" + safe_name(ref["path"])
    business_name = business_parent + "/" + safe_name(ref["receiptFile"])
    business_raw = public(business_name)
    if metadata(business_raw) != {k: ref[k] for k in ("bytes", "sha256")}:
        raise ValueError("Current actual-business receipt binding mismatch")
    business = json.loads(business_raw)
    if business["passed"] is not True or business["actualDatabaseExecution"] is not True or business["version"] != VERSION or len(business["producers"]) != 2:
        raise ValueError("Two current original business producers required")
    actual = []
    for row in business["producers"]:
        parent = business_parent + "/producer-" + str(row["id"]) + "/"
        if row["producerPassed"] is not True or row["ownClusterStopped"] is not True:
            raise ValueError("Original business run did not finish")
        for name, record in row["files"].items():
            if metadata(public(parent + safe_name(name))) != record:
                raise ValueError("Original business source bytes changed")
        wrapper = json.loads(saved["package/" + parent + "wrapper-receipt.json"])
        if wrapper["sourceUnchanged"] is not True or wrapper["ownClusterStopped"] is not True or wrapper["sourceBefore"] != wrapper["sourceAfter"]:
            raise ValueError("Original collector implementation changed")
        for name, digest in wrapper["sourceBefore"].items():
            if sha(read(safe_name(name))) != digest:
                raise ValueError("Archive collector differs from original actual run")
        actual.append({"name": "orm-actual-" + str(row["id"]),
                       "inputPath": parent + "suite/profile-source.json",
                       "originalObservedSource": True, "databaseExecutedHere": False})
    if sorted(row["name"] for row in actual) != ["orm-actual-1", "orm-actual-2"]:
        raise ValueError("Distinct current business producers required")
    synthetic_root = "fixtures/orm-profile-v3/synthetic-nonrepeatable-first/"
    synthetic = json.loads(public(synthetic_root + "manifest.json"))
    if synthetic["actualPostgresAnomaly"] is not False or synthetic["actualDatabaseExecution"] is not False:
        raise ValueError("Synthetic anomaly must remain labelled synthetic")
    synthetic_path = synthetic_root + "profile-source.json"
    if sha(public(synthetic_path)) != synthetic["envelopeSha256"]:
        raise ValueError("Synthetic raw-source binding mismatch")
    public(synthetic_root + "segment-000001.jsonl")
    lost = "verification/capture-persistence/v023-initial/postgres-cases/lost-commit-sync/"
    for name in ("trace.json", "lifecycle.jsonl", "journal-index.json"):
        public(lost + name)
    if publication_raw is not None:
        save("origin/publication.json", publication_raw)
    provider = {"format": "moontxnwitness-v024-provider/v1", **origin, "version": VERSION,
                "runtimeDirectory": "runtime", "packageDirectory": "package",
                "minimalOrmReplayFiles": minimum, "fullSdkEsmFiles": full, "runtime": runtime,
                "buildManifest": manifest, "commonCases": common, "actualOrmCases": actual,
                "syntheticProfilePath": synthetic_path, "lostCommitDirectory": lost,
                "databaseExecutedHere": False, "compilerExecutedHere": False,
                "headerRewriting": False, "bindings": {name: metadata(raw) for name, raw in saved.items()}}
    output.mkdir(parents=True, exist_ok=False)
    for name, raw in saved.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            if handle.write(raw) != len(raw):
                raise OSError("Short provider write")
    (output / "provider.json").write_bytes((json.dumps(provider, indent=2) + "\n").encode())
    return provider

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publication-receipt")
    parser.add_argument("--expected-source", help="Exact source/tag SHA verified independently after publication")
    parser.add_argument("--portable")
    parser.add_argument("--registry")
    parser.add_argument("--development-checkout", help="Explicit non-public probe only")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    output = Path(args.out).resolve()
    if args.development_checkout:
        if any((args.publication_receipt, args.portable, args.registry, args.expected_source)):
            raise ValueError("Development mode cannot claim actual publication")
        checkout = Path(args.development_checkout).resolve()
        if output.is_relative_to(checkout):
            raise ValueError("Keep provider outside the source checkout")
        def read(name):
            path = checkout / safe_name(name)
            if path.is_symlink() or not path.resolve().is_relative_to(checkout):
                raise ValueError("Unexpected linked source")
            return path.read_bytes()
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=checkout).decode().strip()
        provider = prepare(read, output, {"actualPublishedProducer": False, "authorDistRead": True,
            "originMode": "development-author-checkout", "authorSourceCommit": commit})
    else:
        if not all((args.publication_receipt, args.portable, args.registry, args.expected_source)):
            raise ValueError("Real completed publication receipt and both public ZIPs required")
        receipt_path, portable, registry = (Path(value).resolve() for value in (args.publication_receipt, args.portable, args.registry))
        if receipt_path.stat().st_size > 2 * 1024 * 1024 or portable.stat().st_size > 128 * 1024 * 1024 or registry.stat().st_size > 16 * 1024 * 1024:
            raise ValueError("Bounded public input exceeded")
        receipt_raw = receipt_path.read_bytes()
        receipt = json.loads(receipt_raw)
        asset, cakes = validate_publication(receipt, portable, registry, args.expected_source)
        prefix = "MoonTxnWitness-v" + VERSION + "/"
        with zipfile.ZipFile(portable) as packed:
            infos = packed.infolist()
            if len(infos) > 20000 or sum(row.file_size for row in infos) > 512 * 1024 * 1024:
                raise ValueError("Bounded public archive exceeded")
            names = set()
            for info in infos:
                name = safe_name(info.filename.rstrip("/"))
                if not name.startswith(prefix) or name.casefold() in names or (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("Unsafe/duplicate public archive entry")
                names.add(name.casefold())
            def read(name):
                info = packed.getinfo(prefix + safe_name(name))
                if info.is_dir() or info.file_size > MAX_ENTRY:
                    raise ValueError("Bounded regular entry required")
                return packed.read(info)
            provider = prepare(read, output, {"actualPublishedProducer": True, "authorDistRead": False,
                "originMode": "verified-anonymous-public-download", "sourceCommit": args.expected_source, "expectedSourceCommit": args.expected_source,
                "publicPackage": asset, "registryPackage": cakes, "publicationReceiptSha256": sha(receipt_raw),
                "publicationValidationPassed": True}, receipt_raw)
    print(json.dumps({"prepared": True, "actualPublishedProducer": provider["actualPublishedProducer"],
        "minimalOrmReplayFiles": provider["minimalOrmReplayFiles"], "fullSdkEsmFiles": provider["fullSdkEsmFiles"],
        "databaseExecutedHere": False, "compilerExecutedHere": False}))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
