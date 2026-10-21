"""Bounded immutable license retrieval only; no launcher/model execution."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess

here = Path(__file__).resolve().parent
commit = "795c3a5d68de7a2465582da4184c42d7bd065c76"
receipt = here / "lein-license-download-attempt1.json"
if receipt.exists():
    raise RuntimeError("Refuse an old attempt receipt")
env = dict(os.environ)
out = {"schema": 1, "staticDownloadOnly": True, "runtimeExecuted": False,
       "commit": commit, "success": False}
try:
    token = subprocess.run(["gh", "auth", "token", "--user", "HhWw96"],
                           capture_output=True, text=True, timeout=10)
    if token.returncode:
        raise RuntimeError("Credential lookup failed")
    env["GH_TOKEN"] = token.stdout.strip()
    def api(path):
        result = subprocess.run(["gh", "api", path], env=env,
                                capture_output=True, timeout=20)
        if result.returncode or len(result.stdout) > 512 * 1024:
            raise RuntimeError("Bounded official API request failed")
        return json.loads(result.stdout)
    listing = api("repos/technomancy/leiningen/contents?ref=" + commit)
    names = [row["name"] for row in listing]
    out["rootNames"] = names
    candidates = [name for name in names if name.lower() in
                  {"copying", "license", "license.md", "license.txt", "copying.txt"}]
    if not candidates:
        raise RuntimeError("No root license entry found")
    files = []
    for name in candidates:
        entry = api("repos/technomancy/leiningen/contents/" + name + "?ref=" + commit)
        raw = base64.b64decode(entry["content"])
        if len(raw) > 128 * 1024 or len(raw) != entry["size"]:
            raise RuntimeError("Unexpected immutable license size")
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        if blob != entry["sha"]:
            raise RuntimeError("License Git blob differs")
        target = here / ("leiningen-" + name)
        with target.open("xb") as stream:
            stream.write(raw)
        files.append({"path": target.name, "upstreamPath": name,
                      "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                      "gitBlobSha1": blob,
                      "url": "https://github.com/technomancy/leiningen/blob/" + commit + "/" + name})
    out.update(success=True, files=files)
except Exception as error:
    out.update(errorClass=type(error).__name__, reason="Bounded license retrieval did not complete")
finally:
    env.pop("GH_TOKEN", None)
    with receipt.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(out, stream, indent=2)
        stream.write("\n")
print(json.dumps(out))
