"""One admitted original-eight Elle smoke; no import-time execution or provisioning."""
from pathlib import Path, PurePosixPath
import argparse,base64,contextlib,hashlib,json,os,re,signal,stat,subprocess,sys,traceback,zipfile
REPOSITORY="HhWw96/moontxnwitness"
BRANCH="experiment/elle-v028-smoke"
PARENT="092687468bdc999486fda16320669bcf49772b50"
SOURCE_PARENT="5d35a83c8fe6ca5f3fada41a88432833543075d7"
APP="experiments/elle/v028"
WORKFLOW=".github/workflows/elle-v028-smoke.yml"
NEW_FILES=frozenset((WORKFLOW,APP+"/hosted_smoke.py",APP+"/smoke-stage.json",APP+"/smoke-execution-source-manifest.json"))
RUNNER_LITERAL="/home/runner/work/_temp"
PRODUCER_LITERAL=RUNNER_LITERAL+"/mtw-elle-v028-runtime-first"
SMOKE_LITERAL=RUNNER_LITERAL+"/mtw-elle-v028-smoke-first"
ARCHIVE_LITERAL=RUNNER_LITERAL+"/mtw-elle-v028-smoke-runtime-original.zip"
ADMISSION_SHA="4381947aa2266616061d161f38e9b143818763d2a69a04e7199651e5853e805d"
ORIGINAL_MANIFEST_SHA="c22406bc6975f981144f42273734e227ec2ea42c448f4812408d318c0b946654"
CORE="4f9a73a5fe82478d913cb751ab68714d4ba0558c85b45a3933c6eb9a6c3078ef"
R4_CLOSURE="a27f9d17dc41a9c90d1bc851d3fdbb710ead594ce212edf5f86ce5d8f7744b0a"
VERIFY="748c6867ab44759239a6ee3a72fce8b0561ca5a725d5b3a95868fe4a47c692b2"
PLAN="90fd3ca8220ae1bd4cb726356b1adf7501804e10440d88e174e1d5de0539a8b7"
REQUEST="762cdfe9e9c2c5441911647b913b6ee49b46a5004f3c0588c358450fecb61616"
WRAPPER="533670da2f176194cfe4776309c7b6e42dc543dcf3e43109585b10c82346bf3b"
SUMMARY="28cc491ea897d7191ea6305219abdd1009d53b822a79cfccbac3d79dfdf1709c"
TRANSPORT="0664577c850598ac683f2c31f33c86e8da27a2011f694a8b147f1f91632964f0"
SDK_PIN="ef83cf8e4e053adefe2542ab87f0faf059c509cabe9d58db3d78ae8bec600539"
ARTIFACT_ID=12573702295
ARTIFACT_BYTES=41509254
ARTIFACT_SHA="2743c7e87adf2155fb20b737eada555ef3cd45f6e3f7ce956079175f979d3731"
INDEX_SHA="bf2c6ca0e75f0b66e9354c82566102017f8df237ba42d9da35e2ec977d2fd8bb"
RUNTIME_SHA="921768885e9203bbc39324f752b644e01fa2b19f701ebe5fe5e2714ebbaf036a"
RUNTIME_INDEX_SHA="0c31085a0ef67618be51e9d708e558f5eb9a8d608b64483d6b08757c0f316b33"
LOADER="import hashlib,sys;from pathlib import Path;p,h=sys.argv[1:3];b=Path(p).read_bytes();assert hashlib.sha256(b).hexdigest()==h;sys.argv=[p,*sys.argv[3:]];exec(compile(b,p,'exec'),{'__name__':'__main__','__file__':p,'__verified_source_sha256__':h})"
class HostedSmokeCancelled(Exception):
    """Reach the unchanged r4 Exception kill/wait path, including closed pipes."""
def need(value,message):
    if not value:raise ValueError(message)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def unique(pairs):
    result={}
    for k,v in pairs:
        need(k not in result,"Duplicate JSON key");result[k]=v
    return result
def decode(raw):return json.loads(raw,object_pairs_hook=unique)
def binding(p):
    count,h=0,hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda:f.read(65536),b""):count+=len(b);h.update(b)
    return {"bytes":count,"sha256":h.hexdigest()}
