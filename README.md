# MoonTxnWitness v0.0.7

MoonTxnWitness 是用 **MoonBit** 实现的离线事务历史检查器。它分析带唯一版本的多键点读写日志，解释异常依赖，把冗长日志缩成可复现反例，并比较普通与严格可串行化模型。所有分析在本地完成。

English: An offline MoonBit transaction-history checker with shortest cycle witnesses, bounded serial completion, transaction reduction and self-contained replay.

公开入口：[GitHub 源码](https://github.com/HhWw96/moontxnwitness)、[v0.0.6 下载](https://github.com/HhWw96/moontxnwitness/releases/tag/v0.0.6)、[Mooncakes 库](https://mooncakes.io/docs/HhWw96/moontxnwitness)。公开发布的验证记录在 `verification/publication.json`。

2026-10-16 已完成两个 ZIP 的匿名下载与 SHA-256 核对，以及 Mooncakes 上传/下载字节一致性检查。全新独立项目从 Mooncakes 安装后，JS / Wasm GC 各 6 项接口测试通过；公开 Windows/Linux CI 均通过。

## 先运行完整演示

运行包需要 **Node.js 20 或更新版本**，本次实测为 24.13.0。解压 portable ZIP，在解压目录运行：

```powershell
node dist/moontxnwitness.mjs --version
node dist/demo.mjs
```

Windows 也可双击 `run-demo.cmd`。演示自动创建新的 `moontxnwitness-demo-*` 目录，导出中文报告、7→2 事务缩减结果、模型对比和通过复核的复现包。先打开其中的 `report.md`。每次运行创建新目录，已有文件不会被覆盖。

演示使用合成异常；实际 SQLite 并发采集另见下文。

## 五轮迭代完成的能力

| 版本 | 核心改进 | 能解决的问题 |
| --- | --- | --- |
| 0.0.2 | 有预算的精确串行重放搜索 | 小日志缺少写入版本顺序时，寻找可行执行或证明穷举无解 |
| 0.0.3 | 按事务缩减反例 | 删除无关事务，保留确定异常；明确是否完成单事务删除检查 |
| 0.0.4 | 自包含复现包、语义回放、模型对比 | 复现环、直接读写异常和无环的穷举失败；区分实时先后导致的异常 |
| 0.0.5 | 真实双线程 SQLite WAL 采集 | 记录实际提交、忙冲突回滚和新事务重试；从事务内审计表采集版本顺序 |
| 0.0.6 | 强连通分量定位、版本来源与逐键诊断 | 先排除无环区域；区分采集事实和搜索补全，提示下一步需要采集什么 |

初版 0.0.1 的 MoonBit 库、CLI、JavaScript SDK、WR/WW/RW/RT 依赖、最短异常环及独立环复核均保留。区别与检索范围见 [独特性说明](docs/UNIQUENESS.md)。

## 检查、缩减和复现

以下命令创建新文件；若目标已存在会拒绝覆盖。

```powershell
node dist/moontxnwitness.mjs check examples/write-skew.json
node dist/moontxnwitness.mjs check examples/unknown-order.json --format json
node dist/moontxnwitness.mjs check examples/fractured-observation.json --format markdown
node dist/moontxnwitness.mjs shrink examples/noisy-write-skew.json --output reduction.json --history mini.json
node dist/moontxnwitness.mjs check mini.json --format markdown --output report.md --witness witness.json --capsule case.capsule.json
node dist/moontxnwitness.mjs verify mini.json witness.json
node dist/moontxnwitness.mjs replay case.capsule.json
node dist/moontxnwitness.mjs compare-models examples/strict-realtime.json
```

`check` 支持 `text`、`json`、`markdown`、`dot`。异常示例返回 **1** 是预期结果；成功复核返回 **0**。`--witness` 只导出依赖环。没有环的直接异常、穷举无解也可使用 `--capsule` 复现。

`verify` 重新推导边并检查环闭合，不重跑最短环搜索。`replay` 检查包内文本的 SHA-256，并重算核心判断；支持本项目 schema 1 的 0.0.1–0.0.6 证据版本。哈希不能认证采集者身份，展示补充字段也不属于核心语义复核范围。详见 [证据与缩减](docs/evidence.md)。

## 输入与模型

每次写入必须有同键唯一的版本标记。业务值相同的两次写入也必须使用不同版本，例如 `x:T1:1`、`x:T2:1`。日志记录已完成操作的真实观察，不能把业务值当成写入身份。

```json
{
  "schemaVersion": 1,
  "model": "serializable",
  "initial": {"x": "x0", "y": "y0"},
  "transactions": [
    {"id": "T1", "status": "committed", "ops": [
      {"type": "read", "key": "x", "version": "x0"},
      {"type": "write", "key": "y", "version": "y1"}
    ]},
    {"id": "T2", "status": "committed", "ops": [
      {"type": "read", "key": "y", "version": "y0"},
      {"type": "write", "key": "x", "version": "x1"}
    ]}
  ]
}
```

该日志要求 T1 在 T2 之前、T2 又在 T1 之前，形成两事务写偏斜反例。

- `serializable`：寻找满足读取观察及输入版本约束的整个事务串行执行。
- `strict-serializable`：再尊重共同观察时钟中明确先完成、后开始的事务次序。
- 每个键须声明 `initial`；每个事务须声明 `committed`、`aborted` 或 `unknown`。
- `versionOrders` 是可选的、来自采集的同键最终写入顺序。工具不会从版本名字、数组位置或结束时间猜测写入顺序。
- 多写者键没有顺序时，仅在没有其他信息缺失的小日志中执行精确搜索。`searched` 顺序证明存在一个可能执行，**不是观测到的数据库顺序**。

输入约定、共同时间要求和完整示例见 [输入格式](docs/input-format.md) 与 [JSON Schema](docs/history.schema.json)。

## 看懂结果与边界

| 状态 | check 退出码 | 含义 |
| --- | --- | --- |
| `consistent` | 0 | 当前模型及约束内存在可行串行执行，输入没有未解决的缺失 |
| `violation` | 1 | 有确定读写异常、依赖环或完整搜索无解 |
| `invalid` | 2 | 输入或约束不合法 |
| `inconclusive` | 3 | 缺少必要信息，或预算不足以作出结论 |

报告保留操作下标、依赖来源、逐键读写覆盖、版本顺序来源及下一步采集提示。已有确定异常可以与其他缺失共存，此时 `complete: false`；`complete` 不认证日志真实或采集窗口完整。

范围为唯一版本点读写寄存器；支持外部中间版本、回滚版本、自身读写顺序等直接异常。尚不支持范围查询、谓词冲突、append/list 模型、自动 SQL 插桩、Jepsen 日志直接导入或完整隔离级别分类。分析一个历史不能认证整个数据库。

预算：512 事务、10,000 操作、50,000 依赖；历史最多 2 MiB UTF-8，核心解析最多 1,048,576 UTF-16 单元，JSON 深度 64。精确搜索限 8 个已提交事务、512 操作、128 初始键、100,000 候选前缀和 1,000,000 操作检查。缩减限 64 事务、2,048 操作和 128 次候选检查。`oneMinimal` 不表示全局最少事务，也不最小化操作。

## 真实 SQLite 采集

需要 Python 3.11 或更新版本，使用标准库，无需额外安装：

```powershell
python examples/capture_sqlite.py sqlite-history.json
node dist/moontxnwitness.mjs check sqlite-history.json
python examples/capture_sqlite_concurrent.py sqlite-concurrent.json --rounds 3
node dist/moontxnwitness.mjs compare-models sqlite-concurrent.json
```

顺序基线实际执行 3 个事务。并发采集让两个独立连接先读同一快照，再竞争写入，记录实际忙冲突和回滚，随后以新事务重试。版本顺序来自与数据写入一同提交的审计表，而非线程返回顺序。详见 [SQLite 采集说明](docs/sqlite-capture.md)。本轮实际负载符合两种模型；合成异常不声称是 SQLite 漏洞。

## 程序接入

```javascript
import { analyze, shrink, compareModels, replayReport, verify, version } from './dist/sdk.mjs';
const report = analyze(historyObject); // 也接受原始 JSON 文本
console.log(version(), report.status, report.serialOrder);
const comparison = compareModels(historyObject);
if (report.witness) console.log(verify(historyObject, report));
console.log(replayReport(historyObject, report));
```

SDK 的分析接口可用于 JavaScript/浏览器，不依赖 Node 文件或密码模块；文件读写与 SHA-256 封装由 Node CLI 执行。

MoonBit 公共接口包括 `parse_history`、`analyze`、`reduce_history`、`compare_models`、`verify_cycle`、`replay_report_json`、`history_json` 和报告渲染，类型见 `src/pkg.generated.mbti`。正式模块名为 `HhWw96/moontxnwitness`：

```powershell
moon add HhWw96/moontxnwitness@0.0.6
```

在调用包的 `moon.pkg` 中导入 `"HhWw96/moontxnwitness" @txn`。例如 `@txn.analyze_json(historyText)` 返回结构化结果；原始模型与预算约束同样适用。

## 构建与验证

验证工具链：Moon 0.1.20260920、moonc v0.10.14+7d59c7ec9、Node 24.13.0、Python 3.12.5。源码构建需安装 MoonBit，并设置好 `MOON_HOME` 或运行路径。

```powershell
node scripts/build.mjs
npm test
npm run demo
npm run package
```

没有外部 npm 或 Mooncakes 依赖，无需 `npm install`。核心分析、搜索、缩减、语义复核及报告使用 MoonBit，Node 负责本地文件、哈希和命令行。

验证包含每个 JS / Wasm GC / Wasm 目标 **71 项核心测试**、**10,320 份独立串行重放核对**、6,373 份环证据及最短性核对和 **69 项命令行检查**，包括实际 SQLite 并发执行。Windows 本地 Native 仅完成类型检查；公开 Linux CI 另执行 Native 核心测试并通过。运行包仍交付 JavaScript 核心，不包含原生可执行文件。

记录见 [验证汇总](verification/summary.json)、[独立 oracle](verification/oracle.json)、[命令行](verification/cli.json)、[五轮迭代](verification/iterations.json)。新版示例报告见 [缩减后的中文报告](verification/v0.0.6-write-skew.md)，同目录有配套 mini、witness、capsule 和模型对比。未加版本前缀的 write-skew 报告/证据保留为初版兼容性样本。干净目录重建及运行包验证见 [开发与交付](docs/development.md)。本地端到端性能数据见 `verification/benchmark.json`，不作普遍加速保证。

## 许可证与交付状态

采用 [Apache-2.0](LICENSE)，参考与 AI 辅助开发说明见 [THIRD_PARTY.md](THIRD_PARTY.md)。v0.0.6 提供源码与运行 ZIP，保留初版。发布不等于比赛提交或组织方接受；不能保证获奖。
