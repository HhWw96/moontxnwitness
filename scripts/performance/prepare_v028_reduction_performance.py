"""Prepare one preregistered hosted measurement; never executes an SDK or starts measurement."""
from __future__ import annotations
import argparse,hashlib,json,os,re,stat,subprocess,sys,zipfile
from pathlib import Path,PurePosixPath
PARENT="7359a1025a9c55d28121a937e66a318c93b74a8c"
BRANCH="experimental/v028-reduction-performance-20261025"
REPOSITORY="HhWw96/moontxnwitness"
BUNDLE_REL="scripts/performance/v028-reduction"
HELPER_REL="scripts/performance/prepare_v028_reduction_performance.py"
WORKFLOW_REL=".github/workflows/experimental-reduction-performance.yml"
PLAN_SHA="4f09d227801b316db95604f7dbd601aebd2f735c4a132e4334dec41b0d966641"
ARTIFACT_ID=12571426613
ARTIFACT_BYTES=12484724
ARTIFACT_SHA="17e80186010e7678da89497332c9f03ad07b774d5ce17cce168170079cbc5e8c"
ARTIFACT_MEMBERS=3007
ARTIFACT_UNCOMPRESSED=114726329
EXPECTED_BUNDLE=json.loads(r"""{"plan.json":{"bytes":44036,"sha256":"4f09d227801b316db95604f7dbd601aebd2f735c4a132e4334dec41b0d966641"},"common.mjs":{"bytes":13874,"sha256":"ac7fd8827e8a04689b9df25c4a55ded0e3b5c447b441f47f1108d8958a1aa8c9"},"run.mjs":{"bytes":10154,"sha256":"84e86070a0d40bdc34560df4b42d8b97260ddc3916f0a264351ba8f82ce7dce0"},"test_mock.mjs":{"bytes":9290,"sha256":"b093499aa4aba149ca7e55d8b7796a3b355ea39e2b27bb15e93e3cf92afe7dec"},"worker.mjs":{"bytes":3652,"sha256":"fb5b7c46c297a0ab8c2077394e71cd721a967b29485e8876ce30c59e459eda02"},"inputs/list.json":{"bytes":2100,"sha256":"ab2cb0407fc0a24ef98f45322c0c18b2b2b67b2d20d46716773601e99eca5ff4"},"inputs/relation.json":{"bytes":4053,"sha256":"34a1545ac2decc47a4508d0aa443c567f0a83f791fa05855a51ed06db5202c63"},"inputs/register.json":{"bytes":920,"sha256":"9c543184d10303efc0e6e3455787af780b3c2577c9342392729a58263784ee31"},"inputs/legacy.json":{"bytes":418,"sha256":"35033736727b7a3558ae340ec6e0081a8ee2c8145df0e998cd380e81bb586f8e"},"evidence/DIFFERENTIAL-REVIEW.json":{"bytes":2582,"sha256":"6a772d2abeb45638b2f71e2d9ccaeaf22cb5ae64c0fd1c8dabbbf86c255aca25"},"evidence/FULL-ORIGINAL-MEMBER-MANIFEST.json":{"bytes":532863,"sha256":"5bdd6783839a547650f993bd37b197db797c23380ff4e004176ce786541bbaff"},"evidence/REVIEW.json":{"bytes":6538,"sha256":"dafea426b1e4c8747154dcd864fece28251885f9a36c4f812ef881e6c05f3490"}}""")
ALLOWED_ADDITIONS=frozenset([HELPER_REL,WORKFLOW_REL,*[BUNDLE_REL+"/"+x for x in EXPECTED_BUNDLE]])
def require(ok,message):
    if not ok:raise ValueError(message)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def record(p):
    raw=Path(p).read_bytes()
    return {"bytes":len(raw),"sha256":sha(raw)}
def file_sha(p):
    h=hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda:f.read(1048576),b""):h.update(b)
    return h.hexdigest()
def save_new(p,obj):
    raw=obj if isinstance(obj,bytes) else (json.dumps(obj,ensure_ascii=False,indent=2)+"\n").encode("utf-8")
    with Path(p).open("xb") as f:f.write(raw);f.flush();os.fsync(f.fileno())
def plain(p,directory=None):
    p=Path(p);st=p.lstat()
    require(not stat.S_ISLNK(st.st_mode) and not getattr(st,"st_file_attributes",0)&0x400,"symlink/reparse refused: "+str(p))
    if directory is True:require(stat.S_ISDIR(st.st_mode),"plain directory required")
    elif directory is False:require(stat.S_ISREG(st.st_mode),"plain file required")