def plain(p):
    q=Path(p).absolute()
    for x in (q,*q.parents):
        st=x.lstat();need(not stat.S_ISLNK(st.st_mode) and not getattr(st,"st_file_attributes",0)&0x400,"Symlink/reparse ancestor refused")
def relative(name):
    need(type(name) is str and name and not name.startswith("/") and "\\" not in name and not re.search(r"[\x00-\x1f\x7f]",name),"Unsafe relative member")
    parts=name.split("/");need(all(x and x not in (".","..") and ":" not in x and not x.endswith(("."," ")) for x in parts),"Unsafe relative component")
    need(not any(re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)",x,re.I) for x in parts),"Reserved relative member")
    return name
def write_new(p,value):
    raw=value if isinstance(value,bytes) else (json.dumps(value,indent=2,sort_keys=True)+"\n").encode()
    with Path(p).open("xb") as f:f.write(raw);f.flush();os.fsync(f.fileno())
def pinned(p,pin,maximum=4*1024*1024):
    p=Path(p);plain(p);need(p.is_file() and p.stat().st_size<=maximum,"Pinned regular bounded file required")
    raw=p.read_bytes();need(len(raw)<=maximum and sha(raw)==pin,"Pinned raw bytes differ");return raw
def verified_module(path,pin,name):
    raw=pinned(path,pin,1024*1024);ns={"__name__":name,"__file__":str(path),"__verified_source_sha256__":pin}
    exec(compile(raw,str(path),"exec"),ns);return ns
def read_git(project,*args):
    result=subprocess.run(["git","-c","gc.auto=0",*args],cwd=project,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=60)
    need(result.returncode==0,"Read-only Git source check failed");return result.stdout
def validate_context(env,head,parents,changed,status,event):
    need(env.get("GITHUB_ACTIONS")=="true" and env.get("RUNNER_OS")=="Linux","Actual Linux hosted context required")
    need(env.get("GITHUB_REPOSITORY")==REPOSITORY and env.get("GITHUB_EVENT_NAME")=="push" and env.get("GITHUB_REF")=="refs/heads/"+BRANCH,"Dedicated smoke push only")
    need(re.fullmatch(r"[0-9a-f]{40}",head) is not None and env.get("GITHUB_SHA")==head and parents==[head,SOURCE_PARENT],"Exact checkout/event and single reviewed parent required")
    need(changed=={x:"M" for x in NEW_FILES if not x.endswith("/smoke-stage.json")} and status==b"","Only three reviewed modifications in an actually clean smoke checkout")
    need(env.get("GITHUB_RUN_ATTEMPT")=="1" and re.fullmatch(r"[1-9][0-9]*",env.get("GITHUB_RUN_ID","")) is not None,"Actual first run identity required; no retry")
    need(event.get("ref")==env["GITHUB_REF"] and event.get("after")==head and event.get("head_commit",{}).get("id")==head and event.get("repository",{}).get("full_name")==REPOSITORY,"Original push event differs")
    need(env.get("RUNNER_TEMP")==RUNNER_LITERAL,"Exact original literal RUNNER_TEMP required")
def parse_changes(raw):
    parts=raw.split(b"\0");need(parts[-1:]==[b""],"NUL Git change list required");parts=parts[:-1];need(len(parts)%2==0,"Only simple additions supported")
    result={}
    for k in range(0,len(parts),2):
        name=parts[k+1].decode("utf-8");need(name not in result,"Duplicate changed path");result[name]=parts[k].decode("ascii")
    return result
def validate_admission(stage):
    need(type(stage) is dict and type(stage.get("schema")) is int and stage.get("schema")==1 and stage.get("stage")=="original-eight-smoke" and stage.get("experimentBranch")==BRANCH,"Smoke-only stage required")
    need(stage.get("smokeExecutionAuthorized") is True and stage.get("actualSmokeAcceptedFor2000") is False,"Root smoke-only authorization required; future stage is not admitted")
    need(stage.get("sourceReviewPassed") is False and stage.get("readyForHostedSmoke") is False and stage.get("actualSmokeExecuted") is False and stage.get("actualSDKExecuted") is False and stage.get("actual2000Executed") is False,"Prepared source cannot manufacture execution results")
    need(stage.get("runtimeAdmissionSha256")==ADMISSION_SHA,"Externally trusted admission pin required")
    raw=base64.b64decode(stage["runtimeAdmissionOriginalBase64"],validate=True);need(len(raw)==1062 and sha(raw)==ADMISSION_SHA,"Actual original runtime admission bytes differ")
    a=decode(raw)
    expected={"producerRepository":REPOSITORY,"producerHeadSha":PARENT,"producerRunId":40126616353,"producerRunAttempt":1,"artifactId":ARTIFACT_ID,"artifactZipBytes":ARTIFACT_BYTES,"artifactZipSha256":ARTIFACT_SHA,"sourceManifestSha256":ORIGINAL_MANIFEST_SHA,"outputIndexSha256":INDEX_SHA,"runtimeManifestSha256":RUNTIME_SHA,"runtimeArtifactIndexSha256":RUNTIME_INDEX_SHA}
    need(a.get("approved") is True and a.get("actualEvidenceVerified") is True and a.get("actualSmokeAcceptedFor2000") is False,"Only independently admitted runtime accepted")
    need(all(type(a.get(k)) is type(v) and a[k]==v for k,v in expected.items()),"Actual runtime provenance differs")
    return raw,a
def validate_sources(project,manifest_raw,pin):
    need(re.fullmatch(r"[a-f0-9]{64}",pin) is not None and sha(manifest_raw)==pin,"External smoke source manifest pin differs")
    doc=decode(manifest_raw);old_raw=pinned(project/APP/"execution-source-manifest.json",ORIGINAL_MANIFEST_SHA);old=decode(old_raw)
    need(doc.get("originalSourceManifestSha256")==ORIGINAL_MANIFEST_SHA and doc.get("originalRuntimeAdmissionSha256")==ADMISSION_SHA,"Original source/admission pins differ")
    extra={APP+"/hosted_smoke.py",APP+"/smoke-stage.json"}
    need(type(old.get("files")) is dict and len(old["files"])==106 and set(doc.get("files",{}))==set(old["files"])|extra,"Exact106 original plus wrapper/stage required")
    for name,lock in old["files"].items():need(doc["files"][name]==lock,"Original106 source binding changed")
    for name,lock in doc["files"].items():
        path=project/relative(name);plain(path);need(binding(path)==lock,"Bound source bytes differ: "+name)
    stage=decode((project/APP/"smoke-stage.json").read_bytes());admission_raw,a=validate_admission(stage)
    r4=project/APP/"r4";r4raw=pinned(r4/"SOURCE-CLOSURE.json",R4_CLOSURE);closure=decode(r4raw)
    need(closure.get("fileCount")==53 and len(closure["files"])==53,"Original53 r4 closure required")
    for name,lock in closure["files"].items():need(binding(r4/relative(name))==lock,"Original r4 source changed")
    plan_raw=pinned(r4/"plans-final2/smoke-eight.json",PLAN);plan=decode(plan_raw)
    need(len(plan["cases"])==8 and plan.get("expectedTruthSuppliedToChecker") is False and plan.get("batchSha256")==REQUEST,"Only original8 plan accepted")
    need(binding(project/relative(plan["batchPath"]))=={"bytes":4703,"sha256":REQUEST},"Original8 request bytes differ")
    pinned(project/APP/"sdk-public027.json",SDK_PIN)
    return doc,admission_raw,a,plan

def source_check(project,pin,env):
    plain(project);head=read_git(project,"rev-parse","HEAD").decode().strip();parents=read_git(project,"rev-list","--parents","-n","1","HEAD").decode().strip().split()
    changes=parse_changes(read_git(project,"diff-tree","--no-commit-id","--name-status","-r","-z",SOURCE_PARENT,"HEAD"));status=read_git(project,"status","--porcelain=v1","--untracked-files=all")
    event_path=Path(env["GITHUB_EVENT_PATH"]);need(event_path.is_absolute(),"Absolute original event path required");plain(event_path);event_raw=event_path.read_bytes();validate_context(env,head,parents,changes,status,decode(event_raw))
    for name in NEW_FILES:need((project/name).read_bytes()==read_git(project,"show","HEAD:"+name),"Working source differs from actual Git blob")
    raw=(project/APP/"smoke-execution-source-manifest.json").read_bytes();doc,admission_raw,a,plan=validate_sources(project,raw,pin)
    return {"sourceCommit":head,"parent":SOURCE_PARENT,"producerParent":PARENT,"branch":BRANCH,"runId":int(env["GITHUB_RUN_ID"]),"runAttempt":1,"eventSha256":sha(event_raw),"smokeSourceManifestSha256":pin,"original106SourceFilesUnchanged":True,"original53R4ClosureUnchanged":True,"actualSourceFiles":{n:binding(project/n) for n in sorted(NEW_FILES)}},admission_raw,a,plan

def validate_metadata(meta):
    need(meta.get("id")==ARTIFACT_ID and meta.get("size_in_bytes")==ARTIFACT_BYTES and meta.get("digest")=="sha256:"+ARTIFACT_SHA and meta.get("expired") is False,"Actual original artifact metadata differs")
    need(meta.get("workflow_run",{}).get("id")==40126616353 and meta["workflow_run"].get("head_sha")==PARENT,"Original producer run/head required")
def validate_output_index(index):
    need(type(index.get("schema")) is int and index.get("schema")==1 and index.get("kind")=="runtime-producer-owned-output-index" and index.get("sourceRoot")==PRODUCER_LITERAL and index.get("runtimePassed") is True,"Original successful literal runtime output index required")
    need(type(index.get("files")) is dict and type(index.get("directories")) is list,"Complete file/directory index required")
    files=index["files"];dirs=index["directories"]
    names=list(files)+dirs;need(len({relative(n).casefold() for n in names})==len(names),"Duplicate/casefold file/directory index alias")
    for name,lock in files.items():need(type(lock.get("bytes")) is int and lock["bytes"]>=0 and re.fullmatch(r"[a-f0-9]{64}",lock.get("sha256","")) is not None,"Bound file size/hash required")
    for name in names:
        parts=name.split("/")
        for k in range(1,len(parts)):need("/".join(parts[:k]) in dirs,"Indexed parents must be explicit directories")
    need("OUTPUT-INDEX.json" not in files,"Output index self-binding is external")
    return index

def validate_members(infos,index):
    expected=set(index["files"])|{"OUTPUT-INDEX.json"};seen=set();folded=set();files=set()
    for info in infos:
        need(info.orig_filename==info.filename,"ZIP member name must not be NUL-truncated")
        name=info.filename[:-1] if info.is_dir() else info.filename;relative(name)
        need(name not in seen and name.casefold() not in folded,"Duplicate/casefold ZIP member");seen.add(name);folded.add(name.casefold())
        mode=stat.S_IFMT(info.external_attr>>16);need(mode in (0,stat.S_IFREG,stat.S_IFDIR) and not info.external_attr&0x400,"ZIP symlink/reparse/special member refused")
        need(not info.flag_bits&1 and info.compress_type in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED),"Encrypted/unsupported ZIP member")
        need(mode!=stat.S_IFDIR or info.is_dir(),"ZIP directory mode/name conflict");need(mode!=stat.S_IFREG or not info.is_dir(),"ZIP file mode/name conflict")
        if info.is_dir():need(name in index["directories"] and info.file_size==0,"Unexpected/nonempty ZIP directory")
        else:
            need(name in expected,"Unexpected ZIP file");files.add(name)
            size=122404 if name=="OUTPUT-INDEX.json" else index["files"][name]["bytes"];need(info.file_size==size,"ZIP file length differs")
    need(files==expected,"Whole original output ZIP closure differs")

