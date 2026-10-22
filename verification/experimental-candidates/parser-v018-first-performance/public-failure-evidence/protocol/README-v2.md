# 正式对照准备 v2（仍未测量）

原17文件和原准备清单完整保留。v2明确首调用就是预热第1次，再执行4次预热，随后30次计时，因此每个warm进程恰好5次预热；不会暗含第6次。冷进程只有1次调用，equivalence进程另行执行，不参与热样本。

正式启动入口改为：

```text
python -B artifacts/v018-performance-preparation/run-protocol-v2.py --authorization AUTH.json --authorization-sha256 ROOT_SUPPLIED_SHA256
```

授权JSON必须绑定 `preparation-manifest.v2.json` 的摘要，其余独占授权、固定引擎、固定7输入、完整输出对照、3批独立进程、90样本汇总、median/P95/RSS/字节/冷启动与控制10%或2ms阈值均不变。所有大临时输出仅写D盘scratch。

冷启动指新Node进程的导入和第一次调用；OS文件缓存没有清空，不是冷存储测量。外部冷进程墙钟还包含Node启动、守卫I/O和结果核验；子进程同时记录importMs与firstCallMs供区分。

静态准备未调用worker、未import core、未运行计时或RSS测量，未宣称提速。原准备快照不是已执行的性能结果。
