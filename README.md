# MoonTxnWitness v0.1.1 开发中

**用 MoonBit 把事务并发日志变成可解释、可缩减、可回放的反例。** 面向数据库与后端开发者，连接真实采集、异常解释、反例缩减、证据复现和修复回归。分析在本地完成。

English: An offline MoonBit transaction-history checker with shortest cycle witnesses, bounded serial completion, transaction reduction and reproducible database examples.

[源码](https://github.com/HhWw96/moontxnwitness) · [v0.1.0 稳定版下载](https://github.com/HhWw96/moontxnwitness/releases/tag/v0.1.0) · [Mooncakes](https://mooncakes.io/docs/HhWw96/moontxnwitness) · [一页项目说明](docs/project-brief.md)

当前开发版新增 [驱动自动采集与 MoonBit 归一化](docs/automatic-capture.md)。已有业务接入等发布门槛尚待完成；公开稳定包仍为 v0.1.0。后续工作见 [v0.2.0 实施计划](docs/roadmap-v0.2.0.md)。

普通无版本列业务表的 [固定键 CRUD 与空结果采集实验](experiments/provenance/PRESENCE_PROFILE.md)已接通数据库、MoonBit 校验、分析、缩减和重放。实验入口为 `normalizePresenceCapture` / `ingest-presence`；支持范围及安装成本单列，尚未作为 v0.1.2 稳定接口发布。

## 先运行完整演示

下载 portable ZIP，解压后运行。需要 **Node.js ≥20**，本机验证使用 24.13.0：

```powershell
node dist/moontxnwitness.mjs --version
node dist/demo.mjs
```

Windows 也可双击 `run-demo.cmd`。演示使用推荐的 `balanced` 入口，在新的 `moontxnwitness-demo-*` 目录保存中文报告、7→2 事务缩减、模型对照和 schema-2 复现包。先打开 `report.md`。演示使用合成案例；真实数据库流程见下文。

## 检查、缩减、复现

```powershell
node dist/moontxnwitness.mjs check examples/write-skew.json --profile balanced
node dist/moontxnwitness.mjs check examples/fractured-observation.json --profile balanced --format json
node dist/moontxnwitness.mjs shrink examples/noisy-write-skew.json --profile balanced --output reduction.json --history mini.json
node dist/moontxnwitness.mjs check mini.json --profile balanced --format markdown --output report.md --capsule case.capsule.json
node dist/moontxnwitness.mjs replay case.capsule.json
node dist/moontxnwitness.mjs compare-models examples/strict-realtime.json
```

导出拒绝覆盖已有文件。`check` 支持 text/json/markdown/dot；异常返回 **1** 是预期结果。

| 状态 | 退出码 | 含义 |
| --- | --- | --- |
| consistent | 0 | 当前模型与约束内有可行串行执行，无未解决缺失 |
| violation | 1 | 有直接读写异常、依赖环或完整搜索无解 |
| invalid | 2 | 输入或约束不合法 |
| inconclusive | 3 | 缺少观察或计算预算不足 |

`complete` 不认证采集真实性或采集窗口完整。`oneMinimal` 只表示当前分析规则与预算下，删除任何一个剩余事务都不能保留确定异常；它不表示全局最少事务或最少操作。

## 真实 PostgreSQL 18 闭环

按照 [PostgreSQL 采集说明](docs/postgres-capture.md) 安装可选 Python 驱动、配置测试数据库，然后运行：

```powershell
node dist/postgres-demo.mjs
```

同一入口连续执行 **20 轮 Repeatable Read 写偏斜**和 **20 轮 Serializable 回滚/全新事务重试对照**，分析两份真实历史，把异常缩成两事务，并回放三个 v2 复现包。保存 SQL 结果、提交确认、40001 回滚、JSONL 日志和摘要。两连接先点读，再经同步屏障写入；不从自增序号或线程返回时间推断提交顺序。

缺少 Python、驱动或连接配置时明确返回 `not-executed`、`passed:false` 和退出码 3；实际运行失败保留失败记录。每次只创建和清理自己的随机测试 schema，输出放在新目录。源码另有临时实例辅助入口和独立 Linux PostgreSQL CI。

[SQLite 顺序与真实 WAL 并发案例](docs/sqlite-capture.md)使用 Python 标准库。这些实验检查所捕获的执行，不认证整个数据库，也不将隔离级别允许的现象称作漏洞。

## 输入与判断依据

每次同键写入必须有唯一版本身份；业务值相同的两次写入也使用不同标记。

```json
{
  "schemaVersion": 1,
  "model": "serializable",
  "initial": {"x": "x0", "y": "y0"},
  "transactions": [
    {"id": "A", "status": "committed", "ops": [
      {"type": "read", "key": "x", "version": "x0"},
      {"type": "write", "key": "y", "version": "y1"}
    ]},
    {"id": "B", "status": "committed", "ops": [
      {"type": "read", "key": "y", "version": "y0"},
      {"type": "write", "key": "x", "version": "x1"}
    ]}
  ]
}
```

这份日志要求 A 在 B 前、B 又在 A 前，形成两事务环。报告保留依赖的键、操作下标、版本和来源，并寻找图中全局最短的有向环。

- `serializable` 检查整个事务的串行执行；`strict-serializable` 再尊重共同单调观察时钟中明确先完成、后开始的约束。
- 事务状态为 committed/aborted/unknown；缺少结果、来源或共同时间时明确指出。
- `versionOrders` 是可选的采集事实。缺少多写者顺序时，只在其余观察充分且规模允许时搜索补全。
- `searched` 只证明某个可能执行成立，不能变成已观察到的数据库顺序。缩减只裁剪原始声明。

详见 [输入格式](docs/input-format.md)、[JSON Schema](docs/history.schema.json)、[算法设计](docs/design.md) 和 [独特性范围](docs/UNIQUENESS.md)。范围/谓词查询、自动 SQL 插桩、append/list 模型及完整隔离级别分类尚未实现。

## API 与预算约定

保留 `analyze`、`reduce_history`、JS `analyze`/`shrink` 和 CLI 默认行为。推荐显式使用高级入口：

```javascript
import {analyzeWithOptions, shrinkWithOptions, replayReport} from './dist/sdk.mjs';
const report = analyzeWithOptions(history, {
  maxAttempts: 100000, maxOperationChecks: 1000000, maxCachedStates: 50000
});
console.log(report.status, report.search, report.metrics);
const reduced = shrinkWithOptions(history, {maxChecks: 256});
console.log(reduced.oneMinimal, replayReport(reduced.reducedHistory, reduced.report));
```

MoonBit 使用 `analysis_options` / `analyze_with_options` / `analysis_result_json` 和 `reduction_options` / `reduce_with_options` / `reduction_result_json`。类型见 `src/pkg.generated.mbti`。

```powershell
moon add HhWw96/moontxnwitness@0.1.0
```

| 范围 | 默认兼容入口 | balanced 入口 |
| --- | --- | --- |
| 图分析 | 512 事务 / 10,000 操作 / 50,000 依赖 | 相同 |
| 完整串行补全 | 8 个已提交事务 | 12 个已提交事务 |
| 补全操作 / 初始键 | 512 / 128 | 相同 |
| 候选前缀 / 操作检查 | 100,000 / 1,000,000 | 相同，可调低 |
| 失败状态缓存 | 无 | 最多 50,000 项，可关闭 |
| 缩减 | 64 事务 / 2,048 操作 / 128 次检查 | 512 事务 / 10,000 操作 / 256 次检查 |

核心 JSON 限 1,048,576 UTF-16 单元，CLI 历史限 2 MiB UTF-8，深度 64。缓存满后停止新增缓存；预算耗尽不会被当作穷举无解。

v2 记录算法、模型、有效预算和版本来源，把运行计数与判断证据分开；v1 保留原搜索顺序、预算和计数比较规则。回放重算语义，SHA-256 仅保证完整性，不认证采集者。`verify` 使用 schema-1 紧凑环证书；完整 v2 报告使用 `replayReport` 或 CLI `replay`。详见 [高级分析与证据](docs/balanced-profile.md)。

## 构建与可重复验收

源码需要 MoonBit、Node 和 Python，无需 npm install。工具链见 [开发说明](docs/development.md)。

```powershell
npm run build
npm test
npm run benchmark
npm run postgres:verify
npm run package
```

`benchmark` 自动重建，缺少基线时下载并核对公开 v0.0.6 核心的固定摘要。完整报告与完整报告比较：每场景预热 5 次、测量 30 次、分 3 批交替复测；独立进程记录峰值 RSS、冷启动、P95 和输出大小。固定输入、原始样本和失败记录均保留。`--quick` 只作烟雾检查。详见 [路线与协议](docs/ROADMAP.md) 和 [性能报告](docs/performance.md)。

v0.0.10 的完整负载组相对 v0.0.6：图分析 2.67 倍、搜索 5.02 倍、缩减 2.18 倍，图分析峰值内存下降约 30.3%。这是工程测量，不是官方评分权重；当前冻结版本的结果见性能报告。

验证保留每后端 94 项核心测试、10,320 份独立串行重放、6,373 份环证据、2,542 份解析差分和独立缩减检查。Windows/Linux CI 检查便携交付；Linux 另执行 Native 和独立 PostgreSQL 流程。每版实际 CI、公开下载、摘要、Mooncakes 字节和全新注册表安装结果见 `verification/releases/VERSION/publication.json`。

## 开源与参赛状态

开发分支新增独立的 [v3 生命周期及证据入口](docs/v3-contract.md)和 [分段磁盘日志](docs/capture-journal-v3.md)。构建后可运行：

```text
node dist/moontxnwitness.mjs check-v3 examples/v3-savepoint.json
node dist/moontxnwitness.mjs check-v3 examples/v3-write-skew.json --capsule new-v3-case.json
node dist/moontxnwitness.mjs replay-v3 new-v3-case.json
node dist/moontxnwitness.mjs reduce-v3 examples/v3-write-skew.json
```

写偏斜案例退出码为 1，表示发现反证。SDK 对应 `normalizeCaptureV3`、`analyzeV3`、`reduceV3`、`verifyV3`。开发分支另有[追加列表模型](docs/list-v3.md)和[原 dislock 生命周期采集](docs/dislock-v3.md)；六种冻结 SQL 的来源证明须显式选择 [sqlProof 策略](docs/dislock-sql-v3.md)，其他 SQL、零行条件来源不足与未知提交保持缺口。来源闭包窗口、安全保留、完整采集成本、ORM、关系模型及六模型分类继续按[剩余执行计划](docs/remaining-execution-plan.md)开发。当前完成项与未执行项见[开发状态](docs/development-status.md)，v3 实验不表示已完成 v0.1.1/v0.1.2 联合验收。

Apache-2.0；依赖、概念来源、AI 使用与复核方式见 [THIRD_PARTY.md](THIRD_PARTY.md)。分析算法全部使用 MoonBit；JS 处理文件与传输，Python 可选采集数据库，JS 后端有一个字符串片段拼接原语。

v0.0.7–v0.0.11 的实质提交、变更、失败尝试和发布记录保留。参赛者本人仍须完成 [安装与解释验收](docs/human-acceptance.md)，并独立确认报名、入群及组织方回执。公开发布或自动检查通过不表示官方接受或获奖。
