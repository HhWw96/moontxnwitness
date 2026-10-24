"""Prepare the four-worker bounded CPU diagnostic only. Never imports an SDK or starts profiling."""
from __future__ import annotations
import argparse,hashlib,json,os,re,sys
from pathlib import Path
PARENT="c96fc56339022e76c43775ad1fe4714c7e1f7fda"
BRANCH="experimental/v028-reduction-cpu-diagnostic-20261025"
REPOSITORY="HhWw96/moontxnwitness"
ORIGINAL_HELPER_REL="scripts/performance/prepare_v028_reduction_performance.py"
ORIGINAL_HELPER_SHA="44ef175fd01fac81c3b5a1c7c6015c6dc1af71242f4371febcd3b77c3389fe3a"
HELPER_REL="scripts/performance/prepare_v028_reduction_cpu.py"
WORKFLOW_REL=".github/workflows/experimental-reduction-cpu.yml"
CPU_REL="scripts/performance/v028-reduction-cpu"
CPU_FILES={'plan.json': {'bytes': 2106, 'sha256': '15b2aa0595e6e8b976a5cafaefc17b2b30485c206b2cd2f885bb8be8084c7660'}, 'profile-core.mjs': {'bytes': 5581, 'sha256': '80be62907ccc4f9158555a4c20e50f54b87bf4099cdabf6b86f13f12ef265501'}, 'run.mjs': {'bytes': 6449, 'sha256': '1d2634da66d5eb0897d733ce2dcabb2aac371a4fa2d50b7931c5266ceb5b75ff'}, 'worker.mjs': {'bytes': 5076, 'sha256': '93a7011904d84e4b7fe50dadb8ef509125651238833cee6cb45e554c60cf0af6'}}
PLAN_SHA=CPU_FILES["plan.json"]["sha256"]
ALLOWED_ADDITIONS=frozenset([HELPER_REL,WORKFLOW_REL,*[CPU_REL+"/"+n for n in CPU_FILES]])
def require(ok,message):
    if not ok:raise ValueError(message)
def sha(b):return hashlib.sha256(b).hexdigest()
def original_primitives(repo):
    p=Path(repo)/ORIGINAL_HELPER_REL
    raw=p.read_bytes()
    require(sha(raw)==ORIGINAL_HELPER_SHA,"exact reviewed original archive primitives")
    ns={"__name__":"frozen_archive_primitives","__file__":str(p)}
    exec(compile(raw,str(p),"exec"),ns)
    return ns
def validate_context(c,event,head,parents,changed,status):
    require(c.get("GITHUB_ACTIONS")=="true" and c.get("RUNNER_OS")=="Linux","actual Linux hosted context")
    require(c.get("GITHUB_REPOSITORY")==REPOSITORY and c.get("GITHUB_EVENT_NAME")=="push" and c.get("GITHUB_REF")=="refs/heads/"+BRANCH,"exact diagnostic repository/event/branch")
    require(re.fullmatch("[0-9a-f]{40}",head) is not None and c.get("GITHUB_SHA")==head,"actual Git HEAD")
    require(parents==[head,PARENT],"one exact c96 parent")
    require(changed=={p:"A" for p in ALLOWED_ADDITIONS} and status==b"","only exact six new source files/clean")
    require(event.get("ref")=="refs/heads/"+BRANCH and event.get("after")==head and event.get("head_commit",{}).get("id")==head and event.get("repository",{}).get("full_name")==REPOSITORY,"raw diagnostic push event")
    require(c.get("GITHUB_RUN_ATTEMPT")=="1" and re.fullmatch("[1-9][0-9]*",c.get("GITHUB_RUN_ID","")) is not None,"only first run attempt")
    return True