def restore_members(z,dest,index,index_raw):
    need(not dest.exists(),"Original literal runtime output must be absent; no resumption")
    dest.mkdir()
    for name in sorted(index["directories"],key=lambda n:(n.count("/"),n)):(dest/relative(name)).mkdir()
    expected={**index["files"],"OUTPUT-INDEX.json":{"bytes":len(index_raw),"sha256":sha(index_raw)}}
    for name in sorted(expected):
        target=dest/relative(name);plain(target.parent);need(not target.exists(),"Restore destination collision")
        h,count=hashlib.sha256(),0
        with z.open(name) as src,target.open("xb") as out:
            while block:=src.read(65536):out.write(block);h.update(block);count+=len(block)
            out.flush();os.fsync(out.fileno())
        need({"bytes":count,"sha256":h.hexdigest()}==expected[name] and binding(target)==expected[name],"Restored original bytes differ")
    return expected

def closure(root):
    files,dirs={},[]
    for p in sorted(root.rglob("*")):
        plain(p)
        if p.is_dir():dirs.append(p.relative_to(root).as_posix())
        elif p.is_file():files[p.relative_to(root).as_posix()]=binding(p)
        else:raise ValueError("Nonregular owned output")
    return {"files":files,"directories":sorted(dirs)}

GENERATED_CLASS_POLICY="dom-top-1.0.11-mutableacc-original8-v1"
GENERATED_WRITER="runtime/runtime-home/.m2/repository/dom-top/dom-top/1.0.11/dom-top-1.0.11.jar"
GENERATED_WRITER_LOCK={"bytes":23699,"sha256":"d21401fbf7c5d4d1e59b1ac22093c7c708146a263f535b87cfd6074f55ba6633"}
GENERATED_CLASSES={
    "runtime/upstream/classes/dom_top/core/MutableAcc-Object-Object-Object.class":{"bytes":219,"sha256":"d76e6772c26914897d41db25f9da696d20462783eecd30cbab57fe98585d6f5d"},
    "runtime/upstream/classes/dom_top/core/MutableAcc-Object-Object.class":{"bytes":199,"sha256":"c36bd7a65cbe002e7e0dbadf38e0e573844f79cafe75169708f2752a458d1f6a"}}