def ancestors(p):
    q=Path(p).absolute()
    for x in [q,*q.parents]:plain(x)
def relative(name):
    require(isinstance(name,str) and name and "\\" not in name and not name.startswith("/") and not re.search(r"[\x00-\x1f\x7f]",name),"unsafe ZIP/path member")
    s=name[:-1] if name.endswith("/") else name
    parts=s.split("/")
    require(all(x and x not in (".","..") and ":" not in x and not x.endswith(("."," ")) for x in parts),"unsafe member component")
    require(not any(re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)",x,re.I) for x in parts),"reserved device member")
    return s
def git(repo,*args):
    result=subprocess.run(["git","-C",str(repo),*args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=60)
    require(result.returncode==0,"read-only git command failed: "+repr(args)+" "+result.stderr.decode("utf-8","replace")[:2000])
    return result.stdout
def validate_context(context,event,head,parents,changed,status):
    require(context.get("GITHUB_ACTIONS")=="true" and context.get("RUNNER_OS")=="Linux","actual Linux hosted context required")
    require(context.get("GITHUB_REPOSITORY")==REPOSITORY and context.get("GITHUB_EVENT_NAME")=="push" and context.get("GITHUB_REF")=="refs/heads/"+BRANCH,"wrong repository/event/ref")
    require(re.fullmatch(r"[0-9a-f]{40}",head) is not None and context.get("GITHUB_SHA")==head,"HEAD/GITHUB_SHA mismatch")
    require(parents==[head,PARENT],"exact one parent7359 required")
    require(event.get("ref")=="refs/heads/"+BRANCH and event.get("after")==head and event.get("repository",{}).get("full_name")==REPOSITORY,"raw push event mismatched")
    require(event.get("head_commit",{}).get("id")==head,"push head_commit mismatched")
    require(changed=={x:"A" for x in ALLOWED_ADDITIONS},"only exact14 new source paths may differ from7359")
    require(status==b"","checkout must be actually clean")
    require(context.get("GITHUB_RUN_ATTEMPT")=="1","automatic/manual retry attempt refused; preserve first execution")
    require(re.fullmatch(r"[1-9][0-9]*",context.get("GITHUB_RUN_ID","")) is not None,"run identity missing")
    return True
def parse_changes(raw):
    fields=raw.split(b"\0");require(fields[-1:]==[b""],"unterminated Git status data");fields=fields[:-1]
    require(len(fields)%2==0,"non-addition/rename Git change shape")
    out={}
    for i in range(0,len(fields),2):
        op=fields[i].decode("ascii");name=fields[i+1].decode("utf-8")
        require(name not in out,"duplicate Git changed path")
        out[name]=op
    return out
def source_check(context):
    require(Path(context["GITHUB_WORKSPACE"]).is_absolute(),"absolute GitHub workspace required")
    repo=Path(context["GITHUB_WORKSPACE"]).absolute();ancestors(repo)
    head=git(repo,"rev-parse","HEAD").decode("ascii").strip()
    parents=git(repo,"rev-list","--parents","-n","1","HEAD").decode("ascii").strip().split()
    changed=parse_changes(git(repo,"diff-tree","--no-commit-id","--name-status","-r","-z",PARENT,"HEAD"))
    status=git(repo,"status","--porcelain=v1","--untracked-files=all")
    ep=Path(context["GITHUB_EVENT_PATH"]);require(ep.is_absolute(),"absolute event path required");plain(ep,False);raw_event=ep.read_bytes();event=json.loads(raw_event)
    validate_context(context,event,head,parents,changed,status)
    actual=[]
    for name in sorted(ALLOWED_ADDITIONS):
        p=repo/name;ancestors(p);plain(p,False)
        blob=git(repo,"show","HEAD:"+name);require(p.read_bytes()==blob,"working bytes != actual Git HEAD blob: "+name)
        actual.append({"path":name,"bytes":len(blob),"sha256":sha(blob)})
    bundle=repo/BUNDLE_REL
    seen=[]
    for parent,dirs,files in os.walk(bundle,followlinks=False):
        for d in dirs:plain(Path(parent)/d,True)
        for n in files:
            p=Path(parent)/n;plain(p,False);seen.append(p.relative_to(bundle).as_posix())
    require(set(seen)==set(EXPECTED_BUNDLE),"source bundle is not exact12 files")
    for name,expected in EXPECTED_BUNDLE.items():require(record(bundle/name)==expected,"frozen original bq bytes changed: "+name)
    require(file_sha(bundle/"plan.json")==PLAN_SHA,"original plan changed")
    require(file_sha(repo/HELPER_REL)==context.get("MTW_HELPER_SHA"),"reviewed helper SHA mismatch")
    return repo,{"format":"moontxnwitness-hosted-performance-source-attestation/v1","head":head,"actualGitTree":git(repo,"rev-parse","HEAD^{tree}").decode("ascii").strip(),"parent":PARENT,"branch":BRANCH,"repository":REPOSITORY,"event":"push","actualEventSha256":sha(raw_event),"actualEventAfter":event["after"],"actualRun":context["GITHUB_RUN_ID"],"attempt":1,"sourceAdditionsOnly":actual,"parentProductSourceUnchanged":True,"actualGitClean":True,"planSha256":PLAN_SHA,"SDKCalledByHelper":False,"performanceMeasuredByHelper":False,"candidateAdopted":False}
def work_path(context):
    require(re.fullmatch(r"[1-9][0-9]*",context.get("GITHUB_RUN_ID","")) is not None,"run id")
    require(re.fullmatch(r"[1-9][0-9]*",context.get("GITHUB_RUN_ATTEMPT","")) is not None,"attempt id")
    require(Path(context["RUNNER_TEMP"]).is_absolute(),"absolute runner temp required")
    base=Path(context["RUNNER_TEMP"]).absolute();ancestors(base)
    return base/("moontxnwitness-v028-performance-"+context["GITHUB_RUN_ID"]+"-"+context["GITHUB_RUN_ATTEMPT"])
def copy_bundle(repo,work):
    dest=work/"bundle";require(not dest.exists(),"bundle destination exists");dest.mkdir()
    for name,expected in EXPECTED_BUNDLE.items():
        out=dest/relative(name);out.parent.mkdir(parents=True,exist_ok=True)
        save_new(out,(repo/BUNDLE_REL/name).read_bytes())
        require(record(out)==expected,"new bundle copy mismatch")
    return dest
def validate_artifact_metadata(meta):
    require(meta.get("id")==ARTIFACT_ID and meta.get("size_in_bytes")==ARTIFACT_BYTES,"wrong original artifact id/size")
    require(meta.get("digest")=="sha256:"+ARTIFACT_SHA and meta.get("expired") is False,"original artifact digest/expiry")
    require(meta.get("workflow_run",{}).get("head_sha")==PARENT,"artifact must be actual7359 hosted producer")
def validate_members(infos):
    require(len(infos)==ARTIFACT_MEMBERS and sum(i.file_size for i in infos)==ARTIFACT_UNCOMPRESSED,"actual original ZIP member/size totals")
    names=[];folded=set();types={}
    for i in infos:
        base=relative(i.filename);require(i.filename not in names and i.filename.casefold() not in folded,"duplicate/casefold ZIP member")
        names.append(i.filename);folded.add(i.filename.casefold())
        t=stat.S_IFMT(i.external_attr>>16)
        require(t in (0,stat.S_IFREG,stat.S_IFDIR) and not i.external_attr&0x400,"link/reparse/special ZIP member")
        require(not i.flag_bits&1 and i.compress_type in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED),"encrypted/unsupported ZIP entry")
        require(i.file_size>=0 and i.compress_size>=0,"negative member sizes")
        require(not i.is_dir() or i.file_size==0,"directory with nonempty payload")
        require(t!=stat.S_IFDIR or i.is_dir(),"directory mode/name conflict")
        require(t!=stat.S_IFREG or not i.is_dir(),"file mode/name conflict")
        require(base not in types,"file/directory member collision");types[base]="dir" if i.is_dir() else "file"
    for name in types:
        parts=name.split("/")
        for k in range(1,len(parts)):require(types.get("/".join(parts[:k]))!="file","file used as ZIP directory")
    return True
def inspect_archive(archive,plan):
    plain(archive,False);require(archive.stat().st_size==ARTIFACT_BYTES and file_sha(archive)==ARTIFACT_SHA,"whole original ZIP byte/digest mismatch")
    required={}
    for role in ("baseline","candidate"):
        rt=plan["runtimes"][role]
        require(rt["root"]=="runtimes/"+role+"/dist" and len(rt["files"])==102,"runtime plan shape")
        for f in rt["files"]:
            n=role+"/dist/"+relative(f["path"])
            require(n not in required,"duplicate expected runtime member");required[n]=(role,f)
    with zipfile.ZipFile(archive) as z:
        infos=z.infolist();validate_members(infos)
        runtime={i.filename:i for i in infos if not i.is_dir() and (i.filename.startswith("baseline/dist/") or i.filename.startswith("candidate/dist/"))}
        require(set(runtime)==set(required),"entire runtime member sets must exactly match both102 manifests")
        for name,(role,f) in required.items():
            require(runtime[name].file_size==f["bytes"],"runtime ZIP length mismatch")
        return required
def extract_runtime(archive,bundle,plan):
    required=inspect_archive(archive,plan)
    out=bundle/"runtimes";require(not out.exists(),"runtime destination already exists");out.mkdir()
    for role in ("baseline","candidate"):(out/role/"dist").mkdir(parents=True)
    observed=[]
    with zipfile.ZipFile(archive) as z:
        for name in sorted(required):
            role,expected=required[name];raw=z.read(name)
            require(len(raw)==expected["bytes"] and sha(raw)==expected["sha256"],"runtime original byte mismatch: "+name)
            target=bundle/plan["runtimes"][role]["root"]/relative(expected["path"])
            target.parent.mkdir(parents=True,exist_ok=True);ancestors(target.parent);save_new(target,raw)
            require(record(target)=={"bytes":expected["bytes"],"sha256":expected["sha256"]},"runtime disk copy mismatch")
            observed.append({"role":role,"path":expected["path"],"bytes":len(raw),"sha256":sha(raw)})
    for role in ("baseline","candidate"):
        root=bundle/plan["runtimes"][role]["root"];seen=[]
        for parent,dirs,files in os.walk(root,followlinks=False):
            for d in dirs:plain(Path(parent)/d,True)
            for n in files:
                p=Path(parent)/n;plain(p,False);seen.append(p.relative_to(root).as_posix())
        require(set(seen)=={f["path"] for f in plan["runtimes"][role]["files"]} and len(seen)==102,"extracted runtime complete closure")
        require(json.loads((root/"build-manifest.json").read_text())==plan["runtimes"][role]["build"],"actual build manifest mismatch")
    return {"format":"moontxnwitness-hosted-performance-runtime-preparation/v1","passed":True,"originalArtifactId":ARTIFACT_ID,"originalArtifactBytes":ARTIFACT_BYTES,"originalArtifactSha256":ARTIFACT_SHA,"originalEntries":ARTIFACT_MEMBERS,"selectedRuntimeFiles":204,"filesPerRole":102,"originalNOTICEUnmodified":True,"selectedFiles":observed,"sourceOrInputOrSDKUnmodified":True,"SDKCalls":0,"performanceMeasured":False,"candidateAdopted":False}
def main():
    parser=argparse.ArgumentParser();parser.add_argument("phase",choices=("preflight","extract"));args=parser.parse_args()
    context=dict(os.environ)
    require(sys.platform=="linux","hosted preparation only runs on Linux")
    work=work_path(context)
    if args.phase=="preflight":
        require(not work.exists(),"fresh workroot required; no resumption");work.mkdir()
    else:plain(work,True)
    try:
        repo,attestation=source_check(context)
        if args.phase=="preflight":
            save_new(work/"source-attestation.json",attestation)
            bundle=copy_bundle(repo,work)
            save_new(work/"PREFLIGHT.json",{"passed":True,"workRoot":str(work),"bundle":str(bundle),"actualSource":attestation["head"],"planSha256":PLAN_SHA,"retries":0,"SDKCalls":0,"performanceMeasured":False})
        else:
            require(not (work/"runtime-preparation.json").exists(),"extraction cannot resume or rerun")
            first=json.loads((work/"source-attestation.json").read_text())
            require(first==attestation,"actual source changed after preflight")
            bundle=work/"bundle"
            for n,e in EXPECTED_BUNDLE.items():require(record(bundle/n)==e,"frozen bundle changed before runtime extraction")
            metadata=json.loads((work/"artifact-metadata.original.json").read_text());validate_artifact_metadata(metadata)
            plan=json.loads((bundle/"plan.json").read_text())
            result=extract_runtime(work/"original-artifact.zip",bundle,plan)
            save_new(work/"runtime-preparation.json",result)
        print(json.dumps({"passed":True,"phase":args.phase,"workRoot":str(work),"SDKCalls":0,"performanceMeasured":False}))
    except BaseException as e:
        p=work/(args.phase+"-FIRST-FAILED.json")
        if not p.exists():save_new(p,{"passed":False,"phase":args.phase,"errorType":type(e).__name__,"error":str(e),"firstFailureOnly":True,"partialOriginalFilesRetained":True,"SDKCalls":0,"performanceMeasured":False})
        raise
if __name__=="__main__":main()
