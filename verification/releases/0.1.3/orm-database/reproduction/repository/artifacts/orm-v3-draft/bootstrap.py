"""Import only a byte-checked frozen upstream tree; never run its build backend."""
from pathlib import Path
import hashlib
import json
import sys
import zipfile

DRAFT = Path(__file__).resolve().parent
ROOT = DRAFT.parents[1]
COMMIT = "6397ace506d829a2ee12786da5d724c3f4c6b634"
ARCHIVE_SHA256 = "5cb6a7059b99ccb565970b75e76e7d291f4db4843337be8dde63eb20e7a40458"
PREFIX = "fastapi-users-db-sqlalchemy-" + COMMIT
UPSTREAM = DRAFT / "upstream" / PREFIX


def verify_upstream():
    archive = DRAFT / "upstream-6397ace.zip"
    if hashlib.sha256(archive.read_bytes()).hexdigest() != ARCHIVE_SHA256:
        raise ValueError("Frozen upstream archive digest changed")
    bindings = {}
    with zipfile.ZipFile(archive) as source:
        for entry in source.infolist():
            if entry.is_dir():
                continue
            relative = Path(entry.filename)
            if relative.parts[0] != PREFIX or ".." in relative.parts or relative.is_absolute():
                raise ValueError("Unsafe source archive path")
            relative = Path(*relative.parts[1:])
            data = source.read(entry)
            if (UPSTREAM / relative).read_bytes() != data:
                raise ValueError("Frozen extracted source differs from archive")
            bindings[relative.as_posix()] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    tag = json.loads((DRAFT / "tag-v7.0.0.json").read_text(encoding="utf-8-sig"))
    annotated = json.loads((DRAFT / "tag-object-v7.0.0.json").read_text(encoding="utf-8-sig"))
    if tag["object"]["sha"] != annotated["sha"] or annotated["object"] != {
            "sha": COMMIT, "type": "commit",
            "url": "https://api.github.com/repos/fastapi-users/fastapi-users-db-sqlalchemy/git/commits/" + COMMIT}:
        raise ValueError("Official annotated tag does not bind expected commit")
    license_text = (UPSTREAM / "LICENSE").read_text(encoding="utf-8")
    if not license_text.startswith("MIT License\n\nCopyright (c) 2021 François Voron"):
        raise ValueError("Unexpected frozen source license")
    return {"repository": "https://github.com/fastapi-users/fastapi-users-db-sqlalchemy", "tag": "v7.0.0",
        "commit": COMMIT, "archiveSha256": ARCHIVE_SHA256, "license": "MIT", "sourceBindings": bindings}


verify_upstream()
sys.path.insert(0, str(ROOT / "integrations" / "python"))
sys.path.insert(0, str(UPSTREAM))
