# MoonTxnWitness

**把事务读写日志变成可解释、可缩减、可回放的反例。** MoonBit 实现离线分析核心，提供 Mooncakes 库、JavaScript SDK、命令行和可选 PostgreSQL 采集器。

English: An offline MoonBit transaction-history checker with shortest-cycle witnesses, bounded serial completion, counterexample reduction and replay.

[源码](https://github.com/HhWw96/moontxnwitness) · [下载](https://github.com/HhWw96/moontxnwitness/releases) · [Mooncakes](https://mooncakes.io/docs/HhWw96/moontxnwitness) · [更新记录](CHANGELOG.md)

## v0.1.7 支持范围

本版新增执行故障诊断包：`makeExecutionCapsuleV3`、`replayExecutionCapsuleV3`，把原始记录与完整诊断封存并重新计算。运行 `node examples/execution-roundtrip.mjs` 可离线比较两份既有 MLflow 记录，见[诊断包说明](docs/execution-capsule-v3.md)；有效重放不表示没有故障、业务修复或数据库真实性证明。

继续提供已验证点寄存器证据环的类型与来源解读：`explainRegisterCycleV3`、`verifyRegisterCycleExplanationV3`。运行 `node examples/register-cycle-roundtrip.mjs`，见[证据环解读说明](docs/cycle-explanation-v3.md)。

关系集合的六个专用 SDK 入口与来源闭包缩减示例继续提供；保留列表、ORM 模板、局部来源诊断、普通表 CRUD 与已有分析接口。v0.1.5 已发布至 GitHub 与 Mooncakes，并通过[公开下载验证](https://github.com/HhWw96/moontxnwitness/actions/runs/39792872938)；本版实际构建、安装和公开发布状态以 `verification/releases/0.1.7/` 收据及[发行记录](https://github.com/HhWw96/moontxnwitness/releases)为准。

| 能力 | 本版支持 |
| --- | --- |
| 离线分析 | 带唯一写入版本的点读写寄存器；serializable / strict-serializable |
| 追加列表 | `append-list-v1` 的来源检查、有界串行分析、缩减及胶囊重放；显式列表 SDK 入口 |
| 关系集合 | `relation-set-v1` 的完整谓词查询、行写入、来源闭包缩减及胶囊重放；显式关系 SDK 入口 |
| 异常解释 | 直接读写异常、完整依赖来源、图中最短有向环和有界串行补全 |
| 反例与证据 | 事务缩减、中文报告、图导出、v1/v2 证据及复现包回放 |
| PostgreSQL 采集 | psycopg 同步/异步连接；已有版本列、单列主键及明确映射的点读写 SQL |
| 普通表 CRUD | 独立 `moontxnwitness_capture.presence` 入口；受控两列表、固定文本键集合、同步点查询及插入/更新/删除、负读与墓碑来源 |
| ORM 模板与缓存 | 独立 `moontxnwitness_capture.orm` 入口；固定 base-user 点 CRUD SQL 编译、完全匹配及有界结构缓存 |
| ORM 局部诊断 | `inspectOrmSourceV3` / `inspect-orm-source-v3` 核验固定来源片段；保留 `history:null` 和明确覆盖缺口 |
| 数据库演示 | PostgreSQL 18 写偏斜与 Serializable 回滚/全新事务重试；SQLite WAL 并发案例 |

采集需要显式声明写者范围和 SQL 映射。未知提交、丢失来源或预算耗尽保留为无法判定。普通表入口会安装版本列、触发器和来源表，适用条件及示例见[普通表采集](docs/presence-capture.md)。关系分析要求显式模型事实；扩展来源持久化和完整 ORM 自动采集继续使用实验入口。

## 运行演示

下载并解压 portable ZIP，需要 Node.js ≥20：

```powershell
node dist/moontxnwitness.mjs --version
node dist/demo.mjs
```

Windows 可双击 `run-demo.cmd`。演示使用合成案例，在新目录生成中文报告、7→2 事务缩减和可回放证据，先打开 `report.md`。

## 检查、缩减与回放

```powershell
node dist/moontxnwitness.mjs check examples/write-skew.json --profile balanced
node dist/moontxnwitness.mjs shrink examples/noisy-write-skew.json --profile balanced --history mini.json
node dist/moontxnwitness.mjs check mini.json --profile balanced --format markdown --output report.md --capsule case.json
node dist/moontxnwitness.mjs replay case.json
node dist/moontxnwitness.mjs compare-models examples/strict-realtime.json
```

导出拒绝覆盖已有文件。`check` 支持 text/json/markdown/dot。

| 状态 | 退出码 | 含义 |
| --- | --- | --- |
| consistent | 0 | 在提供的模型、观察及约束内有可行串行执行 |
| violation | 1 | 发现直接异常、依赖环或完整搜索无解 |
| invalid | 2 | 输入或约束不合法 |
| inconclusive | 3 | 观察不足或预算耗尽 |

`complete` 不认证采集者或数据库全局完整性。`oneMinimal` 表示当前规则与预算下不能再单独删除任一剩余事务，不保证全局最小。

## 库与 SDK

```powershell
moon add HhWw96/moontxnwitness@0.1.7
```

```javascript
import {analyzeWithOptions, shrinkWithOptions, replayReport} from './dist/sdk.mjs';
const report = analyzeWithOptions(history);
const reduced = shrinkWithOptions(history, {maxChecks: 256});
console.log(report.status, reduced.oneMinimal);
console.log(replayReport(reduced.reducedHistory, reduced.report));
```

MoonBit 对应 `analyze_with_options`、`reduce_with_options` 等；旧入口和默认预算保持。每次同键写入必须使用唯一版本，业务值相同也不能复用版本。搜索补全单独标记，不变成已观察到的版本顺序。

| 范围 | 默认入口 | balanced 入口 |
| --- | --- | --- |
| 图分析 | 512 事务 / 10,000 操作 / 50,000 依赖 | 相同 |
| 精确串行补全 | 8 个提交事务 | 12 个提交事务 |
| 补全操作 / 初始键 | 512 / 128 | 相同 |
| 搜索前缀 / 操作检查 | 100,000 / 1,000,000 | 相同，可调低 |
| 缩减 | 64 事务 / 2,048 操作 / 128 次检查 | 512 事务 / 10,000 操作 / 256 次检查 |

高级缓存最多 50,000 项，满后停止插入。核心历史 JSON 限 1,048,576 UTF-16 单元，CLI 历史限 2 MiB UTF-8、深度 64。见[输入格式](docs/input-format.md)和[高级分析](docs/balanced-profile.md)。

## PostgreSQL 接入

按[自动采集说明](docs/automatic-capture.md)配置版本列与点查询映射，通过连接入口包装应用连接，保存采集文档后运行：

```powershell
node dist/moontxnwitness.mjs ingest capture-trace.json --history history.json
node dist/moontxnwitness.mjs check history.json --profile balanced --capsule case.json
node dist/postgres-demo.mjs
```

`ready` 表示可导出历史；`inconclusive` 或 `invalid` 保持 `history:null`。采集器保留文档所述驱动结果与异常，不添加业务重试。需要受控写者、一致初始快照和受支持 SQL。

真实演示需要 PostgreSQL 18 和可选 Python 驱动，保存实际结果、提交/回滚、40001 重试及复现包；缺少数据库时明确未执行。见[数据库流程](docs/postgres-capture.md)和[SQLite 案例](docs/sqlite-capture.md)。

## 有界追加列表

[列表 SDK](docs/list-sdk.md)提供 `normalizeListCaptureV3`、`analyzeListV3`、`reduceListV3`、`verifyListV3`、`makeListCapsuleV3`、`replayListCapsuleV3`。入口要求显式 `traceSchema:3`、`dataModel:"append-list-v1"`，保留调用者原始 JSON 字符串；不能混入其他数据模型。

```powershell
node examples/list-roundtrip.mjs
```

演示使用合成历史，将三个事务缩为两个事务的追加环反例，并保存分析、缩减、复现包及逐文件摘要。每个元素需要唯一身份，值为字符串且允许重复。精确分析最多六个已提交事务、128 个 append/read，默认最多 100,000 个状态和 1,000,000 次语义检查；缩减最多 256 次候选检查。来源不足、未知提交和计算未完成保持无法判定，`oneMinimal` 只表示同一规则下的事务单删最小。

胶囊 `valid:true` 表示报告可重算，仍须读取 `status` 与覆盖标记；它也可能重放如实记录的 invalid 或 inconclusive 诊断。列表入口不提供自动 SQL 采集或完整隔离级别分类，语义与额度见[模型说明](docs/list-v3.md)。

## 有界关系集合

[关系 SDK](docs/relation-sdk.md)提供规范化、分析、缩减、验证和复现包重放六个入口，要求显式 `dataModel:"relation-set-v1"`。支持完整结果集合与空结果、字段等值/区间 AND 谓词，以及插入、更新、删除和保存点；实际写影响与完整查询分别记录。

```powershell
node examples/relation-roundtrip.mjs
```

合成示例将四个事务缩为三个，保留被异常事务读取的生产者。删除该生产者会丢失来源，不能为了得到更小反例而忽略。类型、完整性与精确搜索额度见[关系模型](docs/relation-v3.md)；任意 SQL 自动映射、混合模型和完整隔离分类仍不支持。

## ORM 模板与来源诊断

[Python 模板入口](docs/orm-plans.md)提供固定 FastAPI Users SQLAlchemy v7.0.0 base-user 的按 ID 查询、创建、修改及删除 SQL。普通导入无需可选依赖，编译时使用 SQLAlchemy 2.0.55。缓存只保存不可变计划，默认最多 128 项、1 MiB 计费条目字节；参数、结果与事务状态不进入缓存。该入口本身不执行 SQL。

[MoonBit 来源诊断](docs/orm-source-v3.md)核验原始 SQL、同语句来源、回滚与效果账本的对应关系。局部证明成功仍保留 `analysisCoverageAccepted:false`，不能据此推断完整事务历史。`ProvenanceObserver`、安装迁移及完整 ORM 采集仍为实验能力。

## 预览功能

- [v3 生命周期](docs/v3-contract.md)、[分段磁盘日志](docs/capture-journal-v3.md)：独立 `check-v3` / `reduce-v3` / `replay-v3` 入口。
- [普通表扩展来源](experiments/provenance/PRESENCE_PROFILE.md)、[dislock](docs/dislock-v3.md)：按适配器声明的 SQL 与来源范围使用。
- [执行故障诊断](experiments/faults/mlflow/README.md)：死锁等故障单列，不冒充隔离模型违反。

预览格式可能调整。v0.1.7 显式兼容 v0.1.1 至 v0.1.6 的既有算法的显式兼容检查；更早研究期记录仍可能需要对应源码回放。不支持的 SQL、缺失来源与覆盖缺口始终可见；尚不提供任意 SQL 插桩或完整隔离级别分类。

## 开发与验证

需要 MoonBit、Node.js 和 Python，无需 npm install：

```powershell
npm run build
npm test
npm run package
```

测试覆盖跨目标核心、10,320 份独立串行重放、6,373 份环证据、解析差分、缩减与 CLI；发行包另在全新目录构建和运行。见[开发说明](docs/development.md)。

性能优化保持完整报告、依赖来源及预算语义。测量和环境见[性能报告](docs/performance.md)，进一步提速与扩容按[后续路线](docs/remaining-execution-plan.md)推进。

Apache-2.0。依赖和参考来源见 [THIRD_PARTY.md](THIRD_PARTY.md)；逐版测试与下载记录在 `verification/releases/`，详细证据见[开发记录](docs/development-status.md)。
