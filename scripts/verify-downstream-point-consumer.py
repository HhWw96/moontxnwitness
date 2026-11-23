"""Run a clean downstream consumer from caller-pinned public releases."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import time


ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / ".github/actions/check-point-window/check.py"
SPEC = importlib.util.spec_from_file_location("point_window_action", ENTRY)
ACTION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ACTION)
FIXTURES = "examples/point-window-replay-data"
GATE_TEST = "scripts/point-window-ci-test.mjs"
MOON_CHECK = "scripts/verify-point-window-moon-consumer.mjs"
CASES = {
    "ordered": 0,
    "refutation": 1,
    "coverage-gap": 2,
    "missing-source-snapshot": 2,
    "rehashed-verdict": 2,
    "wrong-budget": 2,
}


def run_node(script, args, work, env):
    result = subprocess.run(
        ["node", str(script), *args], cwd=work, env=env, encoding="utf-8",
        timeout=600, check=True, stdout=subprocess.PIPE,
    )
    return json.loads(result.stdout)


def verify(version, portable_digest, registry_digest, output):
    output = output.resolve()
    output.mkdir()
    work = output / "work"
    work.mkdir()
    archive = output / "portable.zip"
    registry = output / "registry.zip"
    stages = {}
    start = time.monotonic()
    ACTION.download_portable(version, portable_digest, archive)
    stages["downloadPortableSeconds"] = time.monotonic() - start
    start = time.monotonic()
    ACTION.download_archive(
        f"https://download.mooncakes.io/user/HhWw96/moontxnwitness/{version}.zip",
        registry_digest, registry,
    )
    stages["downloadRegistrySeconds"] = time.monotonic() - start
    start = time.monotonic()
    package = output / "package"
    fixtures = ("manifest.json", "config.json", "policy.json", "ordered.json.gz", "before.json.gz", "retry.json.gz")
    files = (GATE_TEST, MOON_CHECK, *(f"{FIXTURES}/{name}" for name in fixtures))
    ACTION.unpack_runtime(archive, package, version, files)
    stages["extractSeconds"] = time.monotonic() - start
    public = package / f"MoonTxnWitness-v{version}"
    env = {**os.environ, "TMPDIR": str(work), "TEMP": str(work), "TMP": str(work)}
    start = time.monotonic()
    gate = run_node(public / GATE_TEST, [], work, env)
    if gate.get("passed") is not True or {row["name"]: row["code"] for row in gate["cases"]} != CASES:
        raise ValueError("Public package returned unexpected gate results")
    stages["gateSeconds"] = time.monotonic() - start
    start = time.monotonic()
    moon = run_node(public / MOON_CHECK, [
        "--runtime", str(public / "dist"), "--module-version", version,
        "--output", str(output / "moon-consumer"),
    ], work, env)
    if (moon.get("passed") is not True or moon.get("mooncakesVersion") != version
            or moon.get("runtimeVersion") != version):
        raise ValueError("Public MoonBit and JavaScript versions did not match")
    stages["registryInstallAndCompareSeconds"] = time.monotonic() - start
    receipt = {
        "passed": True, "version": version, "os": platform.system(),
        "portableSha256": portable_digest, "registrySha256": registry_digest,
        "portableBytes": archive.stat().st_size, "registryBytes": registry.stat().st_size,
        "stages": {name: round(value, 3) for name, value in stages.items()},
        "gate": gate["cases"], "compared": moon["compared"],
    }
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--portable-sha256", required=True)
    parser.add_argument("--registry-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", args.version):
        parser.error("Choose a stable version without a v prefix")
    digests = [args.portable_sha256.lower(), args.registry_sha256.lower()]
    if not all(re.fullmatch(r"[0-9a-f]{64}", value) for value in digests):
        parser.error("Both archive pins must be exact SHA-256 digests")
    verify(args.version, *digests, args.output)


if __name__ == "__main__":
    main()
