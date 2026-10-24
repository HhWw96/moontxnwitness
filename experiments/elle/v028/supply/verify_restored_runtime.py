"""Verify a restored runtime artifact at its exact original root; no JVM invocation."""
from pathlib import Path
import argparse
import hashlib
import json

CORE = "4f9a73a5fe82478d913cb751ab68714d4ba0558c85b45a3933c6eb9a6c3078ef"


def pinned(path, pin, limit):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError("Pinned bounded regular file required")
    raw = path.read_bytes()
    if len(raw) > limit or hashlib.sha256(raw).hexdigest() != pin:
        raise ValueError("External SHA differs")
    return raw


def binding(path):
    digest, count = hashlib.sha256(), 0
    with Path(path).open("rb") as stream:
        while block := stream.read(65536):
            count += len(block)
            digest.update(block)
    return {"bytes": count, "sha256": digest.hexdigest()}


def verify(root, index, runtime_pin):
    root = Path(root).absolute()
    if root.resolve() != root or root.is_symlink() or index["sourceRoot"] != str(root):
        raise ValueError("Original literal runtime root required; relocation is not implicit")
    expected = index["files"]
    for name in expected:
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Unsafe runtime member")
    actual = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Runtime symlink refused")
        if path.is_file():
            name = path.relative_to(root).as_posix()
            if name != "RUNTIME-ARTIFACT-INDEX.json":
                actual[name] = binding(path)
    if actual != expected:
        raise ValueError("Restored runtime full member closure differs")
    if not index["runtimePassed"]:
        raise ValueError("A failed supply artifact cannot start checker inputs")
    runtime_path = root / "runtime-manifest.json"
    runtime_raw = pinned(runtime_path, runtime_pin, 4 * 1024 * 1024)
    runtime = json.loads(runtime_raw)
    for name in ("javaExecutable", "xvfbExecutable"):
        entry = runtime[name]
        if binding(entry["path"]) != {k: entry[k] for k in ("bytes", "sha256")}:
            raise ValueError("Actual host executable differs")
    for name, expected_binding in runtime["auxiliaryExecutableBindings"].items():
        if binding(name) != expected_binding:
            raise ValueError("Actual auxiliary host executable differs")
    return runtime_raw


def main():
    p = argparse.ArgumentParser()
    for name in ("root", "index-sha256", "runtime-sha256", "controller", "output"):
        p.add_argument("--" + name, required=True)
    a = p.parse_args()
    root = Path(a.root)
    index_raw = pinned(root / "RUNTIME-ARTIFACT-INDEX.json", a.index_sha256, 8 * 1024 * 1024)
    runtime_raw = verify(root, json.loads(index_raw), a.runtime_sha256)
    source = pinned(a.controller, CORE, 1024 * 1024)
    ns = {"__name__":"same_byte_runtime_verifier_core","__file__":a.controller,
          "__verified_source_sha256__":CORE}
    exec(compile(source, a.controller, "exec"), ns)
    ns["validate_runtime"](runtime_raw)
    target = Path(a.output).absolute()
    if target.resolve().is_relative_to(root.resolve()):
        raise ValueError("Verification output must not mutate restored runtime closure")
    ns["write_new"](target, ns["json_bytes"]({"passed":True,"kind":"runtime-restoration-byte-verification",
        "runtimeIndexSha256":a.index_sha256,"runtimeManifestSha256":a.runtime_sha256,
        "actualJVMExecuted":False,"actualCheckerInputs":0,"independentRuntimeAdmission":False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
