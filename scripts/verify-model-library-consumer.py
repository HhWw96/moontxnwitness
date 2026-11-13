"""Exercise the new public MoonBit APIs from a fresh isolated consumer.

The default mode installs the requested published version with `moon add`.
--source explicitly selects a local workspace dependency, uses frozen commands
without registry installation, and can never verify a public package.
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


MODULE = "HhWw96/moontxnwitness"
CONSUMER = "verification/model-library-consumer"
BASE = Path(__file__).resolve().parent.parent
WORKSPACE_NAMES = ("moon.work", "moon.work.json")
MODULE_NAMES = ("moon.mod", "moon.mod.json")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def binding(path):
    digest, size = hashlib.sha256(), 0
    with path.open("rb") as stream:
        while block := stream.read(65536):
            digest.update(block)
            size += len(block)
    return {"bytes": size, "sha256": digest.hexdigest()}


def manifest(root):
    text_path = root / "moon.mod"
    if text_path.is_file():
        text = text_path.read_text("utf8")
        fields = {name: json.loads(value) for name, value in re.findall(
            r'(?m)^\s*(name|version|source)\s*=\s*("(?:[^"\\]|\\.)*")', text)}
        return text_path, fields
    path = root / "moon.mod.json"
    return path, json.loads(path.read_text("utf8"))


def no_ancestor_project(path):
    for parent in path.parents:
        for name in WORKSPACE_NAMES + MODULE_NAMES:
            require(not (parent / name).exists(), "Fresh consumer must be outside an ancestor MoonBit project/workspace: " + str(parent / name))


def library_bindings(root, version):
    path, fields = manifest(root)
    require(fields.get("name") == MODULE and fields.get("version") == version, "Installed module identity/version differs")
    source = (root / fields.get("source", ".")).resolve(strict=True)
    resolved = root.resolve(strict=True)
    require(source.is_relative_to(resolved), "Library source escapes its installed module")
    paths = [path]
    for name in ("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.txt"):
        if (root / name).is_file():
            paths.append(root / name)
    for entry in source.rglob("*"):
        if entry.is_file() and (entry.suffix == ".mbt" or entry.name in ("moon.pkg", "moon.pkg.json")):
            require(not entry.is_symlink() and entry.resolve().is_relative_to(resolved), "Installed library source uses an external link")
            paths.append(entry)
    require(len(paths) > 2, "Installed library has no inspectable MoonBit core sources")
    return {entry.relative_to(root).as_posix(): binding(entry) for entry in sorted(set(paths))}


def compiled_bindings(output, targets):
    cores, executables = {}, {}
    for path in sorted((output / "build").rglob("*")):
        if not path.is_file():
            continue
        name = path.relative_to(output).as_posix()
        if "/HhWw96/moontxnwitness/" in name and path.suffix == ".core":
            cores[name] = binding(path)
        if "/verification/model-library-consumer/" in name and path.suffix in (".js", ".wasm", ".exe"):
            executables[name] = binding(path)
    for target in targets:
        require(any(name.startswith("build/" + target + "/") for name in cores), "An actual compiled installed-library core is missing: " + target)
    return {"libraryCore": cores, "consumerExecutables": executables}


def moon_literal(text):
    return json.dumps(text, ensure_ascii=True)


def tests_for(level, version, predicate, reduction):
    tests = ['''///|
test "installed library reports the independently requested version" {
  assert_eq(@txn.version(), VERSION)
}
'''.replace("VERSION", moon_literal(version))]
    if level == "inference":
        return "\n".join(tests), len(tests)
    helpers = '''///|
fn field(value : Json, name : String) -> Json {
  match value {
    Object(fields) => fields.get_or_default(name, Json::null())
    _ => abort("Public JSON object required")
  }
}

///|
fn items(value : Json) -> Array[Json] {
  match value {
    Array(rows) => rows
    _ => abort("Public JSON array required")
  }
}

///|
fn model_status(report : Json, name : String) -> Json {
  for row in items(field(report, "models")) {
    if field(row, "model") == Json(name) { return field(row, "status") }
  }
  abort("Selected model missing from the public report")
}

///|
fn relation_facts() -> @txn.ModelFactsV4 {
  @txn.model_facts_v4(
    @txn.parse_history_v4(PREDICATE).unwrap(),
    clients=[
      { id: "declared-A", transactions: ["A"], },
      { id: "declared-B", transactions: ["B"], },
    ],
    clients_complete=true,
  ).unwrap()
}
'''.replace("PREDICATE", moon_literal(predicate))
    tests.extend(['''///|
test "fourteen relation definitions classify a real predicate-only cycle" {
  let facts = relation_facts()
  let options = @txn.model_options_v4(models=@txn.elle_core_models_v4()).unwrap()
  let report = @txn.relation_model_classification_v4_json(
    @txn.classify_relation_models_v4(facts, options).unwrap(),
  )
  assert_eq(field(report, "semanticContract"), Json("relation-predicate-models/v1"))
  assert_eq(items(field(report, "models")).length(), 14)
  for row in items(field(report, "models")) {
    let serial = field(row, "model") == Json("serializable") ||
      field(row, "model") == Json("strict-serializable") ||
      field(row, "model") == Json("strong-session-serializable")
    assert_eq(field(row, "status"), if serial { Json("refuted") } else { Json("checked-compatible") })
  }
  assert_true(@txn.verify_relation_models_v4(facts, report, options))
}
''', '''///|
test "unknown real time is independent policy and retains a data refutation" {
  let facts = relation_facts()
  let options = @txn.model_options_v4(models=@txn.elle_core_models_v4()).unwrap()
  let known = @txn.relation_model_classification_v4_json(
    @txn.classify_relation_models_v4(facts, options).unwrap(),
  )
  assert_false(@txn.verify_relation_models_v4(facts, known, options, realtime_known=false))
  let unknown = @txn.relation_model_classification_v4_json(
    @txn.classify_relation_models_v4(facts, options, realtime_known=false).unwrap(),
  )
  assert_eq(field(field(unknown, "sourcePolicy"), "realtimeKnown"), Json(false))
  assert_eq(field(field(unknown, "orderFacts"), "realtimeComplete"), Json(false))
  assert_eq(model_status(unknown, "strong-snapshot-isolation"), Json("unknown"))
  assert_eq(model_status(unknown, "strict-serializable"), Json("refuted"))
  assert_true(@txn.verify_relation_models_v4(facts, unknown, options, realtime_known=false))
  assert_false(@txn.verify_relation_models_v4(facts, unknown, options))
}
''', '''///|
test "relation verification rejects changed verdict and independently changed budgets" {
  let facts = relation_facts()
  let options = @txn.model_options_v4(models=@txn.elle_core_models_v4()).unwrap()
  let report = @txn.relation_model_classification_v4_json(
    @txn.classify_relation_models_v4(facts, options).unwrap(),
  )
  let changed = @json.parse(report.stringify())
  match changed {
    Object(fields) => fields["status"] = Json("checked-compatible")
    _ => abort("Object report required")
  }
  assert_false(@txn.verify_relation_models_v4(facts, changed, options))
  assert_false(@txn.verify_relation_models_v4(
    facts, report,
    @txn.model_options_v4(models=@txn.elle_core_models_v4(), max_states=0).unwrap(),
  ))
}
'''])
    if level == "reduction":
        helpers += '''
///|
fn reduction_facts() -> @txn.ModelFactsV4 {
  @txn.model_facts_v4(@txn.parse_history_v4(REDUCTION).unwrap()).unwrap()
}
'''.replace("REDUCTION", moon_literal(reduction))
        tests.extend(['''///|
test "model-preserving reduction removes noise and independently verifies" {
  let facts = reduction_facts()
  let options = @txn.model_options_v4(models=[@txn.ElleSerializable]).unwrap()
  let result = @txn.reduce_relation_models_v4(facts, @txn.ElleSerializable, options)
  let report = @txn.relation_model_reduction_v4_json(result)
  assert_eq(field(report, "semanticContract"), Json("relation-predicate-model-reduction/v1"))
  assert_eq(field(report, "status"), Json("reduced"))
  assert_eq(field(report, "preserveModel"), Json("serializable"))
  assert_eq(field(report, "oneMinimal"), Json(true))
  assert_eq(items(field(report, "selectedTransactions")).length(), 2)
  assert_eq(items(field(report, "removedTransactions")).length(), 1)
  assert_eq(field(field(report, "classification"), "status"), Json("refuted"))
  assert_true(@txn.verify_relation_model_reduction_v4(facts, report, @txn.ElleSerializable, options))
  assert_false(@txn.verify_relation_model_reduction_v4(facts, report, @txn.ElleReadUncommitted, options))
  assert_false(@txn.verify_relation_model_reduction_v4(facts, report, @txn.ElleSerializable, options, realtime_known=false))
}
''', '''///|
test "zero deletion budget preserves a reverified refutation without minimality" {
  let facts = reduction_facts()
  let options = @txn.model_options_v4(models=[@txn.ElleSerializable]).unwrap()
  let report = @txn.relation_model_reduction_v4_json(
    @txn.reduce_relation_models_v4(facts, @txn.ElleSerializable, options, max_checks=0),
  )
  assert_eq(field(report, "status"), Json("budget"))
  assert_eq(field(report, "oneMinimal"), Json(false))
  assert_eq(field(field(report, "classification"), "status"), Json("refuted"))
  assert_eq(field(field(report, "execution"), "finalRevalidation"), Json(true))
  assert_true(@txn.verify_relation_model_reduction_v4(facts, report, @txn.ElleSerializable, options, max_checks=0))
  assert_false(@txn.verify_relation_model_reduction_v4(facts, report, @txn.ElleSerializable, options))
}
'''])
    return helpers + "\n".join(tests), len(tests)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, required=True, help="new directory outside every ancestor project/workspace")
    parser.add_argument("--source", type=Path, help="explicit local checkout; never verifies a public package")
    parser.add_argument("--api-level", choices=("inference", "relation", "reduction"), help="default follows version: 0.4.3/0.4.4/0.4.5")
    parser.add_argument("--targets", default="js,wasm-gc", help="comma-separated targets; Linux can add native")
    parser.add_argument("--moon", help="Moon executable; defaults to MOON_HOME/bin/moon or PATH")
    args = parser.parse_args(argv)
    require(re.fullmatch(r"\d+\.\d+\.\d+", args.version), "An exact released semantic version is required")
    version_tuple = tuple(map(int, args.version.split(".")))
    require(version_tuple >= (0, 4, 3), "This consumer verifies new model-library APIs from v0.4.3 onward")
    level = args.api_level or ("reduction" if version_tuple >= (0, 4, 5) else "relation" if version_tuple >= (0, 4, 4) else "inference")
    targets = args.targets.split(",")
    require(targets and len(targets) == len(set(targets)) and all(t in ("js", "wasm-gc", "wasm", "native") for t in targets), "Invalid or duplicate targets")
    require("native" not in targets or sys.platform.startswith("linux"), "Native consumer execution must run on Linux")
    out = args.output.resolve()
    require(not out.exists(), "Consumer output already exists; original records are never overwritten")
    no_ancestor_project(out)
    source = args.source.resolve(strict=True) if args.source else None
    assets = source or BASE
    asset_paths = {"registeredExample": assets / "examples/inference-modules-v4/main.mbt"}
    if level != "inference":
        asset_paths["predicateExample"] = assets / "examples/relation-predicate-categories.json"
    if level == "reduction":
        asset_paths["reductionExample"] = assets / "examples/relation-category-reduction.json"
    asset_before = {name: binding(path) for name, path in asset_paths.items()}
    moon_name = args.moon or (str(Path(os.environ["MOON_HOME"]) / "bin" / ("moon.exe" if os.name == "nt" else "moon")) if os.environ.get("MOON_HOME") else shutil.which("moon"))
    require(moon_name, "Moon executable is required; set --moon or MOON_HOME")
    moon = Path(moon_name).resolve(strict=True)
    out.mkdir(parents=True)
    consumer, logs, temporary = out / "consumer", out / "logs", out / "temporary"
    consumer.mkdir()
    logs.mkdir()
    temporary.mkdir()
    (out / "inputs").mkdir()
    for path in asset_paths.values():
        shutil.copyfile(path, out / "inputs" / path.name)
    shutil.copyfile(Path(__file__).resolve(), out / "executed-verifier.py")
    env = dict(os.environ)
    env.update(MOON_HOME=str(moon.parent.parent), TEMP=str(temporary), TMP=str(temporary), TMPDIR=str(temporary))
    env["PATH"] = str(moon.parent) + os.pathsep + env.get("PATH", "")
    receipt = {"format": "moontxnwitness-new-model-library-consumer/v1", "passed": False,
               "version": args.version, "apiLevel": level, "module": MODULE, "targets": targets,
               "mode": "source-workspace" if source else "registry-only", "workspaceOverride": bool(source),
               "publicPackageVerified": False, "registryInstallAttempted": False,
               "startedAt": datetime.now(timezone.utc).isoformat(), "stages": [], "assets": asset_before,
               "driver": binding(Path(__file__).resolve()), "formalPerformanceMeasurement": False}
    installed = None

    def save():
        (out / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", "utf8")

    def stage(name, command, timeout=900):
        row = {"name": name, "command": [str(a) for a in command], "passed": False}
        receipt["stages"].append(row)
        try:
            result = subprocess.run(command, cwd=consumer, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
            (logs / (name + ".stdout.log")).write_bytes(result.stdout)
            (logs / (name + ".stderr.log")).write_bytes(result.stderr)
            row.update(exitCode=result.returncode, stdout=binding(logs / (name + ".stdout.log")), stderr=binding(logs / (name + ".stderr.log")), passed=result.returncode == 0)
            require(result.returncode == 0, "Consumer stage failed: " + name)
            return result.stdout.decode("utf8", errors="replace")
        except subprocess.TimeoutExpired as error:
            (logs / (name + ".stdout.log")).write_bytes(error.stdout or b"")
            (logs / (name + ".stderr.log")).write_bytes(error.stderr or b"")
            row["timeout"] = True
            raise
        finally:
            save()

    try:
        versions = stage("compiler-versions", [str(moon), "version", "--all"], timeout=60)
        compiler = re.search(r"moonc\s+v?(\d+)\.(\d+)\.(\d+)([^\s]*)", versions)
        require(compiler and tuple(map(int, compiler.group(1, 2, 3))) >= (0, 10, 16), "Actual moonc must be >=0.10.16")
        receipt["compiler"] = compiler.group(0)
        receipt["compilerBinary"] = binding(moon.parent / ("moonc.exe" if os.name == "nt" else "moonc"))
        toolchain_manifest = moon.parent.parent / "lib/core/moon.mod"
        if toolchain_manifest.is_file():
            receipt["toolchainCoreManifest"] = binding(toolchain_manifest)
        module = f'name = "{CONSUMER}"\nversion = "0.0.0"\nsource = "src"\n'
        if source:
            library_bindings(source, args.version)
            module += f'import {{ "{MODULE}@{args.version}", }}\n'
            (consumer / "moon.work").write_text("members = [\".\", " + json.dumps(source.as_posix()) + "]\n", "utf8")
            installed = source
        (consumer / "moon.mod").write_text(module, "utf8")
        (consumer / "src/inference_demo").mkdir(parents=True)
        imports = f'import {{ "{MODULE}" @txn, ' + ('"moonbitlang/core/json", ' if level != "inference" else '') + '}\n'
        (consumer / "src/moon.pkg").write_text(imports, "utf8")
        library = '///|\npub fn installed_version() -> String { @txn.version() }\n'
        if level != "inference":
            library += '///|\npub fn parse_report(text : String) -> Json raise { @json.parse(text) }\n'
        (consumer / "src/consumer.mbt").write_text(library, "utf8")
        (consumer / "src/inference_demo/moon.pkg").write_text(f'import {{ "{MODULE}" @txn, }}\npkgtype(kind: "executable")\n', "utf8")
        shutil.copyfile(asset_paths["registeredExample"], consumer / "src/inference_demo/main.mbt")
        predicate = asset_paths["predicateExample"].read_text("utf8") if level != "inference" else ""
        reduction = asset_paths["reductionExample"].read_text("utf8") if level == "reduction" else ""
        tests, expected = tests_for(level, args.version, predicate, reduction)
        (consumer / "src/consumer_wbtest.mbt").write_text(tests, "utf8")
        receipt["expectedConsumerTestsPerTarget"] = expected
        if not source:
            require(not (consumer / "moon.work").exists(), "Registry consumer cannot contain a workspace override")
            receipt["registryInstallAttempted"] = True
            stage("registry-add", [str(moon), "add", MODULE + "@" + args.version])
            installed = consumer / ".mooncakes" / MODULE
            require(installed.is_dir() and not installed.is_symlink(), "Registry install must materialize the requested module")
        before = library_bindings(installed, args.version)
        (out / "installed-source-bindings.json").write_text(json.dumps(before, indent=2) + "\n", "utf8")
        receipt["installedModuleManifest"] = binding(manifest(installed)[0])
        receipt["installedCoreSourceFiles"] = len(before)
        receipt["installedSourceBindings"] = binding(out / "installed-source-bindings.json")
        for target in targets:
            target_dir = out / "build" / target
            common = ["--target", target, "--target-dir", str(target_dir), "--frozen"]
            stage("check-" + target, [str(moon), "check", "src", "--deny-warn", "--jobs", "1", *common])
            output = stage("test-" + target, [str(moon), "test", "--package", CONSUMER, "--deny-warn", "--jobs", "1", *common])
            require(f"Total tests: {expected}, passed: {expected}, failed: 0." in output, "Expected consumer test count was not executed: " + target)
            example = stage("registered-modules-" + target, [str(moon), "run", "src/inference_demo", "--deny-warn", "--jobs", "1", *common])
            require("two independent modules and builtins verified" in example and "changed module, removed modules and changed budget rejected" in example, "Registered-module example did not execute all policy checks")
        require(before == library_bindings(installed, args.version), "Installed library sources changed during consumer verification")
        for name, path in asset_paths.items():
            require(binding(path) == asset_before[name], "Consumer input/example changed during execution: " + name)
        if not source:
            no_ancestor_project(out)
            require(not any((consumer / name).exists() for name in WORKSPACE_NAMES), "Unexpected registry consumer workspace override")
        receipt["generatedConsumerBindings"] = {p.relative_to(consumer).as_posix(): binding(p)
            for p in sorted(consumer.rglob("*")) if p.is_file() and ".mooncakes" not in p.parts and (p.suffix == ".mbt" or p.name in ("moon.mod", "moon.work", "moon.pkg"))}
        compiled = compiled_bindings(out, targets)
        (out / "compiled-artifact-bindings.json").write_text(json.dumps(compiled, indent=2) + "\n", "utf8")
        receipt["compiledArtifactBindings"] = binding(out / "compiled-artifact-bindings.json")
        receipt["compiledLibraryCoreCount"] = len(compiled["libraryCore"])
        require(receipt["driver"] == binding(Path(__file__).resolve()) == binding(out / "executed-verifier.py"), "Consumer verifier changed during execution")
        receipt["passed"] = True
        receipt["publicPackageVerified"] = source is None
    except Exception as error:
        receipt["error"] = {"class": type(error).__name__, "message": str(error)}
    finally:
        receipt["finishedAt"] = datetime.now(timezone.utc).isoformat()
        save()
    print(json.dumps({name: receipt.get(name) for name in ("passed", "version", "apiLevel", "mode", "workspaceOverride", "publicPackageVerified", "expectedConsumerTestsPerTarget", "targets", "error")}))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
