# 空实时边图复用实验：未采用

本次比较公开 v0.2.6（源码 `4c74fd29f45c2e6756a20881fefb03677fa9bf52`）和只复用空实时边图结构的私有候选。候选未达到目标，不合入默认实现，已发布版本保持原实现。

| 固定 128 事务的完整六模型 SDK 调用 | 基线 | 候选 |
|---|---:|---:|
| 中位数耗时 | 1259.154 ms | 1235.626 ms |
| P95 | 1430.832 ms | 1338.775 ms |
| 三进程峰值 RSS 中位数 | 553036 KiB | 579372 KiB |

提速为 **1.01904 倍**，RSS 比为 **1.04762**，均未满足预先登记的“提速至少 1.15 倍或 RSS 比不超过 0.85”。六模型负载组的几何平均提速为 1.00666 倍，RSS 比为 1.01018。单个大图结果不能代替全组或此前 v0.2.0 基线的目标。

同机、同 Node.js 24.13.0、同输入、同选项、同输出范围，共执行三批、60 个串行独立进程。每进程一次冷调用、5 次预热和30次正式样本，合计1800个正式样本及2160份完整原输出。六模型输出仅允许已登记的 `engine.coreSha256` 构建摘要差异；四项 `analyzeV3` 对照要求原文一致。全部输出符合此规则。

九个非目标负载中，七个出现逐批 P95 回退：G0、列表写偏斜、实时反证、空历史、寄存器链、列表链和关系链。九项合并批次检查虽均通过，仍不能覆盖逐批失败。所有60个进程正常退出，这是性能未达标，并非运行故障。RSS 包含进程及此前报告编码、封存的分配，不解释为纯算法常驻内存。

原始报告、原始摘要、日志、计划、输入、测量代码和候选补丁均保留。公开证据包收录2362份未改原文件，并利用跨文件压缩保留2160份原输出；独立复算与作者结果一致。分类 SDK 检查没有调用采集接口，本次不宣称完成采集行为回归。

- [结果摘要](../verification/performance-experiments/empty-interval-reuse/REPORT.json)
- [独立复算记录](../verification/performance-experiments/empty-interval-reuse/independent-review.json)
- [完整原始证据](../verification/performance-experiments/empty-interval-reuse/MoonTxnWitness-v0.2.6-empty-interval-performance-evidence.tar.xz)
- [只读验真器](../verification/performance-experiments/empty-interval-reuse/verify_evidence.py)

证据包 SHA256：`0fb8c0992338dfb05eb695bc4a14278c5e99f414c170674db17623a08af19852`。

从仓库根目录运行以下命令可重算样本并核对全部原输出，不执行 SDK 或重新测量：

```text
python verification/performance-experiments/empty-interval-reuse/verify_evidence.py verification/performance-experiments/empty-interval-reuse/MoonTxnWitness-v0.2.6-empty-interval-performance-evidence.tar.xz
```

验真成功仅表示证据完整；结果仍为 `performanceGatePassed: false`、`candidateAdopted: false`。下一步依据 CPU 诊断优化报告 JSON 的扫描分配，不重复相同实现争取通过，也不修改既有失败记录。
