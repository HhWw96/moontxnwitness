# v0.5.1 原生模型报告性能

在相同工具链和完整输出范围下，共同模型调用组几何平均提速 **2.688 倍**，峰值 RSS 下降 **26.7%**；关系谓词模型组提速 **1.531 倍**，RSS 比为 **1.002**。完整报告逐字节相同，两个控制负载通过 P95 回退检查。

## 实现与兼容

`classifyModelsV4` 与 `classifyRelationModelsV4` 通过 JavaScript 专用 MoonBit 导出取得新建的普通对象，省去完整报告的编码、核心重新解析和再次编码。原始来源核验、逐模型规则、全部证据和运行计数保持不变。

原生传输按原 `indent=2` 文本计算 32 MiB UTF-8 额度，并保留 64 层容器限制。字符串转义、Unicode、数字词法、原型敏感键和对象隔离均有边界检查。原生入口不可用时使用原文本入口；复现包仍绑定原有完整文本，不可信报告仍按独立调用选项解析和重算。

83 项 SDK 对照及 22 项原生边界测试覆盖三种数据模型、十四个模型选项、零预算、文本回退、篡改和包装后的嵌套边界。新传输不改变模型适用范围。能力查询用法见[接口发现](capabilities.md)。

## 正式协议

基线为公开 v0.5.0 源码在本机固定工具链下的运行时，候选为 v0.5.1。两者均使用 moonc 0.10.16+b1a0e846e、同一 Node.js 和同机环境；逐文件源码及运行时绑定见[源码核对](evidence/native-model-performance-v051-source.json)。Linux 发行包摘要用于下载验证，不替代本机计时基线。

每个负载、每个实现预热 5 次、测量 30 次，分 3 批独立进程，批次交替前后顺序。本次 8 个目标负载和 2 个控制负载共保留 1,800 份计时样本；另在独立进程测量导入、冷调用和峰值 RSS。计时包括完整 SDK 调用及全部输出的 JSON 序列化，未计时复现包。默认六模型报告保持与基线一致。

计时前核对完整输出字节，计时后核对输入、选项及运行时摘要。本机测量期间暂停编译、数据库测试、打包和下载解压。控制负载允许回退为 10% 或 2 ms 中较大值。冷启动表示新进程，不代表清空操作系统磁盘缓存。

## 结果

| 调用组 | 目标数 | 中位提速几何平均 | 峰值 RSS 比 | P95 控制 |
| --- | ---: | ---: | ---: | --- |
| `classifyModelsV4` | 5 | 2.688× | 0.733 | 通过 |
| `classifyRelationModelsV4` | 3 | 1.531× | 1.002 | 通过 |

共同模型组达到提速 1.3 倍及 RSS 下降 20% 的目标；关系组达到提速目标，内存基本持平。八个目标负载合并的几何平均提速为 2.176 倍，RSS 下降 17.6%；不把共同模型组的内存收益套用于关系组。性能结果限定于本页负载和环境，完整采集成本另行测量。

耗时为 ms，RSS 为 MiB；B 为 v0.5.0，C 为 v0.5.1。

| 负载 | B 中位 | C 中位 | B P95 | C P95 | B RSS | C RSS | 输出字节 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| classifyModelsV4 / register-full | 89.613 | 29.541 | 123.258 | 45.955 | 103.16 | 88.06 | 574919 |
| classifyModelsV4 / list-prefix | 88.989 | 30.862 | 137.787 | 66.752 | 101.79 | 88.18 | 599744 |
| classifyModelsV4 / relation-atomic | 481.654 | 149.858 | 765.500 | 246.672 | 249.91 | 117.88 | 2451044 |
| classifyModelsV4 / register-cycle | 106.146 | 33.196 | 157.990 | 54.480 | 103.40 | 88.30 | 730165 |
| classifyModelsV4 / register-noise | 1572.846 | 1008.231 | 1880.489 | 1405.812 | 303.63 | 215.26 | 3659082 |
| classifyModelsV4 / budget-control（控制） | 98.472 | 35.178 | 133.305 | 50.969 | 102.98 | 88.11 | 603241 |
| classifyRelationModelsV4 / predicate-point | 14.676 | 8.463 | 20.674 | 14.068 | 87.92 | 88.04 | 89815 |
| classifyRelationModelsV4 / predicate-cycle | 21.830 | 12.640 | 29.465 | 20.488 | 88.07 | 88.40 | 104481 |
| classifyRelationModelsV4 / predicate-noise | 216.234 | 180.365 | 264.993 | 282.079 | 101.97 | 102.04 | 364102 |
| classifyRelationModelsV4 / budget-control（控制） | 11.782 | 8.479 | 18.497 | 13.716 | 88.23 | 88.21 | 79340 |

## 复测与记录

使用维护中的 `scripts/model-performance-v050.mjs`，显式设置基线与候选 `dist/sdk.mjs` 路径。共同模型组选择 `register-full`、`list-prefix`、`relation-atomic`、`register-cycle`、`register-noise`，以 `register-budget` 为控制；关系组选择 `predicate-point`、`predicate-cycle`、`predicate-noise`，以 `predicate-budget` 为控制。配置需声明 `exclusiveExecution: true`，结果目录必须尚不存在。

```text
node scripts/model-performance-v050.mjs --config bench-config.json --output NEW_RUN_DIRECTORY
```

完整汇总、P95、冷启动、环境和运行时逐文件摘要见[测量收据](evidence/native-model-performance-v051.json)。200 份原始 worker 结果合并为[原始样本](evidence/native-model-performance-v051-samples.jsonl)，每条保留原文件摘要。合并不改变样本内容；原始全目录清单摘要保存在收据中。公开环境仅省略主机名称，原始记录原样保留。

`--smoke` 只检查工具流程，不能替代本页正式协议。旧 v0.5.0 测量继续保留在[原性能记录](model-performance-v050.md)，其基线与本次不同。
