"""Static phase split only. Preserve every v2 byte and all semantic assertions."""
from pathlib import Path
import ast
import hashlib
import json
HERE=Path(__file__).resolve().parent
SHA=lambda b:hashlib.sha256(b).hexdigest()
raw=(HERE/"preparation-manifest.v2.json").read_bytes()
assert SHA(raw)=="a464db0a028761408caa17c2b5af94bcda6c3447c858c0912be1b0910ca698e5"
v2=json.loads(raw)
for row in v2["files"]:
    data=(HERE/row["file"]).read_bytes()
    assert len(data)==row["bytes"] and SHA(data)==row["sha256"],row["file"]
def put(name,raw):
    with (HERE/name).open("xb") as f:f.write(raw)
launcher=(HERE/"run-review.py").read_text(encoding="utf-8")
changes=[
    ('HERE/"preparation-manifest.v2.json"','HERE/"preparation-manifest.v3.json"'),
    ('assert {x["kind"] for x in frozen["packages"]}=={"source","portable"}','assert isinstance(frozen["packages"],list)\n        assert len(frozen["packages"])==0 or (len(frozen["packages"])==2 and {x["kind"] for x in frozen["packages"]}=={"source","portable"})\n        preflight["packagesExecuted"]=bool(frozen["packages"])\n        preflight["packageReviewPending"]=not bool(frozen["packages"])'),
    ('str(HERE/"run-tests.mjs")','str(HERE/"run-tests-v3.mjs")'),
]
for before,after in changes:
    assert launcher.count(before)==1,before
    launcher=launcher.replace(before,after)
ast.parse(launcher,filename="run-review-v3.py")
put("run-review-v3.py",launcher.encode())
worker=(HERE/"run-tests.mjs").read_text(encoding="utf-8")
assert worker.count("preparation-manifest.v2.json")==2
worker=worker.replace("preparation-manifest.v2.json","preparation-manifest.v3.json")
needle="actual17RuntimeExecuted:true,newCoreBuild:false"
assert worker.count(needle)==1
worker=worker.replace(needle,"actual17RuntimeExecuted:true,packagesExecuted:guard.packagesExecuted===true,packageReviewPending:guard.packageReviewPending===true,downloadAcceptance:false,formalPackageAcceptance:false,newCoreBuild:false")
put("run-tests-v3.mjs",worker.encode())
template=json.loads((HERE/"root-freeze.template.json").read_bytes())
template["packages"]=[]
template["packagePhase"]="Deferred. Source/runtime semantics first; package SHA and consumer acceptance are a separate second phase."
put("root-freeze-v3.template.json",(json.dumps(template,ensure_ascii=False,indent=2)+"\n").encode())
readme="""# 实际17独立审查 v3（仅准备，尚未执行）

原32文件v2及其准备清单完整保留，SHA仍为 `a464db0a028761408caa17c2b5af94bcda6c3447c858c0912be1b0910ca698e5`。v3只拆开阶段，避免“独立审查→acceptance→正式打包”依赖环；没有减少任何执行诊断语义断言、source fingerprint或runtime/import闭包守卫。

根外给实际17冻结信号、源码/runtime逐文件SHA和冻结JSON的SHA后，才启动：

```text
python -B artifacts/v017-actual-independent/run-review-v3.py --freeze ROOT_FREEZE.json --freeze-sha256 ROOT_SUPPLIED_SHA256
```

第一阶段可使用 `root-freeze-v3.template.json` 的 `packages:[]`。此时结果必须记录 `packagesExecuted:false`、`packageReviewPending:true`、`downloadAcceptance:false`、`formalPackageAcceptance:false`，只审查实际17源码/runtime语义，不把它当包或下载验收。

第二阶段由正式打包/消费者流程独立外给source与portable包SHA并完整核验。v3若提供两个包，仍要求各自SHA、CRC及全部绑定成员原字节；只有实际执行这些检查才记packagesExecuted。正式包可以包含第一阶段的最终acceptance，不再形成循环。

实际17尚未执行；没有导入SDK、构建、联网、数据库或测量。根的正式冻结信号仍是必要前提。完整诊断期待、旧模型胶囊兼容、业务版本字符串保留及旧MLflow边界见原README；v3没有改写原输入或预期，也没有覆盖任何旧失败。
"""
put("README-v3.md",readme.encode())
adapt={"schema":1,"kind":"actual17-review-phase-split-preparation","v2ManifestSha256":SHA(raw),"v2FilesUnchanged":32,"actual17Executed":False,"SDKImported":False,"semanticCheckerSha256":SHA((HERE/"execution-checks.mjs").read_bytes()),"semanticAssertionsChanged":False,"changes":["packages=[] is allowed and explicitly leaves package/download acceptance pending","actual17 source fingerprint and full runtime/import guards remain mandatory","second phase keeps exact package SHA/CRC/all-member binding when packages are supplied"]}
put("phase-split-v3.json",(json.dumps(adapt,indent=2)+"\n").encode())
names=[row["file"] for row in v2["files"]]+["preparation-manifest.v2.json","prepare-v3.py","run-review-v3.py","run-tests-v3.mjs","root-freeze-v3.template.json","README-v3.md","phase-split-v3.json"]
assert len(names)==len(set(names))
files=[]
for name in sorted(names):
    data=(HERE/name).read_bytes();files.append({"file":name,"bytes":len(data),"sha256":SHA(data)})
manifest={**{k:v for k,v in v2.items() if k!="files"},"revision":3,"phaseSplit":True,"packageInputsRequiredForSemanticPhase":False,"packageReviewStillRequiredSeparately":True,"v2FilesUnchanged":32,"files":files}
put("preparation-manifest.v3.json",(json.dumps(manifest,indent=2)+"\n").encode())
print(json.dumps({"prepared":True,"actual17Executed":False,"SDKImported":False,"files":len(files),"v2FilesUnchanged":32,"manifestSha256":SHA((HERE/"preparation-manifest.v3.json").read_bytes())}))
