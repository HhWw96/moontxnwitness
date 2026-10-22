"""Static actual17/actual18 protocol variant. No core import or timing occurs here."""
from pathlib import Path
import ast
import hashlib
import json
HERE=Path(__file__).resolve().parent
SHA=lambda b:hashlib.sha256(b).hexdigest()
v2_raw=(HERE/"preparation-manifest.v2.json").read_bytes()
assert SHA(v2_raw)=="c98163a730d4d7c38f5952a4c75d9a1d66eca319d36ded06402d29a84dc84158"
v2=json.loads(v2_raw)
for row in v2["files"]:
    raw=(HERE/row["file"]).read_bytes();assert len(raw)==row["bytes"] and SHA(raw)==row["sha256"],row["file"]
def put(name,raw):
    with (HERE/name).open("xb") as f:f.write(raw)
worker=(HERE/"worker-v2.mjs").read_text(encoding="utf-8")
changes=[
    ("{readFileSync,writeFileSync}","{readFileSync,writeFileSync,existsSync}"),
    ("import {historyText} from './logical-history.mjs';","import {historyText} from './logical-history.mjs';\nimport {projectEngineHeader} from './engine-header-projection-v3.mjs';"),
    ("assert.equal(core.version(),'0.1.5');","assert.equal(core.version(),job.expectedVersion);assert.ok((job.engine==='baseline'&&job.expectedVersion==='0.1.7')||(job.engine==='current'&&job.expectedVersion==='0.1.8'));"),
]
for before,after in changes:
    assert worker.count(before)==1,before
    worker=worker.replace(before,after)
old_check=next(line for line in worker.splitlines() if line.startswith("const checkOutput="))
new_check="""const checkOutput=value=>{try{const text=encode(value),projection=job.phase==='full'?projectEngineHeader(text,job.expectedVersion):null,projectedText=projection?projection.projectedText:text,rawDigest=hash(text),digest=hash(projectedText);if(job.expectedRawOutputSha256)assert.equal(rawDigest,job.expectedRawOutputSha256,'Native full output changed within this exact runtime');if(job.expectedOutputSha256)assert.equal(digest,job.expectedOutputSha256,'Projected complete output differs');if(job.phase==='full')assert.equal(JSON.parse(text).status,job.expectedStatus);return{text,projectedText,projection,rawDigest,digest,bytes:Buffer.byteLength(text),projectedBytes:Buffer.byteLength(projectedText)};}catch(error){if(!existsSync(job.firstFailureOutputPath))writeFileSync(job.firstFailureOutputPath,typeof value==='string'?value:JSON.stringify(value,(_k,v)=>typeof v==='bigint'?{'$moonbitInt64':v.toString()}:v),{flag:'wx'});throw error;}};"""
worker=worker.replace(old_check,new_check)
before="writeFileSync(job.fullOutputPath,first.text,{flag:'wx'});"
assert worker.count(before)==1
worker=worker.replace(before,before+"writeFileSync(job.projectedOutputPath,first.projectedText,{flag:'wx'});")
before="fullOutputSha256:first.digest,outputBytes:first.bytes,exactCompleteOutputValidated:true"
assert worker.count(before)==1
worker=worker.replace(before,"fullOutputSha256:first.digest,rawFullOutputSha256:first.rawDigest,projectedOutputSha256:first.digest,outputBytes:first.bytes,projectedOutputBytes:first.projectedBytes,engineMetadataProjection:first.projection?{path:first.projection.projectedPath,nativeEngine:first.projection.engineVersion,valueStart:first.projection.rawValueStart,valueEnd:first.projection.rawValueEnd,otherCharactersPreserved:true}:null,exactCompleteOutputValidated:true")
put("worker-v3.mjs",worker.encode())
put("binding_guard_v3.py",(HERE/"binding-guard-v3.py").read_bytes())
launcher=(HERE/"run-protocol-v2.py").read_text(encoding="utf-8")
launcher=launcher.replace("import time\n","import time\nfrom binding_guard_v3 import stage_bound_engines\n",1)
before='parser.add_argument("--authorization-sha256",required=True)'
assert launcher.count(before)==1
launcher=launcher.replace(before,before+'\n    parser.add_argument("--binding",type=Path,required=True)\n    parser.add_argument("--binding-sha256",required=True)')
before='assert auth["runPerformanceNow"] is True and auth["exclusiveMachine"] is True'
assert launcher.count(before)==1
launcher=launcher.replace(before,before+'\n    assert auth["allAgentsStopped"] is True and auth["runningNonMeasurementAgents"]==[]\n    assert auth["agentShutdownAttestation"] and "ROOT_MUST" not in auth["agentShutdownAttestation"]\n    binding_bytes=args.binding.read_bytes()\n    assert SHA(binding_bytes)==args.binding_sha256==auth["runtimeSourceBindingSha256"]\n    binding=json.loads(binding_bytes)')
assert launcher.count('HERE/"preparation-manifest.v2.json"')==1
launcher=launcher.replace('HERE/"preparation-manifest.v2.json"','HERE/"preparation-manifest.v3.json"')
begin=launcher.index('        engines={}\n')
end=launcher.index('        receipt["engines"]=engines\n',begin)
launcher=launcher[:begin]+'        engines=stage_bound_engines(binding,output)\n'+launcher[end:]
before='        receipt["measurementExecuted"]=True'
assert launcher.count(before)==1
replacement='''        receipt["runtimeSourceBindingSha256"]=args.binding_sha256
        receipt["baselineVersion"]="0.1.7"
        receipt["currentVersion"]="0.1.8"
        receipt["allAgentsStoppedAttestation"]=auth["agentShutdownAttestation"]
        receipt["allAgentsStoppedIndependentlyProven"]=False
        receipt["baselinePublicationReceipt"]=binding["baselinePublicationReceipt"]
        receipt["projectionPolicy"]="Validate actual core.version and each native /version header, tool/schema/algorithm; project only those two root JSON string spans. Every other character remains exact."
        projection_check=subprocess.run([str(node),str(HERE/"projection-self-check-v3.mjs")],capture_output=True,text=True,encoding="utf-8",timeout=30)
        (output/"projection-self-check.stdout.log").write_text(projection_check.stdout,encoding="utf-8")
        (output/"projection-self-check.stderr.log").write_text(projection_check.stderr,encoding="utf-8")
        assert projection_check.returncode==0,projection_check.stderr
        receipt["measurementExecuted"]=True'''
