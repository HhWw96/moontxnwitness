# MoonTxnWitness

MoonBit 通用事务异常分析基础库。以 Elle 的异常与模型定义为对照，提供可嵌入的分析、解释、缩减和证据回放。当前覆盖与待补能力见[Elle 对齐表](docs/elle-alignment.md)，后续按[开发顺序](docs/roadmap-v0.4.0.md)推进；定位不表示已完整兼容 Elle。

仓库已开始分离当前源码与历史实验归档；原始材料通过提交／标签恢复，规则和精简计数见[仓库布局](docs/repository-layout.md)。

自动诊断采集：使用 [`instrument_engine`／局部 psycopg 工厂](docs/diagnostic-instrumentation.md) 在业务启动时接入，保留实际执行和结果；通用入口输出执行诊断；配置化 [base-user 来源采集](docs/configured-user-profile.md) 可将受支持的按 ID 增删改查送入核心分析、缩减与重放。

**把事务读写日志变成可解释、可缩减、可回放的反例。** MoonBit 实现离线分析核心，提供 Mooncakes 库、JavaScript SDK、命令行和可选 PostgreSQL 采集器。

English: A MoonBit transaction anomaly analysis library with explainable witnesses, bounded model analysis, counterexample reduction and evidence replay. See the explicit Elle alignment and coverage matrix.