GENERATED_DIRECTORIES=frozenset(("runtime/upstream/classes","runtime/upstream/classes/dom_top","runtime/upstream/classes/dom_top/core"))

def validate_runtime_delta(before,after):
    need(before["files"].get(GENERATED_WRITER)==GENERATED_WRITER_LOCK,"Original fixed dom-top writer jar binding differs")
    need(all(after["files"].get(n)==v for n,v in before["files"].items()),"An original runtime file was modified or deleted")
    need(set(before["directories"])<=set(after["directories"]),"An original runtime directory was deleted")
    need(not(set(GENERATED_CLASSES)&set(before["files"])) and not(GENERATED_DIRECTORIES&set(before["directories"])),"Generated output must not pre-exist in the admitted runtime")
    added={n:v for n,v in after["files"].items()if n not in before["files"]};dirs=set(after["directories"])-set(before["directories"])
    need((not added and not dirs)or(added==GENERATED_CLASSES and dirs==GENERATED_DIRECTORIES),"Only the exact two pinned generated classes and three parent directories may be added")
    return {"schema":1,"policy":GENERATED_CLASS_POLICY,"originalRuntimeFilesUnchanged":True,"runtimeUnchanged":not added and not dirs,"generatedFiles":added,"generatedDirectories":sorted(dirs),"writerJar":{"relativePath":GENERATED_WRITER,**GENERATED_WRITER_LOCK},"newOutputsAreObservedBytesNotCheckerResults":True}

