"""Pre-execution protocol refinement; retain the original 17 prepared files."""
from pathlib import Path
import ast
import hashlib
import json
HERE=Path(__file__).resolve().parent
SHA=lambda b:hashlib.sha256(b).hexdigest()
raw=(HERE/"preparation-manifest.json").read_bytes()
assert SHA(raw)=="e27de096eb247f3ef1f72b253fb07475768be07ad380f624ccd6e207796c68a0"
old=json.loads(raw)
for row in old["files"]:
    data=(HERE/row["file"]).read_bytes();assert len(data)==row["bytes"] and SHA(data)==row["sha256"]
def put(name,data):
    with (HERE/name).open("xb") as f:f.write(data)
worker=(HERE/"worker.mjs").read_text(encoding="utf-8")
before="for(let i=0;i<5;i++){value=run();checkOutput(value);}"
after="// The recorded first call is warmup 1; four more make exactly five.\n  for(let i=1;i<5;i++){value=run();checkOutput(value);}"
assert worker.count(before)==1
worker=worker.replace(before,after)
put("worker-v2.mjs",worker.encode())
launcher=(HERE/"run-protocol.py").read_text(encoding="utf-8")
for before,after in [('HERE/"preparation-manifest.json"','HERE/"preparation-manifest.v2.json"'),('str(HERE/"worker.mjs")','str(HERE/"worker-v2.mjs")')]:
    assert launcher.count(before)==1
    launcher=launcher.replace(before,after)
ast.parse(launcher,filename="run-protocol-v2.py")
put("run-protocol-v2.py",launcher.encode())
readme="""# 正式对照准备 v2（仍未测量）

原17文件和原准备清单完整保留。v2明确首调用就是预热第1次，再执行4次预热，随后30次计时，因此每个warm进程恰好5次预热；不会暗含第6次。冷进程只有1次调用，equivalence进程另行执行，不参与热样本。

正式启动入口改为：

```text
python -B artifacts/v018-performance-preparation/run-protocol-v2.py --authorization AUTH.json --authorization-sha256 ROOT_SUPPLIED_SHA256
```

授权JSON必须绑定 `preparation-manifest.v2.json` 的摘要，其余独占授权、固定引擎、固定7输入、完整输出对照、3批独立进程、90样本汇总、median/P95/RSS/字节/冷启动与控制10%或2ms阈值均不变。所有大临时输出仅写D盘scratch。

冷启动指新Node进程的导入和第一次调用；OS文件缓存没有清空，不是冷存储测量。外部冷进程墙钟还包含Node启动、守卫I/O和结果核验；子进程同时记录importMs与firstCallMs供区分。

静态准备未调用worker、未import core、未运行计时或RSS测量，未宣称提速。原准备快照不是已执行的性能结果。
"""
put("README-v2.md",readme.encode())
names=[row["file"] for row in old["files"]]+["preparation-manifest.json","prepare-v2.py","worker-v2.mjs","run-protocol-v2.py","README-v2.md"]
files=[]
for name in sorted(names):
    data=(HERE/name).read_bytes();files.append({"file":name,"bytes":len(data),"sha256":SHA(data)})
result={**{k:v for k,v in old.items() if k!="files"},"revision":2,"original17PreparedFilesUnchanged":True,"warmFirstCallCountsAsWarmupOne":True,"files":files}
put("preparation-manifest.v2.json",(json.dumps(result,ensure_ascii=False,indent=2)+"\n").encode())
print(json.dumps({"prepared":True,"formalPerformanceMeasured":False,"coreImported":False,"cases":len(result["cases"]),"files":len(files),"manifestSha256":SHA((HERE/"preparation-manifest.v2.json").read_bytes())}))
