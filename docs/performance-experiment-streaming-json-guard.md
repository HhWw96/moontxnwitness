# 流式 JSON 守卫：完整调用性能对照

2026 年 10 月 24 日，以公开 v0.2.6（`4c74fd29f45c2e6756a20881fefb03677fa9bf52`）为基线，仅改变内部 JSON 守卫的有效输入扫描方式。使用 Unicode 字符迭代，避免物化完整字符数组；索引摘要保留原扫描器，输入错误回退原守卫，完整判断、预算和报告字段继续核验。

同机、同工具链、同输入与完整输出，10 个固定负载，60 个串行独立进程，每项预热 5 次、正式 30 次、3 批。保留 1,800 个正式样本和 2,160 份完整原始报告。

| 指标 | 公开基线 | 优化候选 | 结果 |
| --- | ---: | ---: | --- |
| 128 事务完整六模型 SDK 中位耗时 | 1421.3299 ms | 1150.4180 ms | 1.23549×，耗时减少约 19.1% |
| 同一负载 P95 | 1776.9486 ms | 1259.4026 ms | 降低 |
| 同一负载进程峰值 RSS 中位数 | 547284 KiB | 560008 KiB | 1.02325 倍，内存下降目标未达到 |
| 六个模型负载几何平均提速 | — | 1.20184× | 描述本组结果，不代表其它总体目标通过 |

9 个控制负载的 27 项分批和 9 项合并 P95 检查全部通过。仅六模型报告的实际 `engine.coreSha256` 可按两份真实构建映射；四个分析控制要求完整原文相同。峰值 RSS 包含进程此前的报告编码与归档分配，不是单次调用专用峰值。统计采用上中位数和最近秩 P95。

[原始证据包](../verification/performance-experiments/streaming-json-guard/MoonTxnWitness-v0.2.6-streaming-guard-performance-evidence.tar.xz)、[独立复核](../verification/performance-experiments/streaming-json-guard/independent-review.json)及[逐负载结果](../verification/performance-experiments/streaming-json-guard/REPORT.json)保留源码差分、固定输入、原工具和 94 个运行文件。用同目录 `verify_evidence.py` 加归档路径，只读核对所有样本和原始报告；它不导入 SDK，也不重新计时。

605 份正确性原件公开 604 份；1 份首次失败日志含本机用户路径，原文私下保留，公开其相对身份、长度和摘要。原 plan 未改，因此公开子集不能直接一键重跑原控制器的全部依赖，详见 [隐私范围](../verification/performance-experiments/streaming-json-guard/PRIVACY-SCOPE.json)。两处历史测试清单偏差保持待核实，不把公开 v0.2.6 输出兼容当作其规范正确性。

本次实验通过预先声明的速度／内存二选一目标及全部控制检查。原实验的 `candidateAdopted=false` 保持，正式主线集成、跨目标回归和发布采用分别记录；已发布的 v0.2.6 默认实现不因这份实验记录而改变。[此前失败的图复用实验](performance-experiment-empty-interval-reuse.md)保持原结论。