[源码](https://github.com/HhWw96/moontxnwitness) · [下载](https://github.com/HhWw96/moontxnwitness/releases) · [Mooncakes](https://mooncakes.io/docs/HhWw96/moontxnwitness) · [更新记录](CHANGELOG.md)

## 关系分析接口（开发分支）

关系行版本新增 G0、G1a、G1b、G1c、G2-item 和内部一致性分类，提供独立 SDK、命令行与证据回放入口。缩减可以指定保留的异常类别，并保留原始事件来源映射；完成全部剩余事务的单删检查后，才标记事务单最小。见[关系库使用示例](docs/relation-library-workflow.md)。

## v0.3.3

新增有完整来源引用的 `G-single` 检查、寄存器丢失更新和读取来源诊断；列表图可显式选择 `effective-v1`，处理同一事务同键的多次追加与保存点撤销。报告、验证器、复现包及命令行共用明确的算法和预算。

运行新例子：`node examples/v4-anomalies-roundtrip.mjs`。详细边界见 [v4 API](docs/v4-api.md)；后续关系分类、更多模型与配置化采集按支持矩阵推进。

## v0.3.2

新增[三模型结构化 v4 接口](docs/v4-api.md)：MoonBit 的 `HistoryV4`、`analyze_v4`、`classify_v4`、`reduce_v4`、`verify_v4`，以及对应 SDK 和命令行入口。缩减显式指定保留的模型反证，验证使用调用者自己的预算；旧入口保持。

源码包移出历史运行时和大语料，通过[按摘要校验的输入缓存](docs/input-cache.md)恢复。直接运行 MoonBit 核心无需下载这些材料；完整 SDK 构建与测试首次需要联网，之后可离线复用缓存。旧公开 v0.3.1 证据使用原运行时回放。

## v0.3.1

需要 MoonBit moonc ≥0.10.16。当前构建与 CI 固定使用 0.10.16+b1a0e846e。JSON 转换已迁移至新标准库接口，并在构建前检查编译器版本。

直接运行 MoonBit 核心库示例，无需 Node.js 或 Python：

```powershell
moon run --target wasm-gc src/demo
```

示例分析两事务写偏斜、核对环证据并验证缩减结果。JavaScript SDK 和 CLI 保留原入口；公开 v0.3.0 的原运行时通过固定下载摘要校验后用于旧证据回放。首次源码构建需要联网取得该兼容组件，已准备的缓存可离线复用，源码树不保存其副本。

## v0.3.0

本版收敛自动采集、三种数据模型、逐类别诊断和证据重放，新增[原生 MLflow HTTP 排障案例](docs/mlflow-http-case.md)。真实 `log-batch` 路由的修复前后各运行 30 个固定种子；原生死锁通过 SQLSTATE `40P01` 确认。案例由 1000 个键缩减至 623 个，同一最终请求在修复前连续三次复现、修复后连续三次成功，保留 `oneMinimal=false`。

无需数据库即可查看两份真实采集的差异并重放证据：

```powershell
node examples/mlflow-http-roundtrip.mjs
```

[来源日志缓冲](docs/performance-v0.3.0-capture.md)可显式配置，关闭时仍同步尾部并核验封存。正式 A/B/C 采集实验的目标尚未达到，完整结果与失败单元继续保留；不将局部优化或诊断回放耗时写成业务吞吐收益。六模型、关系精确分析和自动 SQL 映射的范围继续见[支持矩阵](docs/stable-scope.md)。

公开 v0.2.8 的原始报告与胶囊保留三个实际构建上下文，共 156 份原始案例；校验使用完整原运行时，不改证据、预算及历史预期。v0.3.0 的最终测试、独立验收与公开安装记录存于 `verification/releases/0.3.0/`，以相应收据为准。

## v0.2.8 支持范围

新增[统一诊断入口](docs/diagnosis-sdk.md)：`diagnoseV3` 与 `diagnose-v3` 同时保留串行分析、模型检查和证据缺口；`verifyDiagnosisV3` 可重新核对完整报告。事务读错自身写入会明确显示 INT，不会误标成 G2 或改写尚无法判定的其它模型。

关系反例缩减复用已解析的候选结构，并保留完整语义重验、来源、预算和旧接口。寄存器与列表入口继续采用原实现。公开 v0.2.7 证据通过固定旧运行时重放；构建时从实际工具链保留完整许可证与 NOTICE。固定关系候选负载测得 1.124× 提速，完整范围见[性能记录](docs/performance-v0.2.8-relation.md)。

配置化[列表与关系来源采集](docs/configured-model-profile.md)可从实际 SQL、原始返回、fetch 交付和事务结果自动投射模型事实，无需手写历史。[SDK 与命令行](docs/model-profile-sdk.md)提供分析、报告验证和完整原始来源包重放；10 个真实 PostgreSQL 场景覆盖 7 个受支持路径和 3 个明确无法判定的边界。配置化模型来源缩减留待后续版本。

已有独立[六模型检查入口](docs/classification-models-sdk.md)：对唯一版本点寄存器和声明的单追加列表范围，逐项检查异常与适用条件，输出反证、已完成检查及覆盖缺口。它补充 G1a、G1b、内部一致性、非相邻反依赖和有明确来源的实时关系。模型名称使用固定定义标识，不将结果直接等同于数据库产品的隔离级别。

已有 G0、G1c、G2-item [分类搜索及固定类别缩减](docs/classification-sdk.md)继续保留。配置化 base-user 采集可将受支持的按 ID 增删改查送入分析、缩减和重放；通用启动插桩保留实际 SQL、结果和执行诊断。完整范围见[支持矩阵](docs/stable-scope.md)。

可靠反证在其它检查预算耗尽时仍成立；缺少来源、完整读取、内部有效性或实时证据时，相关检查保持无法判定。关系六模型分类、模型保持缩减、任意 SQL 和完整认证系统接入仍未支持。重放成功说明证据可复现，不表示采集内容得到数据库真实性认证。

本版的实际构建、回归和公开交付以 `verification/releases/0.2.8/` 收据及[发行记录](https://github.com/HhWw96/moontxnwitness/releases)为准。默认分析实现继续保留已验证的算法；新增检查的成本与旧版完整分析分别报告。此前未通过性能控制的优化候选及[完整采集成本差距](docs/performance-v0.2.5-candidate.md)继续公开保留，Unicode 流式 JSON 预检查的[固定工作负载成对实验](docs/performance-experiment-streaming-json-guard.md)保留全部原始样本；该实验不等于所有当前版本调用的统一提速或内存下降。

## 运行演示

从源码克隆时，Windows 请启用 Git 长路径支持：`git -c core.longpaths=true clone --depth 1 https://github.com/HhWw96/moontxnwitness.git`。

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

`complete` 不认证采集者或数据库全局完整性。`oneMinimal` 表示当前规则与预算下不能再单独删除任一剩余事务，不保证全局最小。配置化 ORM 缩减只针对“来源闭合且有确定异常”的候选；来源闭合但预算未判定的候选会阻止这一声明。

## 库与 SDK

```powershell
moon add HhWw96/moontxnwitness@0.3.3
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

胶囊 `valid:true` 表示报告可重算，仍须读取 `status` 与覆盖标记；它也可能重放如实记录的 invalid 或 inconclusive 诊断。该精确入口与配置化 SQL 来源入口分别使用；列表逐模型分类仍有声明的图适用范围，语义与额度见[模型说明](docs/list-v3.md)及[支持矩阵](docs/stable-scope.md)。

## 有界关系集合

[关系 SDK](docs/relation-sdk.md)提供规范化、分析、缩减、验证和复现包重放六个入口，要求显式 `dataModel:"relation-set-v1"`。支持完整结果集合与空结果、字段等值/区间 AND 谓词，以及插入、更新、删除和保存点；实际写影响与完整查询分别记录。

```powershell
node examples/relation-roundtrip.mjs
```

合成示例将四个事务缩为三个，保留被异常事务读取的生产者。删除该生产者会丢失来源，不能为了得到更小反例而忽略。类型、完整性与精确搜索额度见[关系模型](docs/relation-v3.md)；任意 SQL 自动映射、混合模型和完整隔离分类仍不支持。

## ORM 模板与来源诊断

[Python 模板入口](docs/orm-plans.md)提供固定 FastAPI Users SQLAlchemy v7.0.0 base-user 的按 ID 查询、创建、修改及删除 SQL。普通导入无需可选依赖，编译时使用 SQLAlchemy 2.0.55。缓存只保存不可变计划，默认最多 128 项、1 MiB 计费条目字节；参数、结果与事务状态不进入缓存。该入口本身不执行 SQL。

[MoonBit 来源诊断](docs/orm-source-v3.md)核验原始 SQL、同语句来源、回滚与效果账本的对应关系。局部证明成功仍保留 `analysisCoverageAccepted:false`，不能据此推断完整事务历史。`ProvenanceObserver`、安装迁移及完整 ORM 采集仍为实验能力。

## 证据解读与执行诊断

`node examples/register-cycle-roundtrip.mjs` 解读已有且完整验证的点寄存器环，保存原模型包和独立派生解释；它不搜索全部类别或接受隔离模型。`node examples/execution-roundtrip.mjs` 离线比较两份旧 MLflow 组件观察，分别重放模型和执行诊断；40P01、未知结果及原 capture.py 来源缺口保留。用法见[环解读](docs/cycle-explanation-v3.md)和[执行诊断包](docs/execution-capsule-v3.md)。

已声明输入的 v3 寄存器、列表与关系工作流使用 `check-v3`、`reduce-v3`、`verify-v3`、`replay-v3`；旧 v1/v2 默认规则保持。显式引擎兼容名单与预算见[支持矩阵](docs/stable-scope.md)，兼容不改写业务版本。

## 实验与后续

[分段日志与来源窗口](docs/capture-journal-v3.md)按各自契约使用；更广普通表/ORM 路径、[dislock 完整生命周期](docs/dislock-v3.md)、关系六模型、模型保持缩减及 MLflow 原服务 HTTP 故障闭环继续开发。受控组件案例不是生产采用证明，不把这些工作作为已经交付的完整应用集成。未支持 SQL 和缺失来源始终可见。

## 开发与验证

需要 MoonBit、Node.js 和 Python，无需 npm install：

```powershell
npm run build
npm test
npm run package
```

测试覆盖跨目标核心、独立串行重放、环证据、解析差分、缩减、CLI 及各 SDK；数量与执行目标取当前版本真实收据，发行包另在全新目录构建和运行。见[开发说明](docs/development.md)。

性能优化保持完整报告、依赖来源及预算语义。测量和环境见[性能报告](docs/performance.md)，进一步提速与扩容按[后续路线](docs/remaining-execution-plan.md)推进。

Apache-2.0。依赖和参考来源见 [THIRD_PARTY.md](THIRD_PARTY.md)；逐版测试与下载记录在 `verification/releases/`，详细证据见[开发记录](docs/development-status.md)。
