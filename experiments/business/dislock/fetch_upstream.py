"""Read-only upstream download; never runs an upstream installer or script.

Writes a new output directory strictly below this experiment's own directory.
The full fixed archive and selected untouched source/license files are retained.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import tarfile
import urllib.request
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent
REPOSITORY = "Actticus/dislock"
COMMIT = "f9946f07159054433d9071c3805e41223cb47856"
ARCHIVE_URL = "https://api.github.com/repos/" + REPOSITORY + "/tarball/" + COMMIT
MAX_ARCHIVE = 4 * 1024 * 1024
MAX_FILE = 1024 * 1024


def download(destination):
    destination = Path(destination).resolve()
    if ROOT not in destination.parents or destination.exists():
        raise ValueError("Use a new output directory inside experiments/business/dislock")
    request = urllib.request.Request(ARCHIVE_URL, headers={"User-Agent": "MoonTxnWitness-source-freeze"})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read(MAX_ARCHIVE + 1)
        final_url = response.url
    if len(raw) > MAX_ARCHIVE:
        raise ValueError("Upstream archive exceeded the download budget")
    selected = {}
    prefixes = set()
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        for member in archive.getmembers():
            parts = PurePosixPath(member.name).parts
            if not parts or any(p in (".", "..") or "\\" in p or ":" in p for p in parts):
                raise ValueError("Unsafe upstream archive path")
            prefixes.add(parts[0])
            if len(parts) == 1:
                continue
            relative = PurePosixPath(*parts[1:])
            wanted = str(relative) in ("LICENSE", "README.md", "pyproject.toml") or (
                len(relative.parts) == 2 and relative.parts[0] == "dislock" and relative.suffix == ".py")
            if not wanted:
                continue
            if not member.isfile() or member.size > MAX_FILE:
                raise ValueError("Expected a bounded regular source file")
            if str(relative) in selected:
                raise ValueError("Duplicate upstream file")
            with archive.extractfile(member) as source:
                selected[str(relative)] = source.read(MAX_FILE + 1)
    if len(prefixes) != 1 or not all(p in selected for p in (
            "LICENSE", "pyproject.toml", "dislock/__init__.py", "dislock/core.py",
            "dislock/_queries.py", "dislock/exceptions.py")):
        raise ValueError("The fixed archive did not contain the expected package")
    destination.mkdir(parents=True, exist_ok=False)
    archive_name = "dislock-" + COMMIT + ".tar.gz"
    with (destination / archive_name).open("xb") as output:
        output.write(raw)
    files = {}
    for relative, content in sorted(selected.items()):
        target = destination / "source" / relative
        if destination not in target.resolve().parents:
            raise ValueError("Resolved archive target escaped the experiment")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as output:
            output.write(content)
        files[relative] = {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}
    lock = {"repository": REPOSITORY, "commit": COMMIT, "archiveUrl": ARCHIVE_URL,
            "resolvedArchiveUrl": final_url, "archive": archive_name,
            "archiveSha256": hashlib.sha256(raw).hexdigest(), "archiveBytes": len(raw),
            "license": "MIT", "sourceModified": False, "upstreamCodeExecuted": False,
            "files": files}
    with (destination / "lock.json").open("x", encoding="utf-8", newline="\n") as output:
        json.dump(lock, output, ensure_ascii=False, indent=2)
        output.write("\n")
    return lock


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / "upstream"))
    args = parser.parse_args()
    lock = download(args.output)
    print(json.dumps({"status": "source-frozen", "commit": lock["commit"],
                      "archiveSha256": lock["archiveSha256"], "files": len(lock["files"]),
                      "upstreamCodeExecuted": False}))
