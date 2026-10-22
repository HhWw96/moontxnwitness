"""Public relative-path semantic rerun only; no build, DB, network or performance."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parent
SHA=lambda b:hashlib.sha256(b).hexdigest()
parser=argparse.ArgumentParser()
parser.add_argument("--closure-sha256",required=True)
args=parser.parse_args()
raw=(ROOT/"public-closure.json").read_bytes()
assert SHA(raw)==args.closure_sha256
closure=json.loads(raw)
for row in closure["files"]:
    p=(ROOT/row["file"]).resolve()
    assert p.is_relative_to(ROOT)
    data=p.read_bytes()
    assert len(data)==row["bytes"] and SHA(data)==row["sha256"],row["file"]
freeze=ROOT/"public-root-freeze.json"
assert SHA(freeze.read_bytes())==closure["publicRootFreezeSha256"]
parent=ROOT/"reproduction-runs"
parent.mkdir(exist_ok=True)
out=Path(tempfile.mkdtemp(prefix="consumer-",dir=parent))
result=subprocess.run([sys.executable,"-B","review/run-review-v3-final.py","--freeze","public-root-freeze.json","--freeze-sha256",closure["publicRootFreezeSha256"]],cwd=ROOT,capture_output=True,text=True,encoding="utf-8",timeout=240)
(out/"stdout.log").write_text(result.stdout,encoding="utf-8")
(out/"stderr.log").write_text(result.stderr,encoding="utf-8")
receipt={"schema":1,"kind":"fresh-public-relative-path-actual17-reproduction","passed":False,"closureSha256":args.closure_sha256,"publicRootFreezeSha256":closure["publicRootFreezeSha256"],"originalPrivateRootFreezeSha256":closure["originalPrivateRootFreezeSha256"],"packagesExecuted":False,"packageReviewPending":True,"newCoreBuild":False,"actualDatabaseExecution":False,"networkUsed":False,"formalPerformanceMeasurement":False,"releaseAcceptance":False,"commandExitCode":result.returncode}
try:
    assert result.returncode==0,result.stderr+result.stdout
    summary=json.loads(result.stdout.strip().splitlines()[-1])
    assert summary["passed"] and summary["checks"]==85
    actual=ROOT/"review"/summary["receipt"]
    content=json.loads(actual.read_bytes())
    assert content["passed"] and content["checkCount"]==85 and content["packagesExecuted"] is False and content["packageReviewPending"] is True
    assert not any(not row["passed"] for row in content["checks"])
    for row in closure["files"]:
        data=(ROOT/row["file"]).read_bytes()
        assert len(data)==row["bytes"] and SHA(data)==row["sha256"]
    receipt.update(passed=True,checks=85,originalPublicFilesUnchanged=len(closure["files"]),actualReceipt={"file":actual.relative_to(ROOT).as_posix(),"sha256":SHA(actual.read_bytes())})
except Exception as error:
    receipt.update(errorClass=type(error).__name__,error=str(error))
with (out/"receipt.json").open("x",encoding="utf-8",newline="\n") as f:json.dump(receipt,f,indent=2);f.write("\n")
print(json.dumps({"passed":receipt["passed"],"checks":receipt.get("checks"),"receipt":(out/"receipt.json").relative_to(ROOT).as_posix()}))
raise SystemExit(0 if receipt["passed"] else 1)
