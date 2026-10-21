"""Independent fixed-commit transport, executable-byte and fresh-runtime audit.

Read-only GitHub APIs; no workflow dispatch, build, database or benchmark.
Only new scratch/evidence paths are written. Credentials never enter receipts.
"""
from __future__ import annotations
import argparse
import concurrent.futures
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

REPO = "HhWw96/moontxnwitness"
COMMIT = "f017c0dfe6b8f69c58034046cf9e37c9e7614137"
ROOT = Path(__file__).resolve().parents[2]
sha = lambda raw: hashlib.sha256(raw).hexdigest()
load = lambda path: json.loads(path.read_bytes())


def immutable(path, value):
    raw = value if isinstance(value, bytes) else (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf8")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
    return {"file": str(path), "bytes": len(raw), "sha256": sha(raw)}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(work, runs, wait_seconds, proxy=None):
    # Explicit OS-protected account, independent of another chat's active login
    # or inherited environment-token override. Never print the captured secret.
    env = {k: v for k, v in os.environ.items() if k not in ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN")}
    token = subprocess.run(["gh", "auth", "token", "--hostname", "github.com", "--user", "HhWw96"],
                           env=env, capture_output=True, check=True, timeout=20).stdout.decode().strip()
    assert token
    requests = []
    handlers = [NoRedirect]
    if proxy:
        assert proxy == "http://127.0.0.1:7897", "Only the user's existing loopback proxy is accepted"
        handlers.append(urllib.request.ProxyHandler({"https": proxy}))
    opener = urllib.request.build_opener(*handlers)

    def get(path, maximum=180 * 1024 * 1024):
        original = "https://api.github.com" + path if path.startswith("/") else path
        for attempt in range(1, 4):
            url = original
            try:
                for redirect in range(6):
                    parsed = urllib.parse.urlsplit(url)
                    assert parsed.scheme == "https"
                    headers = {"User-Agent": "MoonTxnWitness-independent-v3-checkpoint", "Accept": "application/vnd.github+json",
                               "X-GitHub-Api-Version": "2022-11-28"}
                    if parsed.hostname == "api.github.com":
                        headers["Authorization"] = "Bearer " + token
                    try:
                        response = opener.open(urllib.request.Request(url, headers=headers), timeout=40)
                    except urllib.error.HTTPError as error:
                        if error.code not in (301, 302, 303, 307, 308):
                            raise RuntimeError("GitHub HTTP status " + str(error.code)) from None
                        url = urllib.parse.urljoin(url, error.headers["Location"])
                        continue
                    with response:
                        body = response.read(maximum + 1)
                    assert len(body) <= maximum
                    requests.append({"apiPath": path if path.startswith("/") else "<signed-artifact-or-public-source>",
                                     "attempt": attempt, "redirects": redirect, "finalHost": parsed.hostname,
                                     "bytes": len(body), "sha256": sha(body)})
                    return body
                raise RuntimeError("HTTPS redirect bound exhausted")
            except (TimeoutError, urllib.error.URLError, RuntimeError) as error:
                requests.append({"apiPath": path if path.startswith("/") else "<download>", "attempt": attempt,
                                 "errorClass": type(error).__name__})
                if attempt == 3:
                    raise
                time.sleep(1)

    assert json.loads(get("/user", 1024 * 1024))["login"] == "HhWw96"
    if not runs:
        discovery = json.loads(get(f"/repos/{REPO}/actions/runs?head_sha={COMMIT}&per_page=20", 8 * 1024 * 1024))
        chosen = [run for run in discovery["workflow_runs"] if run["head_sha"] == COMMIT and run["path"] in
                  (".github/workflows/ci.yml", ".github/workflows/postgres.yml") and run["event"] == "push"]
        assert len(chosen) == 2 and len({run["path"] for run in chosen}) == 2
        runs = [run["id"] for run in chosen]
        immutable(work / "run-discovery.json", discovery)
        print(json.dumps({"progress": "discovered", "runs": [{"id": run["id"], "path": run["path"]} for run in chosen]}), flush=True)
    deadline = time.monotonic() + wait_seconds
    while True:
        states = [json.loads(get(f"/repos/{REPO}/actions/runs/{run}", 4 * 1024 * 1024)) for run in runs]
        assert all(state["head_sha"] == COMMIT for state in states)
        print(json.dumps({"progress": "remote-workflows", "states": [{"id": s["id"], "status": s["status"], "conclusion": s["conclusion"]} for s in states]}), flush=True)
        if all(state["status"] == "completed" for state in states):
            break
        if time.monotonic() >= deadline:
            immutable(work / "remote-wait-timeout.json", {"complete": False, "states": states, "requests": requests})
            return 3
        time.sleep(30)
    immutable(work / "completed-run-states.json", states)
    if not all(state["conclusion"] == "success" for state in states):
        immutable(work / "remote-first-failure.json", {"passed": False, "states": states, "requests": requests})
        return 1
    jobs_all, artifacts_all, downloads = [], [], []
    for state in states:
        run = state["id"]
        jobs_raw = get(f"/repos/{REPO}/actions/runs/{run}/jobs?per_page=100", 8 * 1024 * 1024)
        artifacts_raw = get(f"/repos/{REPO}/actions/runs/{run}/artifacts?per_page=100", 8 * 1024 * 1024)
        immutable(work / f"jobs-{run}.json", jobs_raw)
        immutable(work / f"artifacts-{run}.json", artifacts_raw)
        jobs, artifacts = json.loads(jobs_raw), json.loads(artifacts_raw)
        assert jobs["total_count"] == len(jobs["jobs"]) and artifacts["total_count"] == len(artifacts["artifacts"])
        assert all(job["head_sha"] == COMMIT and job["conclusion"] == "success" for job in jobs["jobs"])
        for artifact in artifacts["artifacts"]:
            assert not artifact["expired"] and artifact["workflow_run"]["head_sha"] == COMMIT
            downloads.append((artifact["name"] + ".zip", artifact["archive_download_url"], artifact["digest"]))
        for job in jobs["jobs"]:
            downloads.append((f"job-{job['id']}.log", f"/repos/{REPO}/actions/jobs/{job['id']}/logs", None))
        jobs_all.extend(jobs["jobs"])
        artifacts_all.extend(artifacts["artifacts"])
    downloads.append(("source-" + COMMIT + ".zip", f"/repos/{REPO}/zipball/{COMMIT}", None))

    def download(item):
        name, url, declared = item
        raw = get(url)
        result = immutable(work / name, raw)
        if declared:
            assert declared == "sha256:" + result["sha256"], "Downloaded artifact differs from GitHub digest"
        result.update({"file": name, "githubDigest": declared})
        print(json.dumps({"progress": "downloaded", **result}), flush=True)
        return result

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        downloaded = list(pool.map(download, downloads))
    immutable(work / "transport-audit.json", {"sourceCommit": COMMIT, "credentialLogin": "HhWw96", "jobs": jobs_all,
              "artifacts": artifacts_all, "downloads": downloaded, "requests": requests,
              "tokenPersisted": False, "authenticatedRedirectForwarding": False,
              "boundedRetries": 3, "requestTimeoutSeconds": 40, "downloadedAt": datetime.now(timezone.utc).isoformat()})
    return 0


def safe_extract(archive, destination):
    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(archive) as zipped:
        assert len(zipped.namelist()) == len(set(zipped.namelist())), "Duplicate archive entry"
        for member in zipped.infolist():
            assert (destination / member.filename).resolve().is_relative_to(destination.resolve()), "Unsafe archive path"
            assert not (member.external_attr >> 16) & 0o170000 == 0o120000, "Archive symlink is not required"
        zipped.extractall(destination)


def audit(work):
    transport = load(work / "transport-audit.json")
    assert transport["sourceCommit"] == COMMIT
    for item in transport["downloads"]:
        raw = (work / item["file"]).read_bytes()
        assert len(raw) == item["bytes"] and sha(raw) == item["sha256"]
        if item["githubDigest"]:
            assert item["githubDigest"] == "sha256:" + sha(raw)
    source_dir = work / "source"
    assert source_dir.is_dir(), "Use the independently safety-checked pre-extracted source archive"
    roots = list(source_dir.iterdir())
    assert len(roots) == 1 and roots[0].is_dir()
    source = roots[0]
    names = sorted(["moon.mod"] + [p.relative_to(source).as_posix() for p in (source / "src").rglob("*")
                   if p.is_file() and (p.suffix == ".mbt" or p.name == "moon.pkg")])
    fingerprint = hashlib.sha256()
    for name in names:
        fingerprint.update(name.encode() + b"\0")
        fingerprint.update((source / name).read_bytes())
        fingerprint.update(b"\0")
    source_hash = fingerprint.hexdigest()
    member_bindings, core_results = {}, []

    def digest_file(path):
        raw = path.read_bytes()
        return {"bytes": len(raw), "sha256": sha(raw)}

    for os_name in ("ubuntu-24.04", "windows-2022"):
        folder = work / ("artifact-" + os_name)
        assert folder.is_dir(), "Use the independently safety-checked pre-extracted artifact"
        summary, package = load(folder / "verification/summary.json"), load(folder / "verification/package.json")
        assert summary["passed"] and package["passed"]
        assert summary["coreTestsPerTarget"] == 398 and summary["executedTargets"] == ["js", "wasm-gc", "wasm"]
        assert (summary["oracleHistories"], summary["verifiedCycleCertificates"], summary["parserDifferentialInputs"], summary["cliChecks"],
                summary["captureCliChecks"], summary["experimentalPresenceCliChecks"]) == (10320, 6373, 2542, 75, 14, 26)
        bindings = summary["testedFileSha256"]
        non_dist = {name: expected for name, expected in bindings.items() if not name.startswith("dist/")}
        assert len(non_dist) == 266, "266 fixed-commit non-runtime tested-source bindings required"
        for name, expected in non_dist.items():
            actual = digest_file(source / name)
            assert actual["sha256"] == expected, "Public source does not match tested bytes: " + name
            member_bindings[os_name + ":source:" + name] = actual
        for name, expected in bindings.items():
            if name.startswith("dist/"):
                actual = digest_file(folder / name)
                assert actual["sha256"] == expected
                member_bindings[os_name + ":runtime:" + name] = actual
        manifest = load(folder / "dist/build-manifest.json")
        assert manifest == summary["buildManifest"] and manifest["sourceSha256"] == source_hash
        assert manifest["coreSha256"] == sha((folder / "dist/core.mjs").read_bytes())
        assert manifest["captureCoreSha256"] == sha((folder / "dist/capture-core.mjs").read_bytes())
        for name in ("sdk.mjs", "evidence.mjs", "moontxnwitness.mjs"):
            assert (folder / "dist" / name).read_bytes() == (source / "cmd" / name).read_bytes()
            assert (folder / "cmd" / name).read_bytes() == (source / "cmd" / name).read_bytes()
        v3 = summary["experimentalV3"]
        assert not v3["foundationOnly"] and v3["experimentalOnly"] and not v3["v011v012JointReleaseReady"] and not v3["fullBusinessLifecycle"] and not v3["formalPerformanceMeasured"]
        assert v3["independentReference"]["passed"] and v3["independentReference"]["cases"] == 57
        assert v3["acceptance"]["passed"] and v3["acceptance"]["checks"] == 167
        assert v3["journal"]["passed"] and v3["journal"]["testsRun"] == 64
        skipped = v3["journal"]["skipped"]
        assert len(skipped) <= (2 if os_name == "windows-2022" else 0)
        if skipped:
            assert all("symlink" in item["test"] and item["reason"] for item in skipped)
        assert v3["independentStorageAudit"]["passed"] and v3["independentStorageAudit"]["checks"] == 10
        for key in ("acceptance", "independentStorageAudit"):
            nested = v3[key]
            assert sha((folder / nested["receipt"]).read_bytes()) == nested["sha256"]
        assert package["sourceRebuilt"] and package["freshConsumerChecks"] == len(package["checks"]) == 68
        job = next(job for job in transport["jobs"] if os_name in job["name"])
        log_raw = (work / f"job-{job['id']}.log").read_bytes()
        log = re.sub(r"\x1b\[[0-9;]*m", "", log_raw.decode("utf8"))
        assert COMMIT in log
        counts = re.findall(r"Total tests: 398, passed: 398, failed: 0\.", log)
        assert len(counts) >= (4 if os_name == "ubuntu-24.04" else 3)
        assert re.search(r"Ran 62 tests in", log)
        native = next(step for step in job["steps"] if step["name"] == "Execute Native core on Linux")
        assert native["conclusion"] == ("success" if os_name == "ubuntu-24.04" else "skipped")
        if os_name == "ubuntu-24.04":
            start = log.index("##[group]Run node scripts/moon.mjs test --target native --deny-warn")
            end = log.index("##[group]", start + len("##[group]"))
            assert "Total tests: 398, passed: 398, failed: 0." in log[start:end]
        core_results.append({"os": os_name, "job": job["html_url"], "sourceBindingsMatched": len(non_dist),
                             "manifest": manifest, "executedTargets": summary["executedTargets"], "coreTestsPerTarget": 398,
                             "actualRuntimeFilesDownloaded": True, "nativeExecuted": os_name == "ubuntu-24.04",
                             "jobLogSha256": sha(log_raw), "v3Counts": {"reference": 57, "acceptance": 167, "journal": 64, "storageAudit": 10},
                             "freshPackageChecks": 68, "journalSkipped": v3["journal"]["skipped"]})
    pg = work / "artifact-postgres"
    assert pg.is_dir(), "Use the independently safety-checked pre-extracted PostgreSQL artifact"
    pg_base = pg / "verification" if (pg / "verification/postgres.json").exists() else pg
    assert set(load(pg_base / "postgres-ci-source.json").values()) == {COMMIT}
    pg_manifest = load(pg / "dist/build-manifest.json")
    assert pg_manifest["sourceSha256"] == source_hash
    assert pg_manifest["coreSha256"] == sha((pg / "dist/core.mjs").read_bytes())
    assert pg_manifest["captureCoreSha256"] == sha((pg / "dist/capture-core.mjs").read_bytes())
    legacy, capture = load(pg_base / "postgres.json"), load(pg_base / "capture-postgres.json")
    assert legacy["passed"] and legacy["actualDatabaseExecution"] and legacy["roundsPerScenario"] == 20
    assert len(legacy["cases"]) == 2 and all(len(c["results"]) == c["rounds"] == 20 for c in legacy["cases"])
    assert legacy["observedTransactions"] == 100 and legacy["oneMinimal"] and legacy["minimalTransactions"] == 2
    for case in legacy["cases"]:
        for result in case["results"]:
            expected = (2, 0, 0, []) if case["isolation"] == "REPEATABLE READ" else (1, 1, 1, ["40001"])
            assert case["isolation"] in ("REPEATABLE READ", "SERIALIZABLE")
            assert (result["initialConcurrentCommits"], result["initialConcurrentAborts"], result["finalOnCallCount"], result["sqlstates"]) == expected
    for filename, expected in legacy["files"].items():
        assert sha((pg_base / "releases/0.1.1/postgres" / filename).read_bytes()) == expected
    assert capture["passed"] and capture["actualDatabaseExecution"] and len(capture["scenarios"]) == 7 and capture["replayedCapsules"] == 4
    assert capture["captureSource"]["analysisCoreSha256"] == pg_manifest["coreSha256"]
    assert capture["captureSource"]["captureCoreSha256"] == pg_manifest["captureCoreSha256"]
    for key, path in (("adapterSha256", "integrations/python/moontxnwitness_capture/capture.py"),
                      ("fixtureSha256", "scripts/capture-postgres-test.py"), ("e2eSha256", "scripts/capture-postgres-e2e.mjs")):
        assert capture["captureSource"][key] == sha((source / path).read_bytes())
    profile = load(pg_base / "provenance-profile/ci/profile-receipt.json")
    assert profile["passed"] and len(profile["scenarios"]) == 4 and len(profile["rejections"]) == 11 and profile["replayedCapsules"] == 2
    dislock = load(pg_base / "business/dislock/ci/business-receipt.json")
    presence = load(pg_base / "provenance-presence/ci/presence-receipt.json")
    assert dislock["passed"] and dislock["actualDatabaseExecution"]
    assert presence["passed"] and presence["actualDatabaseExecution"]
    lifecycle_dir = pg_base / "v3/postgres-ci"
    database, modeled = load(lifecycle_dir / "database-receipt.json"), load(lifecycle_dir / "model-receipt.json")
    assert database["passed"] and database["actualDatabaseExecution"] and len(database["cases"]) == 6
    assert database["sourceSha256"] == sha((source / "experiments/lifecycle_v3/postgres.py").read_bytes())
    assert modeled["passed"] and not modeled["actualDatabaseExecution"] and len(modeled["cases"]) == 6
    assert modeled["rawDatabaseExecutionReceipt"]["sha256"] == sha((lifecycle_dir / "database-receipt.json").read_bytes())
    assert modeled["sourceSha256"] == sha((source / "experiments/lifecycle_v3/e2e.mjs").read_bytes())
    for binding in modeled["bindings"]:
        data = (lifecycle_dir / binding["file"]).read_bytes()
        assert len(data) == binding["bytes"] and sha(data) == binding["sha256"]
    for case in database["cases"]:
        trace_raw = (lifecycle_dir / case["trace"]).read_bytes()
        assert sha(trace_raw) == case["sha256"] and case["serverFinalVersion"] == "x0"
        events = [json.loads(line) for line in (lifecycle_dir / (case["name"] + ".events.jsonl")).read_bytes().splitlines()]
        assert events == json.loads(trace_raw)["events"]
        report = load(lifecycle_dir / (case["name"] + ".report.json"))
        assert report["status"] == "inconclusive" and report["normalized"]["observations"] == events
        assert any(gap["code"] == "unmapped_statement" for gap in report["coverage"]["gaps"])
        capsule = load(lifecycle_dir / (case["name"] + ".capsule.json"))
        for field in ("trace", "normalized", "report", "evidence"):
            assert sha(capsule[field + "Text"].encode()) == capsule[field + "Sha256"]
        assert json.loads(capsule["traceText"]) == json.loads(trace_raw) and json.loads(capsule["reportText"]) == report
    assert next(c for c in database["cases"] if c["name"] == "cursor-position-survives")["delivered"][2]["rows"] == [[1]]
    assert next(c for c in database["cases"] if c["name"] == "cursor-position-survives")["delivered"][4]["rows"] == [[2]]
    immutable(work / "member-bindings.json", member_bindings)
    static = {"passed": True, "sourceCommit": COMMIT, "computedMoonBitSourceSha256": source_hash,
              "core": core_results, "remoteDatabaseExecutionVerified": True, "legacyPgRoundsPerScenario": 20,
              "captureScenarios": 7, "ordinaryProfile": {"cases": 4, "rejections": 11, "capsules": 2},
              "dislockCases": len(dislock["scenarios"]), "presenceCases": len(presence["scenarios"]),
              "v3DatabaseCases": [case["name"] for case in database["cases"]], "v3ModelStatuses": [case["status"] for case in modeled["cases"]],
              "v3BindingsVerified": len(modeled["bindings"]), "actualCompiledBytesVerified": True}
    immutable(work / "static-audit.json", static)
    return source, pg_base, static



def extra_audit(work, source, pg_base):
    checked = []
    def bind(path, expected):
        raw = path.read_bytes()
        expected = {'sha256': expected} if isinstance(expected, str) else expected
        assert sha(raw) == expected['sha256'], str(path)
        if 'bytes' in expected:
            assert len(raw) == expected['bytes'], str(path)
        checked.append({'file': str(path.relative_to(work)), 'sha256': sha(raw), 'bytes': len(raw)})
    def source_bindings(mapping):
        for name, expected in mapping.items():
            bind(work / 'artifact-postgres' / name if name.startswith('dist/') else source / name, expected)
    def bindings(base, items):
        for item in items:
            bind(base / item['file'], item)
    def nested(base, value):
        if isinstance(value, dict):
            receipt = value.get('receipt')
            if isinstance(receipt, dict):
                bind(base / receipt['path'], receipt)
                assert load(base / receipt['path'])['passed']
            elif isinstance(receipt, str) and receipt.startswith('verification/'):
                raw = (base / receipt).read_bytes()
                if value.get('sha256'):
                    bind(base / receipt, value['sha256'])
                assert load(base / receipt)['passed']
            for key, child in value.items():
                if key != 'receipt': nested(base, child)
        elif isinstance(value, list):
            for child in value: nested(base, child)
    for os_name in ('ubuntu-24.04','windows-2022'):
        folder=work/('artifact-'+os_name)
        v=load(folder/'verification/summary.json')['experimentalV3']
        nested(folder,v)
        assert v['appendList']['independentReference']['cases']==20071
        assert v['appendList']['acceptance']['inputCases']==20071 and v['appendList']['acceptance']['differences']==0
        assert (v['appendList']['acceptance']['checks'],v['appendList']['acceptance']['tamperCases'])==(45,31)
        assert (v['boundedProtocolCollector']['testsRun'],v['postCloseIndependentAudit']['checks'])==(35,42)
        assert (v['fixedSqlDiagnostic']['originals'],v['fixedSqlDiagnostic']['mutations'],v['fixedSqlDiagnostic']['checks'])==(7,64,86)
        assert (v['explicitSqlPolicy']['cases'],v['explicitSqlPolicy']['tamper'],v['explicitSqlPolicy']['checks'])==(7,36,199)
        assert v['boundedProtocolCollector']['sourceSha256']==sha((source/'integrations/python/moontxnwitness_capture/capture_v3.py').read_bytes())
    d=pg_base/'list-v3/postgres-ci'
    db,model=load(d/'database-receipt.json'),load(d/'model-receipt.json')
    assert db['passed'] and db['actualDatabaseExecution'] and db['roundsPerScenario']==20 and not db['smokeOnly']
    assert model['passed'] and not model['actualDatabaseExecution'] and not model['automaticG2OrPLClassification']
    assert model['rawDatabaseExecutionReceipt']['sha256']==sha((d/'database-receipt.json').read_bytes())
    assert len(db['cases'])==len(model['cases'])==120
    assert len({(c['name'],c['round']) for c in db['cases']})==120
    assert len({c['name'] for c in db['cases']})==6
    source_bindings(model['sourceBindings'])
    bindings(d,model['bindings'])
    for case in db['cases']:
        assert case['passed']
        folder=d/case['directory'];bindings(folder,case['files'])
        trace=load(folder/'trace.json')
        events=[json.loads(line) for line in (folder/'events.jsonl').read_bytes().splitlines()]
        assert trace['events']==events
        report=load(folder/'report.json')
        assert report['status']==case['expectedModelStatus']
        assert report['normalized']['observations']==events
        capsule=load(folder/'capsule.json')
        assert json.loads(capsule['traceText'])==trace and json.loads(capsule['reportText'])==report
        for field in ('trace','normalized','report','evidence'):
            assert sha(capsule[field+'Text'].encode())==capsule[field+'Sha256']
    d=pg_base/'business/dislock/v3-ci'
    db,model=load(d/'database-receipt.json'),load(d/'model-receipt.json')
    assert db['passed'] and db['actualDatabaseExecution'] and len(db['cases'])==7
    assert db['sourceBindings']==db['sourceBindingsAfter'] and db['sourceBindingsUnchanged']
    assert model['passed'] and not model['actualDatabaseExecution'] and len(model['cases'])==7
    assert model['databaseReceiptSha256']==sha((d/'database-receipt.json').read_bytes())
    source_bindings(db['sourceBindings']);source_bindings(model['sourceBindings'])
    bindings(d,model['inputBindings']);bindings(d,model['outputBindings'])
    positive={'schedule-and-server-clock','acquire-heartbeat-cleanup','body-exception-cleanup'}
    for case in model['cases']:
        assert case['passed'] and case['status']=='inconclusive'
        assert case['explicitSqlPolicy']['policy']=='dislock-f9946f0-sql-proof-1'
        assert case['explicitSqlPolicy']['status']==('consistent' if case['name'] in positive else 'inconclusive')
        assert case['explicitSqlPolicy']['coverageComplete']==(case['name'] in positive)
    d=pg_base/'business/dislock/v3-commit-ci'
    db,model=load(d/'commit-receipt.json'),load(d/'model-receipt.json')
    assert db['passed'] and db['actualDatabaseExecution'] and db['sourceBindingsUnchanged']
    assert db['sourceBindings']==db['sourceBindingsAfter'];source_bindings(db['sourceBindings'])
    assert model['passed'] and (model['committed'],model['aborted'],model['unknown'])==(1,1,0)
    assert model['databaseReceiptSha256']==sha((d/'commit-receipt.json').read_bytes());bindings(d,model['bindings'])
    aborted=next(x for x in db['outcomes'] if x['outcome']=='server-confirmed-aborted')
    assert aborted['sqlstate']==aborted['diagnosticSqlstate']=='40001'
    assert aborted['pgresultPresent'] and aborted['originalExceptionIdentityPreserved']
    assert aborted['transactionStatus']=='IDLE' and aborted['idleRollbackAddedEvents']==0
    assert db['rollbackProof']==model['rollbackProof']
    immutable(work/'expanded-member-bindings.json',checked)
    return {'passed':True,'newBindingChecks':len(checked),'listDatabaseCases':120,'listScenarios':6,'listRoundsEach':20,
            'listInputRecordCount':20071,'listDistinctInputCount':10118,'dislockDefaultInconclusive':7,
            'dislockExplicitConsistent':3,'dislockExplicitInconclusive':4,'realCommitConfirmedAborted':1,
            'fullBusinessLifecycle':False,'formalPerformanceMeasured':False}

NODE_DRIVER = r'''
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {spawnSync} from 'node:child_process';
import * as sdk from './dist/sdk.mjs';
import * as evidence from './dist/evidence.mjs';
const base=process.cwd(), pg=process.argv[2], cases=[];
const load=p=>JSON.parse(readFileSync(p,'utf8'));
const output=resolve('audit-output');mkdirSync(output);
const check=(name,fn)=>{try{fn();cases.push({name,passed:true});}catch(e){cases.push({name,passed:false,error:String(e.message).replaceAll(base,'<fresh>').replaceAll(pg,'<downloaded-pg>')});}};
const trace=load('fixtures/v3/write-skew-safe-projection.json');
let report,proof;
check('v3-real-runtime-import-and-analysis',()=>{assert.equal(sdk.version(),'0.1.1');report=sdk.analyzeV3(trace);assert.equal(report.status,'violation');assert.equal(report.normalized.status,'ready');});
check('v3-report-verification',()=>assert.equal(sdk.verifyV3(trace,report).valid,true));
check('v3-capsule-and-replay',()=>{proof=sdk.makeCapsuleV3(trace,report);assert.equal(sdk.replayCapsuleV3(proof).valid,true);});
check('v3-recomputed-digest-forged-conclusion-rejected',()=>{const c=JSON.parse(proof),r=JSON.parse(c.reportText);r.status='consistent';c.reportText=JSON.stringify(r);c.reportSha256=(awaitHash(c.reportText));assert.equal(sdk.replayCapsuleV3(JSON.stringify(c)).valid,false);});
function awaitHash(text){return createHash('sha256').update(text).digest('hex');}
import {createHash} from 'node:crypto';
check('v3-own-read-before-rollback-observation-retained',()=>{const t=load('fixtures/v3/read-of-later-reverted-own-write.json'),n=sdk.normalizeCaptureV3(t);assert.equal(n.status,'ready');assert.deepEqual(n.observations,t.events);assert.notEqual(n.effects[0].revertedBy,null);assert.deepEqual(n.history.transactions[0].ops,[]);});
check('v3-own-read-after-rollback-remains-incomplete',()=>{const n=sdk.normalizeCaptureV3(load('fixtures/v3/read-after-rollback-revoked-own-write.json'));assert.equal(n.status,'inconclusive');assert.equal(n.history,null);assert.ok(n.coverage.gaps.some(g=>g.code==='own_read_mismatch'));});
check('v3-release-does-not-commit',()=>{const n=sdk.normalizeCaptureV3(load('fixtures/v3/release-is-not-commit.json'));assert.equal(n.status,'inconclusive');assert.equal(n.transactions[0].status,'unknown');});
check('v3-unknown-commit-not-cured-by-rollback',()=>{const r=sdk.analyzeV3(load('fixtures/v3/rollback-after-request-not-proof.json'));assert.equal(r.status,'inconclusive');assert.equal(r.evidence,null);});
check('v3-source-closure-and-budget',()=>{const t=load('fixtures/v3/reduction-source-closure.json'),z=sdk.reduceV3(t,{maxChecks:0}),r=sdk.reduceV3(t,{maxChecks:256});assert.equal(z.oneMinimal,false);assert.equal(z.checks,0);assert.equal(r.oneMinimal,true);assert.deepEqual(r.removed,['noise']);assert.deepEqual(r.report.normalized.transactions.map(t=>t.id),['source','A','B']);});
check('v3-disk-journal-export-runtime-analysis',()=>{const r=sdk.analyzeV3(load('journal-export.json'));assert.equal(r.status,'consistent');assert.equal(r.normalized.status,'ready');});
const old=load('examples/write-skew.json');let r1,p1,r2,p2;
check('legacy-v1-actual-core-analysis',()=>{r1=sdk.analyze(old);assert.equal(r1.status,'violation');});
check('legacy-v1-capsule-replay',()=>{p1=evidence.makeCapsule(JSON.stringify(old),r1);assert.equal(JSON.parse(p1).format,'moontxnwitness-replay/v1');assert.equal(evidence.replayCapsule(p1).valid,true);});
check('legacy-v2-balanced-actual-core-analysis',()=>{r2=sdk.analyzeWithOptions(old);assert.equal(r2.schemaVersion,2);assert.equal(r2.status,'violation');});
check('legacy-v2-capsule-replay',()=>{p2=evidence.makeCapsule(JSON.stringify(old),r2);assert.equal(JSON.parse(p2).format,'moontxnwitness-replay/v2');assert.equal(evidence.replayCapsule(p2).valid,true);});
check('capsule-generations-do-not-mix',()=>{assert.equal(sdk.replayCapsuleV3(p1).valid,false);assert.equal(sdk.replayCapsuleV3(p2).valid,false);assert.equal(evidence.replayCapsule(proof).valid,false);});
for(const name of ['read-before-rollback','read-after-rollback','released-child-parent-rollback','duplicate-name-reveal','repeated-rollback-target','cursor-position-survives'])check('downloaded-postgres-v3-'+name,()=>{const path=resolve(pg,'v3/postgres-ci',name),t=load(path+'.trace.json'),r=load(path+'.report.json');assert.equal(sdk.verifyV3(t,r).valid,true);const replay=sdk.replayCapsuleV3(readFileSync(path+'.capsule.json','utf8'));assert.equal(replay.valid,true);assert.equal(r.status,'inconclusive');assert.equal(r.evidence,null);assert.deepEqual(r.normalized.observations,t.events);assert.ok(r.coverage.gaps.some(g=>g.code==='unmapped_statement'));});
for(const name of ['rr','serial','mini'])check('downloaded-postgres-v2-'+name,()=>assert.equal(evidence.replayCapsule(readFileSync(resolve(pg,'releases/0.1.1/postgres',name+'.capsule.json'),'utf8')).valid,true));
writeFileSync(resolve(output,'v3-report.json'),JSON.stringify(report));writeFileSync(resolve(output,'v3-capsule.json'),proof);writeFileSync(resolve(output,'v1-capsule.json'),p1);writeFileSync(resolve(output,'v2-capsule.json'),p2);
function cli(name,args,code,predicate){check(name,()=>{const p=spawnSync(process.execPath,['dist/moontxnwitness.mjs',...args],{cwd:base,encoding:'utf8',windowsHide:true,timeout:30000,maxBuffer:8*1024*1024});const actual={args,exitCode:p.status,stdout:p.stdout,stderr:p.stderr,error:p.error?.name||null};writeFileSync(resolve(output,name+'.process.json'),JSON.stringify(actual,null,2));assert.equal(p.error,undefined);assert.equal(p.status,code,p.stderr);predicate(JSON.parse(p.stdout));});}
cli('cli-v3-ingest',['ingest-v3','fixtures/v3/write-skew-safe-projection.json'],0,r=>assert.equal(r.status,'ready'));
cli('cli-v3-analysis',['check-v3','fixtures/v3/write-skew-safe-projection.json'],1,r=>assert.equal(r.status,'violation'));
cli('cli-v3-verify',['verify-v3','fixtures/v3/write-skew-safe-projection.json','audit-output/v3-report.json'],0,r=>assert.equal(r.valid,true));
cli('cli-v3-replay',['replay-v3','audit-output/v3-capsule.json'],0,r=>assert.equal(r.valid,true));
cli('cli-v3-reduce',['reduce-v3','fixtures/v3/reduction-source-closure.json'],0,r=>assert.equal(r.oneMinimal,true));
cli('cli-v3-unknown',['check-v3','fixtures/v3/rollback-after-request-not-proof.json'],3,r=>assert.equal(r.status,'inconclusive'));
cli('cli-v3-invalid',['ingest-v3','fixtures/v3/wrong-schema.json'],2,r=>assert.equal(r.status,'invalid'));
cli('cli-v1-replay',['replay','audit-output/v1-capsule.json'],0,r=>assert.equal(r.valid,true));
cli('cli-v2-replay',['replay','audit-output/v2-capsule.json'],0,r=>assert.equal(r.valid,true));

const listDB=load(resolve(pg,'list-v3/postgres-ci/database-receipt.json'));
for(const c of listDB.cases)check('downloaded-list-'+c.name+'-'+c.round,()=>{
 const folder=resolve(pg,'list-v3/postgres-ci',c.directory),t=load(resolve(folder,'trace.json')),r=load(resolve(folder,'report.json'));
 assert.equal(sdk.verifyV3(t,r).valid,true);assert.equal(sdk.replayCapsuleV3(readFileSync(resolve(folder,'capsule.json'),'utf8')).valid,true);
 assert.equal(r.status,c.expectedModelStatus);assert.equal(r.modelDefinition.id,'append-list-serializable-v1');
});
const policy='dislock-f9946f0-sql-proof-1';
const sqlDB=load(resolve(pg,'business/dislock/v3-ci/model-receipt.json'));
for(const c of sqlDB.cases)check('downloaded-business-default-and-policy-'+c.name,()=>{
 const d=resolve(pg,'business/dislock/v3-ci',c.name),t=load(resolve(d,'capture.json')),r=load(resolve(d,'model-report.json')),s=load(resolve(d,'sql-proof-report.json'));
 assert.equal(sdk.verifyV3(t,r).valid,true);assert.equal(r.status,'inconclusive');assert.equal(sdk.replayCapsuleV3(readFileSync(resolve(d,'capsule.json'),'utf8')).valid,true);
 assert.equal(sdk.verifyV3(t,s).valid,true);assert.equal(s.status,c.explicitSqlPolicy.status);
 assert.deepEqual(sdk.normalizeCaptureV3(t,{sqlProof:policy}),s.normalized);
 assert.equal(sdk.replayCapsuleV3(readFileSync(resolve(d,'sql-proof-capsule.json'),'utf8')).valid,true);
});
check('downloaded-real-commit-40001-source-proof',()=>{
 const d=resolve(pg,'business/dislock/v3-commit-ci'),t=load(resolve(d,'capture.json')),r=load(resolve(d,'model-report.json'));
 assert.equal(sdk.verifyV3(t,r).valid,true);assert.equal(r.status,'inconclusive');assert.equal(r.normalized.transactions.filter(x=>x.status==='aborted').length,1);
 assert.equal(r.normalized.transactions.filter(x=>x.status==='unknown').length,0);assert.equal(sdk.replayCapsuleV3(readFileSync(resolve(d,'capsule.json'),'utf8')).valid,true);
});
check('explicit-sql-source-closure-reduction',()=>{
 const t=load('verification/v3/synthetic-dislock-source-closure-v1/trace.json'),r=sdk.reduceV3(t,{analysisOptions:{sqlProof:policy},maxChecks:256});
 assert.equal(r.status,'reduced');assert.equal(r.oneMinimal,true);assert.deepEqual(r.removed,['N']);assert.deepEqual(r.report.normalized.transactions.map(t=>t.id),['P','A','B']);
 assert.equal(sdk.verifyV3(r.reducedCapture,r.report).valid,true);
});
const sqlTrace=resolve(pg,'business/dislock/v3-ci/schedule-and-server-clock/capture.json');
cli('cli-explicit-sql-ingest',['ingest-v3',sqlTrace,'--sql-proof',policy],0,r=>assert.equal(r.status,'ready'));
cli('cli-explicit-sql-check',['check-v3',sqlTrace,'--sql-proof',policy],0,r=>assert.equal(r.status,'consistent'));
cli('cli-default-sql-stays-incomplete',['check-v3',sqlTrace],3,r=>assert.equal(r.status,'inconclusive'));
const listTrace=resolve(pg,'list-v3/postgres-ci/duplicate-business-values-00/trace.json');
cli('cli-append-list-check',['check-v3',listTrace],0,r=>assert.equal(r.status,'consistent'));

const result={passed:cases.every(c=>c.passed),checks:cases.length,cases,node:process.version,platform:process.platform,localDatabaseExecution:false,localBuild:false,authorRuntimeOrCacheUsed:false};writeFileSync(resolve(output,'fresh-result.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));if(!result.passed)process.exitCode=1;
'''

JOURNAL_DRIVER = r'''
import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'integrations/python'))
from moontxnwitness_capture.journal_v3 import SegmentedJournal,JournalReader
trace=json.loads(Path('fixtures/v3/initial-read-commit.json').read_bytes())
w=SegmentedJournal('fresh-journal')
for event in trace['events']:
    assert w.append(event).accepted
assert w.close(source_closed=True).complete
result=JournalReader('fresh-journal').export('journal-export.json',clock_domain=trace['clockDomain'],exclusive_writers=True)
raw=Path('journal-export.json').read_bytes()
assert result['bytes']==len(raw) and result['sha256']==hashlib.sha256(raw).hexdigest()
assert json.loads(raw)==trace
print(json.dumps({'passed':True,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'actualDatabaseExecution':False}))
'''


def fresh(work, source, pg_base):
    results = []
    for os_name in ("ubuntu-24.04", "windows-2022"):
        directory = work / ("fresh-" + os_name)
        shutil.copytree(source, directory)
        assert not any((directory / name).exists() for name in ("dist", "_build", "node_modules", ".local-toolchain.json"))
        shutil.copytree(work / ("artifact-" + os_name) / "dist", directory / "dist")
        immutable(directory / "independent-driver.mjs", NODE_DRIVER.encode())
        immutable(directory / "independent-journal.py", JOURNAL_DRIVER.encode())
        env = dict(os.environ)
        env["MTW_JOURNAL_SCRATCH"] = str(work)
        python = os.environ.get("MTW_PYTHON") or os.environ.get("PYTHON") or "python"
        processes = []
        for name, command in (("journal", [python, "-B", "independent-journal.py"]),
                              ("runtime", ["node", "independent-driver.mjs", str(pg_base)])):
            process = subprocess.run(command, cwd=directory, env=env, capture_output=True, text=True,
                                     encoding="utf8", errors="replace", timeout=120)
            value = {"name": name, "exitCode": process.returncode, "stdout": process.stdout, "stderr": process.stderr,
                     "command": [str(item).replace(str(directory), "<fresh>") for item in command]}
            immutable(directory / (name + "-process.json"), value)
            processes.append({"name": name, "exitCode": process.returncode, "stdoutSha256": sha(process.stdout.encode()),
                              "stderrSha256": sha(process.stderr.encode())})
            if process.returncode:
                results.append({"artifactOrigin": os_name, "passed": False, "processes": processes})
                print(json.dumps({"progress": "fresh-first-failure", "artifactOrigin": os_name, "process": name,
                                  "exitCode": process.returncode}), flush=True)
                break
        else:
            result = load(directory / "audit-output/fresh-result.json")
            assert result["passed"]
            results.append({"artifactOrigin": os_name, "passed": True, "processes": processes, "checks": result["checks"],
                            "node": result["node"], "hostPlatform": result["platform"],
                            "resultSha256": sha((directory / "audit-output/fresh-result.json").read_bytes()),
                            "actualCoreSha256": sha((directory / "dist/core.mjs").read_bytes()),
                            "actualCaptureCoreSha256": sha((directory / "dist/capture-core.mjs").read_bytes()),
                            "nodeDriverSha256": sha(NODE_DRIVER.encode()), "journalDriverSha256": sha(JOURNAL_DRIVER.encode()),
                            "cases": result["cases"]})
            print(json.dumps({"progress": "fresh-complete", "artifactOrigin": os_name, "checks": result["checks"], "passed": True}), flush=True)
    immutable(work / "fresh-audit.json", results)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["fetch", "audit"])
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--runs", type=int, nargs=2)
    parser.add_argument("--wait-seconds", type=int, default=1500)
    parser.add_argument("--proxy", choices=["http://127.0.0.1:7897"])
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    if args.phase == "fetch":
        try:
            return fetch(args.work, args.runs, args.wait_seconds, args.proxy)
        except Exception as error:
            immutable(args.work / ("transport-first-failure-" + str(time.time_ns()) + ".json"),
                      {"sourceCommit": COMMIT, "passed": False, "errorClass": type(error).__name__,
                       "tokenPersisted": False, "tlsVerificationDisabled": False})
            raise
    stamp = datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(":", "-").replace("+00-00", "Z")
    receipt = {"schema": 1, "scope": "Independent AI acceptance of a public development checkpoint and downloaded runtime bytes",
               "sourceCommit": COMMIT, "independentAIAcceptance": True, "humanAcceptance": False,
               "stableReleasePublished": False, "fullApplicationIntegration": False, "formalPerformanceGateEstablished": False,
               "localDatabaseExecution": False, "localBuild": False, "authorRuntimeOrCacheUsed": False,
               "complete": False, "passed": False, "auditScriptSha256": sha(Path(__file__).read_bytes())}
    try:
        source, pg_base, static = audit(args.work)
        static["expanded"] = extra_audit(args.work, source, pg_base)
        receipt["static"] = static
        receipt["fresh"] = fresh(args.work, source, pg_base)
        receipt["complete"] = True
        receipt["passed"] = all(item["passed"] for item in receipt["fresh"])
    except Exception as error:
        receipt["errorClass"] = type(error).__name__
        receipt["error"] = str(error).replace(str(ROOT), "<workspace>")
    receipt["retainedRawDirectory"] = str(args.work)
    if (args.work / "transport-audit.json").exists():
        transport = load(args.work / "transport-audit.json")
        receipt["transportAuditSha256"] = sha((args.work / "transport-audit.json").read_bytes())
        receipt["downloadedFiles"] = transport["downloads"]
        receipt["workflowRuns"] = [{key: run[key] for key in ("id", "html_url", "head_sha", "status", "conclusion", "run_attempt")}
                                   for run in load(args.work / "completed-run-states.json")]
    if (args.work / "member-bindings.json").exists():
        receipt["memberBindingsSha256"] = sha((args.work / "member-bindings.json").read_bytes())
    receipt["finishedAt"] = datetime.now(timezone.utc).isoformat()
    receipt["limitations"] = ["This is checkpoint acceptance, not a stable release or organizer acceptance.",
        "The independent runner is AI-operated; it is not participant/human sign-off.",
        "Raw SQL defaults remain conservative; only the explicit frozen dislock SQL proof can establish a scoped complete result.",
        "No new formal performance measurement, full application run or database workload was executed by this audit."]
    output = ROOT / "verification/v3" / ("independent-public-checkpoint-f017c0d-" + stamp + ".json")
    saved = immutable(output, receipt)
    print(json.dumps({"passed": receipt["passed"], "complete": receipt["complete"], "receipt": output.relative_to(ROOT).as_posix(),
                      "sha256": saved["sha256"], "error": receipt.get("error")}))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
