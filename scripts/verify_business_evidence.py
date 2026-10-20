"""Check published business artifact bindings without running a database.

--git verifies the actual HEAD blobs, catching checkout/commit transformations
that a working-tree-only check cannot see. No file is modified by this script.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent


def verify(use_git=False):
    receipts = sorted((ROOT / "verification/business/dislock").glob("run-*/business-receipt.json"))
    if not receipts:
        raise ValueError("No completed business receipt is present")
    files = 0

    def content(path):
        if use_git:
            return subprocess.check_output(["git", "show", "HEAD:" + path.relative_to(ROOT).as_posix()], cwd=ROOT)
        return path.read_bytes()

    for path in receipts:
        receipt = json.loads(content(path))
        if receipt.get("status") != "passed" or receipt.get("passed") is not True:
            raise ValueError("Incomplete receipt selected")
        for scenario in receipt["scenarios"]:
            bindings = scenario["artifactBindings"]
            required = {"trace", "coverage"}
            if scenario["expectedStatus"] == "ready":
                required |= {"history", "report", "capsule"}
            elif set(bindings) & {"history", "report", "capsule"}:
                raise ValueError("Incomplete scenario must not publish a complete history or capsule")
            if not required.issubset(bindings):
                raise ValueError("Required artifact binding is missing")
            for binding in bindings.values():
                name = binding["path"]
                relative = PurePosixPath(name)
                if (not isinstance(name, str) or not relative.parts or relative.is_absolute()
                        or ".." in relative.parts or "\\" in name or ":" in name):
                    raise ValueError("Artifact path must stay within its receipt directory")
                target = path.parent.joinpath(*relative.parts)
                if target.is_symlink() or not target.resolve().is_relative_to(path.parent.resolve()):
                    raise ValueError("Artifact path escapes the receipt directory")
                raw = content(target)
                if (len(raw) != binding["bytes"]
                        or hashlib.sha256(raw).hexdigest() != binding["sha256"]):
                    raise ValueError("Published artifact bytes differ: " + target.relative_to(ROOT).as_posix())
                files += 1
    return {"passed": True, "receipts": len(receipts), "artifactBindings": files,
            "source": "HEAD git blobs" if use_git else "working tree",
            "actualDatabaseExecution": False,
            "scope": "Byte bindings only; does not authenticate collection or certify application behavior"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--git", action="store_true")
    args = parser.parse_args()
    print(json.dumps(verify(args.git)))
