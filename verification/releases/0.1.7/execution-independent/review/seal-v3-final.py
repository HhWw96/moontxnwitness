"""Static dependency-lexer refinement only; preserve all initial39 prepared files."""
from pathlib import Path
import ast
import hashlib
import json
HERE=Path(__file__).resolve().parent
SHA=lambda b:hashlib.sha256(b).hexdigest()
raw=(HERE/"preparation-manifest.v3.json").read_bytes()
assert SHA(raw)=="50891bd4c05435a93469977d0fc5f1be3fa4f1042e5ba0759cc0d7fe3dcc7ee0"
prior=json.loads(raw)
for row in prior["files"]:
    data=(HERE/row["file"]).read_bytes();assert len(data)==row["bytes"] and SHA(data)==row["sha256"],row["file"]
def put(name,data):
    with (HERE/name).open("xb") as f:f.write(data)
launcher=(HERE/"run-review-v3.py").read_text(encoding="utf-8")
before=next(line for line in launcher.splitlines() if "specs=re.findall" in line)
after=r'''            specs=[]
            for statement in text.splitlines():
                if re.match(r"^\s*import\b",statement):
                    found=re.fullmatch(r"\s*import\s+(?:(?:[^;\n]+?)\s+from\s+)?['\"]([^'\"]+)['\"]\s*;?\s*(?://.*)?",statement)
                    assert found,"Unreviewed import declaration: "+name
                    specs.append(found.group(1))
                elif re.match(r"^\s*export\s*(?:\{|\*)",statement):
                    found=re.fullmatch(r"\s*export\s+(?:[^;\n]+?)\s+from\s+['\"]([^'\"]+)['\"]\s*;?\s*(?://.*)?",statement)
                    if found:specs.append(found.group(1))
                    else:assert re.fullmatch(r"\s*export\s*\{[^;\n]*\}\s*;?\s*(?://.*)?",statement),"Unreviewed export declaration: "+name'''
assert launcher.count(before)==1
# r-quoted staging text uses escaped quotes only as source delimiters here.
after=after.replace('r\\"','r"').replace('\\",statement','",statement').replace('\\",statement)','",statement)')
launcher=launcher.replace(before,after)
for before,after in [('HERE/"preparation-manifest.v3.json"','HERE/"preparation-manifest.v3-final.json"'),('str(HERE/"run-tests-v3.mjs")','str(HERE/"run-tests-v3-final.mjs")')]:
    assert launcher.count(before)==1
    launcher=launcher.replace(before,after)
ast.parse(launcher,filename="run-review-v3-final.py")
put("run-review-v3-final.py",launcher.encode())
worker=(HERE/"run-tests-v3.mjs").read_text(encoding="utf-8")
assert worker.count("preparation-manifest.v3.json")==2
worker=worker.replace("preparation-manifest.v3.json","preparation-manifest.v3-final.json")
put("run-tests-v3-final.mjs",worker.encode())
readme="""# 实际17 v3最终准备（仍未执行）

入口 `run-review-v3-final.py` 与清单 `preparation-manifest.v3-final.json`。原v2的32文件、初v3的39文件均逐字节保留；原11输入、完整诊断期待、两案MLflow事实与旧模型胶囊没有改变。

最终只将依赖扫描识别限制在真正行首import和export-from声明；JSON字段字符串 `\"from\"` 是数据，不是模块声明。仍然拒绝动态import、未知/多行未审查声明、不在冻结runtime清单中的依赖、外部或逃逸路径，所有source/runtime SHA守卫与语义检查保持。没有通过放松业务预期修正这种准备器假阳性，也未执行任何SDK来得到新期待。

```text
python -B artifacts/v017-actual-independent/run-review-v3-final.py --freeze ROOT_FREEZE.json --freeze-sha256 ROOT_SUPPLIED_SHA256
```

source.root='.'与runtime.root='dist'可从repo cwd使用。packages=[]仍明确留下package/download接受未完成；正式包消费者流程另验。私有原启动/预flight保留原件并记录SHA，公开闭包后续只选择相对路径可复制代码、运行文件、输入和收据，不复制整个私有目录或全源镜像。

仍等根实际17冻结与外给SHA；没有SDK/core import、构建、数据库、网络或性能测量。
"""
put("README-v3-final.md",readme.encode())
names=[row["file"] for row in prior["files"]]+["preparation-manifest.v3.json","seal-v3-final.py","run-review-v3-final.py","run-tests-v3-final.mjs","README-v3-final.md"]
assert len(names)==len(set(names))
files=[]
for name in sorted(names):
    data=(HERE/name).read_bytes();files.append({"file":name,"bytes":len(data),"sha256":SHA(data)})
result={**{k:v for k,v in prior.items() if k!="files"},"initialV3All39FilesUnchanged":True,"finalStaticDependencyScan":"Real import/export-from declarations; all declared dependencies remain hash-bound.","files":files}
put("preparation-manifest.v3-final.json",(json.dumps(result,indent=2)+"\n").encode())
print(json.dumps({"prepared":True,"actual17Executed":False,"SDKImported":False,"initialV3All39FilesUnchanged":True,"files":len(files),"manifestSha256":SHA((HERE/"preparation-manifest.v3-final.json").read_bytes())}))
