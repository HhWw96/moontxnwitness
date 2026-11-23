"""Verify a point-window capsule with an independently pinned public archive."""

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile


RELEASES = "https://github.com/HhWw96/moontxnwitness/releases/download"
MAX_DOWNLOAD = 512 * 1024 * 1024
MAX_RUNTIME = 1024 * 1024 * 1024
GATE = "examples/check-point-window.mjs"


def download_portable(version, expected_digest, destination):
    filename = f"MoonTxnWitness-v{version}-portable.zip"
    request = Request(f"{RELEASES}/v{version}/{filename}", headers={
        "User-Agent": "MoonTxnWitness-CI",
        "Accept-Encoding": "identity",
    })
    digest = hashlib.sha256()
    downloaded = 0
    with urlopen(request, timeout=60) as response, destination.open("xb") as output:
        if response.status != 200 or urlsplit(response.url).scheme != "https":
            raise ValueError("Portable archive download did not return HTTPS bytes")
        for block in iter(lambda: response.read(1024 * 1024), b""):
            downloaded += len(block)
            if downloaded > MAX_DOWNLOAD:
                raise ValueError("Portable archive exceeds the download limit")
            digest.update(block)
            output.write(block)
    if digest.hexdigest() != expected_digest:
        raise ValueError("Portable archive SHA-256 differs from the caller's pin")


def unpack_runtime(archive, target, version):
    root = f"MoonTxnWitness-v{version}"
    seen = set()
    runtime = []
    size = 0
    with ZipFile(archive) as zipped:
        for member in zipped.infolist():
            name = member.filename.rstrip("/")
            parts = name.split("/")
            if (parts[0] != root or any(part in ("", ".", "..") for part in parts)
                    or any("\\" in part or ":" in part or part.rstrip(" .") != part for part in parts)
                    or stat.S_ISLNK(member.external_attr >> 16)):
                raise ValueError("Unexpected portable archive member")
            key = name.casefold()
            if key in seen:
                raise ValueError("Duplicate portable archive member")
            seen.add(key)
            relative = "/".join(parts[1:])
            if not member.is_dir() and (relative == GATE or relative.startswith("dist/")):
                size += member.file_size
                if size > MAX_RUNTIME:
                    raise ValueError("Portable runtime exceeds the extraction limit")
                runtime.append(member)
        if not any(member.filename == f"{root}/{GATE}" for member in runtime):
            raise ValueError("Portable archive has no point-window verifier")
        for member in runtime:
            zipped.extract(member, target)
    return target / root / GATE


def run_check(inputs):
    version = inputs.get("MTW_RELEASE_VERSION", "")
    sha256 = inputs.get("MTW_PORTABLE_SHA256", "").lower()
    budget = inputs.get("MTW_MAX_POINT_CHECKS", "1000000")
    if not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version):
        raise ValueError("release-version must be a stable version such as 0.6.4")
    if not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise ValueError("portable-sha256 must be a 64-digit hexadecimal SHA-256")
    if not re.fullmatch(r"0|[1-9][0-9]{0,6}", budget) or int(budget) > 1_000_000:
        raise ValueError("max-point-checks must be an integer from 0 to 1000000")
    paths = {}
    for name in ("capsule", "config", "policy"):
        value = inputs.get(f"MTW_{name.upper()}", "")
        if not value or not Path(value).is_file():
            raise ValueError(f"A readable {name} file is required")
        paths[name] = Path(value).resolve()

    with tempfile.TemporaryDirectory(prefix="mtw-point-action-", dir=inputs.get("RUNNER_TEMP")) as temporary:
        work = Path(temporary)
        archive = work / "portable.zip"
        download_portable(version, sha256, archive)
        gate = unpack_runtime(archive, work, version)
        result = subprocess.run(
            ["node", str(gate), "--config", str(paths["config"]), "--policy", str(paths["policy"]),
             "--max-point-checks", budget, str(paths["capsule"])],
            cwd=work, capture_output=True, encoding="utf-8", timeout=180, check=False,
        )
    code = result.returncode
    if code == 2 and not result.stdout.strip():
        raise ValueError("Portable verifier could not read or verify the input")
    verdict = json.loads(result.stdout)
    if (not isinstance(verdict, dict) or code not in (0, 1, 2)
            or verdict.get("accepted") is not (code == 0)
            or verdict.get("verifiedRefutation") is not (code == 1)
            or (code in (0, 1) and verdict.get("sourceCoverageComplete") is not True)):
        raise ValueError("Portable verifier returned an inconsistent verdict")
    return code, verdict


def main():
    try:
        code, verdict = run_check(os.environ)
    except (OSError, ValueError, BadZipFile, subprocess.SubprocessError) as error:
        code, verdict = 2, {"accepted": False, "verifiedRefutation": False,
                            "status": "error", "reason": str(error)}
    encoded = json.dumps(verdict, ensure_ascii=True, separators=(",", ":"))
    if target := os.environ.get("GITHUB_OUTPUT"):
        with open(target, "a", encoding="utf-8", newline="\n") as output:
            output.write(f"exit-code={code}\nverdict={encoded}\n")
    print(encoded)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