def retain_bound_file(source,target,expected):
    plain(source);need(source.is_file() and source.stat().st_size==expected["bytes"],"Bound generated output size differs")
    raw=source.read_bytes();need({"bytes":len(raw),"sha256":sha(raw)}==expected,"Bound generated output bytes differ")
    write_new(target,raw);need(binding(target)==expected,"Retained generated output bytes differ")
    return binding(target)

def retain_generated_runtime_files(root,output,delta):
    need(binding(root/GENERATED_WRITER)==GENERATED_WRITER_LOCK,"Actual fixed dom-top writer jar bytes differ")
    evidence=output/"generated-runtime-classes";evidence.mkdir();retained={}
    write_new(output/"GENERATED-RUNTIME-OUTPUTS-BEFORE.json",{"policy":GENERATED_CLASS_POLICY,"actualObservedFiles":delta["generatedFiles"],"writerJar":delta["writerJar"],"copyCompleted":False})
    for name,expected in sorted(delta["generatedFiles"].items()):
        need(name in GENERATED_CLASSES and expected==GENERATED_CLASSES[name],"Generated evidence must use the fixed class whitelist")
        target=evidence/Path(name).name;retained[name]={"ownedEvidencePath":target.relative_to(output).as_posix(),**retain_bound_file(root/relative(name),target,expected)}
    write_new(output/"GENERATED-RUNTIME-OUTPUTS.json",{"schema":1,"policy":GENERATED_CLASS_POLICY,"writerJar":delta["writerJar"],"generatedDirectories":delta["generatedDirectories"],"retainedFiles":retained,"copyCompleted":True,"checkerSemanticsNotInferred":True})
    return binding(output/"GENERATED-RUNTIME-OUTPUTS.json")