launcher=launcher.replace(before,replacement)
launcher=launcher.replace('def run(engine,case,phase,mode,batch,expected=None):','def run(engine,case,phase,mode,batch,expected=None,raw_expected=None):')
before='"expectedOutputSha256":expected,'
assert launcher.count(before)==1
launcher=launcher.replace(before,'"expectedOutputSha256":expected,"expectedRawOutputSha256":raw_expected,"expectedVersion":engines[engine]["version"],"projectedOutputPath":str(output/(stem+".projected-output.txt")),"firstFailureOutputPath":str(output/(stem+".first-failure-output.txt")),')
assert launcher.count('str(HERE/"worker-v2.mjs")')==1
launcher=launcher.replace('str(HERE/"worker-v2.mjs")','str(HERE/"worker-v3.mjs")')
assert launcher.count('row["version"]=="0.1.5"')==1
launcher=launcher.replace('row["version"]=="0.1.5"','row["version"]==engines[engine]["version"]')
assert launcher.count('return row,Path(job["fullOutputPath"])')==1
launcher=launcher.replace('return row,Path(job["fullOutputPath"])','return row,Path(job["projectedOutputPath"])')
# Engine role labels only, never fixture data, headers inside output or business strings.
launcher=launcher.replace('"candidate"','"current"')
before='"outputBytes":original["outputBytes"]})'
assert launcher.count(before)==1
launcher=launcher.replace(before,'"outputBytes":original["outputBytes"],"baselineRawOutputSha256":original["rawFullOutputSha256"],"currentRawOutputSha256":candidate["rawFullOutputSha256"],"projectionPolicy":receipt["projectionPolicy"]})')
before='                expected=original["fullOutputSha256"]'
assert launcher.count(before)==1
launcher=launcher.replace(before,before+'\n                raw_expected={"baseline":original["rawFullOutputSha256"],"current":candidate["rawFullOutputSha256"]}')
for mode in ["warm","cold"]:
    before='run(engine,case,phase,"'+mode+'",batch,expected)'
    assert launcher.count(before)==1
    launcher=launcher.replace(before,'run(engine,case,phase,"'+mode+'",batch,expected,raw_expected[engine])')
before='        for name,row in engines.items():assert SHA((ROOT/row["file"]).read_bytes())==row["sha256"] and SHA(Path(row["copy"]).read_bytes())==row["sha256"]'
assert launcher.count(before)==1
after=before+'''\n        for row in engines.values():
            for source_file in row["sourceFiles"]:assert SHA((Path(row["sourceRoot"])/source_file["file"]).read_bytes())==source_file["sha256"]
            assert SHA(Path(row["buildManifest"]["path"]).read_bytes())==row["buildManifest"]["sha256"]'''
