"""Run only this fixture in a new, retained, explicitly owned PG18 instance."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[2]
DRAFT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", required=True, type=Path)
    parser.add_argument("--work-root", required=True, type=Path)
    args = parser.parse_args()
    parent = args.work_root.resolve()
    if not parent.is_relative_to(Path("D:/CodexScratch/MoonTxnWitness-v011-20261020").resolve()):
        raise ValueError("Dedicated task D-drive root required")
    parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="run-", dir=parent)).resolve()
    assert work.is_relative_to(parent)
    executable = args.python.resolve()
    if not executable.is_file(): raise ValueError("Python is missing")
    original = (ROOT / "artifacts/postgres18-tools/pgsql").resolve()
    if not (original / "bin/initdb.exe").is_file() or os.name != "nt": raise ValueError("Bundled Windows PG18 required")
    flags, drive, running = getattr(subprocess, "CREATE_NO_WINDOW", 0), None, False
    binaries, data = original / "bin", work / "data"
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", TEMP=str(work), TMP=str(work))
    sources = [*sorted(DRAFT.glob("*.py")), DRAFT / "plan.json"]
    def bindings():
        return {p.name: {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size} for p in sources}
    receipt = {"schema": 1, "actualPostgresExecution": False, "passed": False,
        "ownedDatabaseStopped": False, "formalPerformanceMeasurement": False,
        "sourceBindings": bindings(), "workDirectory": work.name}
    result_code = 1
    with (work / "control.log").open("ab") as log:
        def control(command, timeout=120):
            return subprocess.run([str(x) for x in command], stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, check=True, timeout=timeout, env=env, creationflags=flags)
        try:
            for letter in "RSTUVWXYZQ":
                if not Path(letter + ":/").exists(): drive = letter + ":"; break
            if drive is None: raise RuntimeError("No unused alias")
            control(["subst", drive, work])
            alias = Path(drive + "/")
            if alias.resolve() != work: raise ValueError("Alias ownership differs")
            env["MTW_PG_ALIAS"], env["MTW_PG_TARGET"] = str(alias / "pgsql"), str(original)
            control(["powershell", "-NoProfile", "-Command", "New-Item -ItemType Junction -Path $env:MTW_PG_ALIAS -Target $env:MTW_PG_TARGET | Out-Null"])
            binaries, data = alias / "pgsql/bin", alias / "data"
            password = secrets.token_hex(24)
            password_file = alias / "password.txt"
            password_file.write_text(password + "\n", encoding="ascii")
            control([binaries / "initdb.exe", "-D", data, "-U", "mtw", "--locale=C", "--encoding=UTF8", "--auth-host=scram-sha-256", "--auth-local=trust", "--pwfile=" + str(password_file)])
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0)); port = probe.getsockname()[1]
            control([binaries / "pg_ctl.exe", "-D", data, "-l", alias / "server.log", "-o", "-h 127.0.0.1 -p " + str(port), "-w", "start"])
            running = True
            connection_file = work / "connection.json"
            connection_file.write_text(json.dumps({"host": "127.0.0.1", "port": port, "dbname": "postgres", "user": "mtw", "password": password}), encoding="utf-8")
            env["MTW_PG_CONNECTION_FILE"] = str(connection_file)
            output = work / "draft-output"
            with (work / "fixture.log").open("ab") as child:
                result = subprocess.run([str(executable), "-B", str(DRAFT / "run_postgres.py"), "--schema", "mtw_relation_v3_" + uuid.uuid4().hex[:12], "--output", str(output)],
                    cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=child, stderr=subprocess.STDOUT, timeout=600, creationflags=flags)
            result_code = result.returncode
            path = output / "database-receipt.json"
            if path.is_file():
                payload = json.loads(path.read_text(encoding="utf-8"))
                raw = path.read_bytes()
                receipt.update(actualPostgresExecution=payload.get("actualPostgresExecution", False),
                    passed=result_code == 0 and payload.get("passed") is True,
                    databaseReceipt={"path": "draft-output/database-receipt.json", "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
        except BaseException as error:
            receipt["schedulerFailureClass"] = type(error).__name__
            result_code = 1
        finally:
            try:
                pid = data / "postmaster.pid"
                if running or pid.is_file():
                    lines = pid.read_text(encoding="utf-8").splitlines()
                    if Path(lines[1]).resolve() != (work / "data").resolve(): raise ValueError("Refusing stop outside this owned data directory")
                    control([binaries / "pg_ctl.exe", "-D", data, "-m", "fast", "-w", "stop"])
                receipt["ownedDatabaseStopped"] = True
            except BaseException as error:
                receipt.update(stopFailureClass=type(error).__name__, passed=False)
                result_code = 1
            if drive and receipt["ownedDatabaseStopped"]:
                try:
                    if Path(drive + "/").resolve() != work: raise ValueError("Refusing alias removal outside owned directory")
                    control(["subst", drive, "/D"])
                    receipt["ownedAliasRemoved"] = True
                except BaseException as error:
                    receipt.update(aliasFailureClass=type(error).__name__, passed=False)
                    result_code = 1
            receipt["sourceBindingsAfter"] = bindings()
            receipt["sourceBindingsUnchanged"] = receipt["sourceBindings"] == receipt["sourceBindingsAfter"]
            if not receipt["sourceBindingsUnchanged"]: receipt["passed"], result_code = False, 1
            (work / "scheduler-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print("Owned relation fixture " + ("passed" if receipt["passed"] else "failed") + "; retained " + work.name)
    print("Owned database stopped: " + str(receipt["ownedDatabaseStopped"]))
    return result_code


if __name__ == "__main__": raise SystemExit(main())