def source_check(c,old,repo):
    old["ancestors"](repo)
    head=old["git"](repo,"rev-parse","HEAD").decode().strip()
    parents=old["git"](repo,"rev-list","--parents","-n","1","HEAD").decode().strip().split()
    changes=old["parse_changes"](old["git"](repo,"diff-tree","--no-commit-id","--name-status","-r","-z",PARENT,"HEAD"))
    status=old["git"](repo,"status","--porcelain=v1","--untracked-files=all")
    ep=Path(c["GITHUB_EVENT_PATH"]);require(ep.is_absolute(),"absolute push event");old["ancestors"](ep);raw=ep.read_bytes()
    validate_context(c,json.loads(raw),head,parents,changes,status)
    files=[]
    for n in sorted(ALLOWED_ADDITIONS):
        p=repo/n;old["ancestors"](p);old["plain"](p,False)
        blob=old["git"](repo,"show","HEAD:"+n);require(p.read_bytes()==blob,"actual Git blob exact: "+n)
        files.append({"path":n,"bytes":len(blob),"sha256":sha(blob)})
    require(old["file_sha"](repo/HELPER_REL)==c.get("MTW_CPU_HELPER_SHA"),"externally reviewed diagnostic helper SHA")
    for n,e in CPU_FILES.items():require(old["record"](repo/CPU_REL/n)==e,"diagnostic source pin: "+n)
    for n,e in old["EXPECTED_BUNDLE"].items():require(old["record"](repo/old["BUNDLE_REL"]/n)==e,"inherited original bundle pin: "+n)
    return {"format":"moontxnwitness-hosted-cpu-diagnostic-source/v1","head":head,"parent":PARENT,"actualTree":old["git"](repo,"rev-parse","HEAD^{tree}").decode().strip(),"branch":BRANCH,"runId":c["GITHUB_RUN_ID"],"attempt":1,"rawEventSha256":sha(raw),"exactSixNewFiles":files,"parentProductSourceUnchanged":True,"originalFormalPerformanceToolsUnmodified":True,"formalPerformanceMeasurement":False,"SDKCallsByHelper":0,"candidateAdopted":False}
def work_path(c,old):
    base=Path(c["RUNNER_TEMP"]);require(base.is_absolute(),"absolute RUNNER_TEMP");old["ancestors"](base)
    require(re.fullmatch("[1-9][0-9]*",c.get("GITHUB_RUN_ID","")) is not None and c.get("GITHUB_RUN_ATTEMPT")=="1","run identity")
    return base/("moontxnwitness-v028-cpu-"+c["GITHUB_RUN_ID"]+"-1")
def main():
    ap=argparse.ArgumentParser();ap.add_argument("phase",choices=["preflight","extract"]);a=ap.parse_args()
    require(sys.platform=="linux","Linux hosted only")
    c=dict(os.environ);repo=Path(c["GITHUB_WORKSPACE"]);require(repo.is_absolute(),"absolute workspace")
    old=original_primitives(repo);work=work_path(c,old)
    if a.phase=="preflight":require(not work.exists(),"fresh no-resume workroot");work.mkdir()
    else:old["plain"](work,True)
    try:
        att=source_check(c,old,repo)
        if a.phase=="preflight":
            old["save_new"](work/"source-attestation.json",att)
            bundle=old["copy_bundle"](repo,work)
            cpu=bundle/"cpu";cpu.mkdir()
            for n,e in CPU_FILES.items():
                old["save_new"](cpu/n,(repo/CPU_REL/n).read_bytes());require(old["record"](cpu/n)==e,"copied diagnostic pin")
            old["save_new"](work/"PREFLIGHT.json",{"passed":True,"planSha256":PLAN_SHA,"SDKCalls":0,"formalPerformanceMeasurement":False})
        else:
            require(not (work/"runtime-preparation.json").exists(),"no resumed/repeated extraction")
            require(json.loads((work/"source-attestation.json").read_bytes())==att,"source changed after preflight")
            bundle=work/"bundle"
            for n,e in old["EXPECTED_BUNDLE"].items():require(old["record"](bundle/n)==e,"inherited bundle changed")
            for n,e in CPU_FILES.items():require(old["record"](bundle/"cpu"/n)==e,"diagnostic bundle changed")
            old["validate_artifact_metadata"](json.loads((work/"artifact-metadata.original.json").read_bytes()))
            result=old["extract_runtime"](work/"original-artifact.zip",bundle,json.loads((bundle/"plan.json").read_bytes()))
            result["diagnosticOnly"]=True;result["formalPerformanceMeasurement"]=False
            old["save_new"](work/"runtime-preparation.json",result)
        print(json.dumps({"passed":True,"phase":a.phase,"workRoot":str(work),"SDKCalls":0,"formalPerformanceMeasurement":False}))
    except BaseException as e:
        p=work/(a.phase+"-FIRST-FAILED.json")
        if not p.exists():
            try:old["save_new"](p,{"passed":False,"errorType":type(e).__name__,"error":str(e),"partialOriginalFilesNotDeleted":True,"firstFailureOnly":True,"SDKCallsByHelper":0,"formalPerformanceMeasurement":False})
            except BaseException as io:print("failure receipt persistence failed: "+str(io)+"; original: "+str(e),file=sys.stderr)
        raise
if __name__=="__main__":main()