def in_process(path,pin,args,logs):
    ns=verified_module(path,pin,"verified_smoke_"+path.stem);logs.mkdir();old_argv=sys.argv;old_signals={sig:signal.getsignal(sig) for sig in (signal.SIGTERM,signal.SIGINT)};attempted=False;returned=False;rc=None;primary=None;post=None
    def cancel_owned_checker(signum,frame):raise HostedSmokeCancelled("Hosted smoke cancelled; unwind original owned-group cleanup")
    try:
        for sig in old_signals:signal.signal(sig,cancel_owned_checker)
        sys.argv=[str(path),*args]
        with (logs/"stdout.raw").open("x",encoding="utf-8",newline="") as stdout,(logs/"stderr.raw").open("x",encoding="utf-8",newline="") as stderr:
            try:
                with contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):
                    attempted=True;rc=ns["main"]();returned=True
            except BaseException as e:
                primary=e
                try:traceback.print_exc(file=stderr)
                except Exception as diagnostic:post=diagnostic
            finally:
                for stream in (stdout,stderr):
                    try:stream.flush();os.fsync(stream.fileno())
                    except Exception as diagnostic:
                        if post is None:post=diagnostic
    except BaseException as e:
        if primary is None:primary=e
    finally:
        sys.argv=old_argv
        for sig,handler in old_signals.items():signal.signal(sig,handler)
        receipt={"sameByteInProcess":True,"sourceSha256":pin,"moduleMainAttempted":attempted,"moduleMainReturned":returned,"returnCode":rc,"coreMainAttempted":attempted if pin==CORE else None,"coreMainReturned":returned if pin==CORE else None,"exception":None if primary is None else {"class":type(primary).__name__,"message":str(primary),"systemExitCode":primary.code if isinstance(primary,SystemExit) else None},"diagnosticFailure":None if post is None else str(post),"ownedGroupCleanupUsesOriginalR4":True,"nestedOuterProcessGroupCreated":False}
        try:write_new(logs/"process.json",receipt)
        except Exception as diagnostic:
            if post is None:post=diagnostic
    if primary is not None:raise primary
    if post is not None:raise post
    return rc

