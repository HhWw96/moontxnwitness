"""Static final seal; preserve all v2 and initial v3 files, execute no runtime."""
from pathlib import Path
import ast
import hashlib
import json
HERE=Path(__file__).resolve().parent
SHA=lambda b:hashlib.sha256(b).hexdigest()
raw=(HERE/"preparation-manifest.v3.json").read_bytes()
assert SHA(raw)=="98a58deeae78ab0378814c9650ca2636f9213ce82a19af88f423818b4aff3626"
prior=json.loads(raw)
for row in prior["files"]:
    data=(HERE/row["file"]).read_bytes();assert len(data)==row["bytes"] and SHA(data)==row["sha256"],row["file"]
def put(name,data):
    with (HERE/name).open("xb") as f:f.write(data)
guard=(HERE/"binding_guard_v3.py").read_text(encoding="utf-8")
before=next(line for line in guard.splitlines() if '"Unbound core module dependency"' in line)
after='        assert not re.search(r"(?m)^\\s*import\\b|^\\s*export\\b[^;\\n]*\\bfrom\\s*[\'\\\"]|\\bimport\\s*\\(",text),"Unbound core module dependency"'
assert guard.count(before)==1
guard=guard.replace(before,after)
ast.parse(guard,filename="binding_guard_v3_final.py")
put("binding_guard_v3_final.py",guard.encode())
launcher=(HERE/"run-protocol-v3.py").read_text(encoding="utf-8")
for before,after in [('from binding_guard_v3 import stage_bound_engines','from binding_guard_v3_final import stage_bound_engines'),('HERE/"preparation-manifest.v3.json"','HERE/"preparation-manifest.v3-final.json"')]:
    assert launcher.count(before)==1
    launcher=launcher.replace(before,after)
ast.parse(launcher,filename="run-protocol-v3-final.py")
put("run-protocol-v3-final.py",launcher.encode())
readme="""# perf-v3 最终静态封存入口

使用 `run-protocol-v3-final.py`，授权中的preparationManifestSha256绑定 `preparation-manifest.v3-final.json`。其余参数和17/18绑定格式、固定7输入、协议和严格根引擎头原文本投影完全见README-v3。

原v2的22文件与初版v3的33文件全部原字节保留。最终仅把无外部依赖的core检测限制在真正import/export-from声明或动态import语法；JSON字符串字段 `\"from\"` 不是模块依赖，不能被误判。首版静态准备快照仍保留，没有执行过SDK或测量，没有改变任何输入/输出/预算/版本语义期待。

```text
python -B artifacts/v018-performance-preparation/run-protocol-v3-final.py --binding RUNTIME_SOURCE_BINDING.json --binding-sha256 ROOT_BINDING_SHA --authorization AUTH.json --authorization-sha256 ROOT_AUTH_SHA
```

缺少外给实际17/18源与core的SHA、正式构建/已发布17绑定、exclusive=true及所有其他agent已停止的授权时不能执行。当前只有静态准备，没有core import、计时、RSS/冷启动测量、编译、数据库、网络或提速结论。
"""
put("README-v3-final.md",readme.encode())
names=[x["file"] for x in prior["files"]]+["preparation-manifest.v3.json","seal-v3-final.py","binding_guard_v3_final.py","run-protocol-v3-final.py","README-v3-final.md"]
assert len(names)==len(set(names))
files=[]
for name in sorted(names):
    data=(HERE/name).read_bytes();files.append({"file":name,"bytes":len(data),"sha256":SHA(data)})
result={**{k:v for k,v in prior.items() if k!="files"},"initialV3All33FilesUnchanged":True,"finalStaticDependencyGuard":"Only module declarations and dynamic import syntax, not JSON field values named from.","files":files}
put("preparation-manifest.v3-final.json",(json.dumps(result,ensure_ascii=False,indent=2)+"\n").encode())
print(json.dumps({"prepared":True,"formalPerformanceMeasured":False,"coreImported":False,"v2All22FilesUnchanged":True,"initialV3All33FilesUnchanged":True,"cases":len(result["cases"]),"files":len(files),"manifestSha256":SHA((HERE/"preparation-manifest.v3-final.json").read_bytes())}))
