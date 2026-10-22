# 正式已发布17 vs 实际18：perf-v3（只准备，未测量）

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