def execute_smoke(project,output,archive,source,admission,plan):
    need(str(output)==SMOKE_LITERAL and str(archive)==ARCHIVE_LITERAL,"Fixed smoke output/archive paths required")
    need(not Path(PRODUCER_LITERAL).exists(),"Original literal producer root already exists")
    plain(archive);need(archive.is_file(),"Regular original archive required")
    need(binding(archive)=={"bytes":ARTIFACT_BYTES,"sha256":ARTIFACT_SHA},"Whole original runtime ZIP bytes differ")
    metadata=decode((output/"artifact-metadata.original.json").read_bytes());validate_metadata(metadata)
    with zipfile.ZipFile(archive) as z:
        candidates=[i for i in z.infolist() if i.filename=="OUTPUT-INDEX.json"];need(len(candidates)==1,"Unique original output index required")
        index_raw=z.read(candidates[0]);need(len(index_raw)==122404 and sha(index_raw)==INDEX_SHA,"Externally admitted output index differs")
        index=validate_output_index(decode(index_raw));validate_members(z.infolist(),index)
        restored=restore_members(z,Path(PRODUCER_LITERAL),index,index_raw)
    snapshot=closure(Path(PRODUCER_LITERAL));need(snapshot=={"files":restored,"directories":sorted(index["directories"])},"Complete original restore including empty/hidden directories differs")
    write_new(output/"RUNTIME-BEFORE.json",snapshot)
    r4=project/APP/"r4";runtime=Path(PRODUCER_LITERAL)/"runtime";core=verified_module(r4/"r4_controller.py",CORE,"verified_smoke_resource_core")
    resources=core["linux_resources"](output);write_new(output/"RESOURCE-GATE.json",resources);need(resources["passed"],"Original1.2GiB RAM/2GiB output gate unavailable")
    verify_args=["--root",str(runtime),"--index-sha256",RUNTIME_INDEX_SHA,"--runtime-sha256",RUNTIME_SHA,"--controller",str(r4/"r4_controller.py"),"--output",str(output/"runtime-restore-first.json")]
    smoke_args=["--execute","--plan",str(r4/"plans-final2/smoke-eight.json"),"--plan-sha256",PLAN,"--runtime",str(runtime/"runtime-manifest.json"),"--runtime-sha256",RUNTIME_SHA,"--wrapper",str(r4/"elle_batch_r4.clj"),"--summary",str(r4/"original-r3/result_summary.clj"),"--transport",str(r4/"original-r3/transport.clj"),"--output",str(output/"original-eight-first")]
    write_new(output/"ATTEMPT-BEFORE-INVOCATION.json",{"sameByteVerifierArgv":[sys.executable,"-B","-c",LOADER,str(project/APP/"supply/verify_restored_runtime.py"),VERIFY,*verify_args],"sameByteOriginalEightArgv":[sys.executable,"-B","-c",LOADER,str(r4/"r4_controller.py"),CORE,*smoke_args],"inputCases":plan["cases"],"runtimeAdmissionSha256":ADMISSION_SHA,"resourceGate":resources,"actualSmokeAcceptedFor2000":False,"SDKOrProvisioningCalled":False})
    attempted=False;rc=None;primary=None;delta=None;generated_evidence=None
    try:
        need(in_process(project/APP/"supply/verify_restored_runtime.py",VERIFY,verify_args,output/"restore-verifier-process")==0,"Original restore verifier failed, including actual host executable hashes")
        need(closure(Path(PRODUCER_LITERAL))==snapshot,"Verifier changed immutable original runtime")
        attempted=True;write_new(output/"ORIGINAL-EIGHT-INVOCATION-INTENT.json",{"attemptedOriginalR4Main":True,"inputPlanSha256":PLAN,"originalRequestsSha256":REQUEST,"expectedInputCount":8,"actualJavaStartedNotInferredFromRegistration":True})
        rc=in_process(r4/"r4_controller.py",CORE,smoke_args,output/"original-r4-process")
        need(rc==0,"Original8 transport failed; preserve all raw accounting and unknowns")
    except BaseException as e:primary=e;raise
    finally:
        try:
            after=closure(Path(PRODUCER_LITERAL));write_new(output/"RUNTIME-AFTER.json",after)
            delta=validate_runtime_delta(snapshot,after);write_new(output/"RUNTIME-DELTA.json",delta)
            generated_evidence=retain_generated_runtime_files(Path(PRODUCER_LITERAL),output,delta)
            need(closure(Path(PRODUCER_LITERAL))==after,"Runtime changed while retaining generated class evidence")
        except Exception as e:
            try:write_new(output/"RUNTIME-AFTER-FAILURE.json",{"error":str(e),"runtimeUnchanged":False})
            except Exception as diagnostic:
                (primary if primary is not None else e).add_note("Runtime-after-failure receipt could not be persisted: "+repr(diagnostic))
            if primary is None:raise
            primary.add_note("Runtime after-verification also failed: "+repr(e))
    return {"passed":True,"scope":"Original8 transport execution only; semantic/unknown results require independent raw review","source":source,"runtimeAdmissionSha256":ADMISSION_SHA,"originalArtifact":{"id":ARTIFACT_ID,"bytes":ARTIFACT_BYTES,"sha256":ARTIFACT_SHA},"coreMainAttempted":attempted,"coreMainReturned":True,"coreMainReturnCode":rc,"originalEightAccounting":binding(output/"original-eight-first/accounting.json"),"runtimeUnchanged":delta["runtimeUnchanged"],"originalRuntimeFilesUnchanged":True,"runtimeDeltaPolicy":GENERATED_CLASS_POLICY,"generatedOutputsEvidence":generated_evidence,"actualSDKExecuted":False,"actual2000Executed":False,"actualSmokeAcceptedFor2000":False,"noAgreementOrFutureAdmissionInferred":True,"automaticRetry":False}