launcher=launcher.replace(before,after)
ast.parse(launcher,filename="run-protocol-v3.py")
put("run-protocol-v3.py",launcher.encode())
readme="""# 正式已发布17 vs 实际18：perf-v3（只准备，未测量）

原v2全部22文件与严格同头原输出字节门禁保持原样，SHA仍为 `c98163a730d4d7c38f5952a4c75d9a1d66eca319d36ded06402d29a84dc84158`。本v3使用根后续外给的真实已发布17与实际18源码/core绑定，不再强制旧候选15版本。未构建、未外给SHA、未给本机独占与所有其他agent停止授权时不可执行。

```text
python -B artifacts/v018-performance-preparation/run-protocol-v3.py --binding RUNTIME_SOURCE_BINDING.json --binding-sha256 ROOT_BINDING_SHA --authorization AUTH.json --authorization-sha256 ROOT_AUTH_SHA
```

模板分别为 `runtime-source-binding-v3.template.json` 与 `authorization-v3.template.json`。两边版本固定baseline=0.1.7/current=0.1.8，需外给完整源码文件SHA/source fingerprint、core文件SHA、build-manifest SHA及已发布17收据绑定。先验证双方全部绑定，再复制核验过的实际core到D scratch，之后才允许import。独占与agent停止是根的显式声明，程序不把声明冒充独立证明。

固定7输入、每个phase的5预热/30样本/3批独立进程、typed History完整比较、median/P95/RSS/字节/冷启动与控制max10%或2ms协议完全不改。首调用仍是预热1。所有大型输出只写D，失败立即保留且不自动重试。

完整分析仍计时原实际core的 `analyze_options_json(input,'{}')` 调用，返回原生完整字符串。比较先检查core.version()，再分别严格核验两个报告的根/version为17/18、tool=MoonTxnWitness、schemaVersion=2、algorithm=bounded-register-v2.1。这里“两头”是两边报告各自唯一的根/version；不存在或不发明execution.engineVersion。

仅定位这两个根JSON字符串值的原文本span并投影为共同占位符；其他每一字符均原样保留，不JSON重序列化、不删字段、不排序报告、不全局替换版本。重复键、未知头/算法或额外差异均失败。来源、预算、计数、观察及业务版本字符串必须完全一致。额外纯投影自检含业务17/18字符串与预算篡改反例；只有正式授权运行时才执行它，准备阶段尚未执行。

每个引擎自己的原生完整输出SHA在所有样本中保持固定；跨版本只比较上述投影后的完整字节。原生完整输出与投影输出、两个摘要、实际metadata值和精确span均保留。typed History没有engine投影，继续完整公开字段、Map逻辑键值、数组顺序和Int64/None类型严格对照。

没有SDK/core import、性能测量或提速结论。实际17审查也仍等根的冻结信号。
"""
put("README-v3.md",readme.encode())
names=[row["file"] for row in v2["files"]]+["preparation-manifest.v2.json","prepare-v3.py","engine-header-projection-v3.mjs","projection-self-check-v3.mjs","binding-guard-v3.py","binding_guard_v3.py","runtime-source-binding-v3.template.json","authorization-v3.template.json","worker-v3.mjs","run-protocol-v3.py","README-v3.md"]
assert len(names)==len(set(names))
files=[]
for name in sorted(names):
    data=(HERE/name).read_bytes();files.append({"file":name,"bytes":len(data),"sha256":SHA(data)})
result={**{k:v for k,v in v2.items() if k not in {"files","engines","candidateFreezeSha256"}},"revision":3,"baselineVersion":"0.1.7","currentVersion":"0.1.8","runtimeAndSourceExternallyBound":True,"externalBindingStillRequired":True,"allAgentsStoppedAuthorizationRequired":True,"v2All22FilesUnchanged":True,"sameSevenInputsAndProtocol":True,"engineHeaderProjection":{"paths":["baseline report /version","current report /version"],"expectedVersions":["0.1.7","0.1.8"],"allOtherCharactersExact":True},"files":files}
put("preparation-manifest.v3.json",(json.dumps(result,ensure_ascii=False,indent=2)+"\n").encode())
for row in v2["files"]:assert SHA((HERE/row["file"]).read_bytes())==row["sha256"]
print(json.dumps({"prepared":True,"formalPerformanceMeasured":False,"coreImported":False,"v2All22FilesUnchanged":True,"cases":len(result["cases"]),"files":len(files),"manifestSha256":SHA((HERE/"preparation-manifest.v3.json").read_bytes())}))
