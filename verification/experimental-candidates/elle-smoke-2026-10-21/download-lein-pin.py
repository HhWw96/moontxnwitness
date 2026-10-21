"""Retrieve one immutable launcher reference, without executing the launcher."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess

here = Path(__file__).resolve().parent
receipt = here / "lein-primary-pin-attempt1.json"
if receipt.exists():
    raise RuntimeError("Refuse existing pin attempt")
env = dict(os.environ)
out = {"schema": 1, "runtimeExecuted": False, "success": False}
try:
    auth = subprocess.run(["gh", "auth", "token", "--user", "HhWw96"], capture_output=True, text=True, timeout=10)
    if auth.returncode:
        raise RuntimeError("Credential lookup failed")
    env["GH_TOKEN"] = auth.stdout.strip()
    def api(path):
        result = subprocess.run(["gh", "api", path], env=env, capture_output=True, timeout=20)
        if result.returncode or len(result.stdout) > 256 * 1024:
            raise RuntimeError("Bounded official API request failed")
        return json.loads(result.stdout)
    ref = api("repos/technomancy/leiningen/git/ref/tags/2.11.2")
    obj = ref["object"]
    if obj["type"] == "tag":
        obj = api("repos/technomancy/leiningen/git/tags/" + obj["sha"])["object"]
    if obj["type"] != "commit":
        raise RuntimeError("Launcher tag does not resolve to commit")
    commit = obj["sha"]
    entry = api("repos/technomancy/leiningen/contents/bin/lein?ref=" + commit)
    raw = base64.b64decode(entry["content"])
    if len(raw) > 65536 or len(raw) != entry["size"]:
        raise RuntimeError("Unexpected launcher source size")
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if blob != entry["sha"]:
        raise RuntimeError("Launcher Git blob differs")
    with (here / "primary-references/lein").open("xb") as file:
        file.write(raw)
    out.update(success=True, version="2.11.2", commit=commit, gitRef=ref, gitBlobSha1=blob,
               sourceSha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw),
               url="https://github.com/technomancy/leiningen/blob/" + commit + "/bin/lein")
except Exception as error:
    out.update(errorClass=type(error).__name__, reason="Bounded launcher source retrieval did not complete")
finally:
    env.pop("GH_TOKEN", None)
    with receipt.open("x", encoding="utf-8", newline="\n") as file:
        json.dump(out, file, indent=2)
        file.write("\n")
print(json.dumps(out))