def main():
    p=argparse.ArgumentParser();p.add_argument("--phase",choices=("preflight","execute"),required=True);p.add_argument("--source-manifest-sha256",required=True);a=p.parse_args()
    need(sys.platform=="linux" and sys.version_info[:2]==(3,12),"Linux Python3.12 hosted execution only")
    env=dict(os.environ);need(env.get("RUNNER_TEMP")==RUNNER_LITERAL,"Original literal runner temp required");parent=Path(RUNNER_LITERAL);plain(parent)
    project=Path.cwd().absolute();output=Path(SMOKE_LITERAL);archive=Path(ARCHIVE_LITERAL)
    if a.phase=="preflight":need(not output.exists() and not Path(PRODUCER_LITERAL).exists() and not archive.exists(),"Fresh exclusive smoke/runtime/archive paths required");output.mkdir()
    else:plain(output);need(output.is_dir() and not (output/"EXECUTION-STARTED.json").exists(),"First execution only; retain failed attempt")
    primary=None
    try:
        source,admission_raw,admission,plan=source_check(project,a.source_manifest_sha256,env)
        if a.phase=="preflight":
            write_new(output/"ORIGINAL-RUNTIME-ADMISSION.json",admission_raw);write_new(output/"SOURCE-ATTESTATION.json",source);write_new(output/"SMOKE-SOURCE-MANIFEST.original.json",(project/APP/"smoke-execution-source-manifest.json").read_bytes());write_new(output/"PREFLIGHT.json",{"passed":True,"source":source,"actualSDKExecuted":False,"actual2000Executed":False,"actualSmokeAcceptedFor2000":False})
        else:
            need(decode((output/"SOURCE-ATTESTATION.json").read_bytes())==source,"Source/context changed since preflight");pinned(output/"ORIGINAL-RUNTIME-ADMISSION.json",ADMISSION_SHA)
            write_new(output/"EXECUTION-STARTED.json",{"phase":"execute","oneShot":True,"source":source,"artifactId":ARTIFACT_ID,"actualSmokeAcceptedFor2000":False})
            result=execute_smoke(project,output,archive,source,admission,plan)
            after_source,_,_,_=source_check(project,a.source_manifest_sha256,env);need(after_source==source,"Execution source changed")
            write_new(output/"STAGE-RECEIPT.json",result)
    except BaseException as e:
        primary=e
        try:write_new(output/(a.phase+"-FIRST-FAILURE.json"),{"passed":False,"type":type(e).__name__,"reason":str(e),"firstFailureOnly":True,"automaticRetry":False,"actualCheckerResultsNotInferred":True,"rawOriginalR4AccountingIfPresent":"original-eight-first/accounting.json","actualSDKExecuted":False,"actual2000Executed":False,"actualSmokeAcceptedFor2000":False})
        except Exception as diagnostic:e.add_note("First-failure receipt could not be persisted: "+repr(diagnostic))
        raise
    finally:
        try:write_new(output/("OUTPUT-INDEX-"+a.phase+".json"),{"schema":1,"kind":"original-eight-smoke-owned-output-index","sourceRoot":str(output),"phase":a.phase,"originalRuntimeArtifactReference":{"id":ARTIFACT_ID,"bytes":ARTIFACT_BYTES,"sha256":ARTIFACT_SHA},**closure(output),"actualSmokeAcceptedFor2000":False,"automaticRetry":False})
        except Exception:
            if primary is None:raise
    return 0
if __name__=="__main__":raise SystemExit(main())