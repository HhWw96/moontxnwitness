"""Bounded static GitHub content download; no upstream code is executed."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
COMMIT = "4e359e597c52938b0afebb8bc42273914d68a424"
receipt = ROOT / "primary-download-attempt4.json"
if receipt.exists():
    raise RuntimeError("Refuse to replace a prior attempt")
rows = []
env = dict(os.environ)
try:
    login = subprocess.run(["gh", "auth", "token", "--user", "HhWw96"],
                           capture_output=True, text=True, timeout=10)
    if login.returncode:
        raise RuntimeError("Named-account credential lookup failed")
    env["GH_TOKEN"] = login.stdout.strip()
    for name in ("project.clj", "LICENSE"):
        target = ROOT / "primary-references" / name
        if target.exists():
            raise RuntimeError("Refuse an existing primary reference")
        result = subprocess.run(["gh", "api", "repos/jepsen-io/elle/contents/" + name + "?ref=" + COMMIT],
                                env=env, capture_output=True, timeout=20)
        if result.returncode:
            rows.append({"path": name, "success": False, "exitCode": result.returncode})
            continue
        if len(result.stdout) > 128 * 1024:
            raise RuntimeError("Unexpected API response size")
        entry = json.loads(result.stdout)
        if entry.get("type") != "file" or entry.get("path") != name or entry.get("encoding") != "base64":
            raise RuntimeError("Unexpected fixed source response")
        raw = base64.b64decode(entry["content"])
        if len(raw) > 65536 or len(raw) != entry["size"]:
            raise RuntimeError("Unexpected source size")
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        if blob != entry["sha"]:
            raise RuntimeError("Git blob content binding mismatch")
        raw.decode("utf-8")
        with target.open("xb") as file:
            file.write(raw)
        rows.append({"path": name, "success": True, "bytes": len(raw), "gitBlobSha1": blob,
                     "sha256": hashlib.sha256(raw).hexdigest(),
                     "url": "https://github.com/jepsen-io/elle/blob/" + COMMIT + "/" + name})
except Exception as error:
    rows.append({"success": False, "errorClass": type(error).__name__,
                 "reason": "Bounded source retrieval did not complete; credential contents are never recorded"})
finally:
    env.pop("GH_TOKEN", None)
    with receipt.open("x", encoding="utf-8", newline="\n") as file:
        json.dump({"schema": 1, "fixedCommit": COMMIT, "transport": "authenticated fixed-ref GitHub content API",
                   "upstreamCodeExecuted": False, "files": rows}, file, indent=2)
        file.write("\n")
print(json.dumps(rows))
