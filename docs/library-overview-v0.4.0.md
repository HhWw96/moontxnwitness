# MoonTxnWitness：MoonBit 通用事务异常分析基础库

MoonTxnWitness 将事务的读写观察转为可核验的异常证据，面向数据库测试、后端并发回归和故障排查。核心由 MoonBit 实现，应用可直接调用结构化接口，也可使用 JavaScript SDK、命令行或可选 Python 采集适配器。

## 核心能力

| 能力 | 接口与证据 |
| --- | --- |
| 三种数据模型 | `HistoryV4` 分别表示唯一版本寄存器、追加列表和关系集合；观察、写效果、推断、判断与运行计数分别保存 |
| 逐类别异常分析 | 来源异常 G1a/G1b、内部一致性、G0/G1c、项目与谓词反依赖、G-single 和 G-nonadjacent 使用各自的检查入口和见证 |
| 模型规则组合 | `classifyModelsV4` 组合 14 个固定 Elle 规范模型定义，默认六个；记录每条必要规则的反证、检查完成或无法判定 |
| 类别保持缩减 | 每次删除重新核对来源与目标反证；只有全部剩余事务单删检查完成，才声明事务单最小 |
| 独立证据验证 | 调用者另行给定选项与预算，重新分析原始观察；复现包中的结论和预算不能自行授予验证权限 |
| 业务接入 | 指定 SQLAlchemy engine、同步／异步 psycopg 工厂；配置表、列、键和类型；保留实际结果消费、异常、保存点和提交响应 |

模型定义固定到 Elle 提交 `4e359e597c52938b0afebb8bc42273914d68a424`，包括 read-uncommitted、read-committed、repeatable-read、serializable、strict-serializable、snapshot-isolation、consistent-view，以及相应的 strong-session／strong 加强定义。[模型规则](model-obligations-v4.md)逐项说明适用来源和必要条件；数据库产品隔离级别与形式模型分别表达。

关系分析使用独立行版本图与谓词图，保存查询范围、实际返回集合、写影响、版本来源和证据位置。关系点模型可显式选择[原子主键行配置](relation-atomic-models-v4.md)；[关系谓词类别](relation-predicate-categories-v4.md)提供七类图检查。未证明查询完整性时，空返回不会自动变成不存在的事实。

## 安装与运行

核心与 CI 使用 MoonBit `0.10.16+b1a0e846e`，许可证为 Apache-2.0。

```text
moon add HhWw96/moontxnwitness@0.4.0
```

在源码项目直接运行 MoonBit 示例，无需 Node.js、Python 或数据库：

```text
moon run --target wasm-gc src/demo
```

源码 SDK 使用 Node.js 20 或以上；完整 SDK 首次构建按摘要取得兼容运行时，之后可复用缓存。也可从 GitHub Releases 下载便携 ZIP，直接运行下列离线示例：

```text
node examples/models-v4-roundtrip.mjs
node examples/relation-predicate-categories.mjs
node examples/relation-category-reduction.mjs
node examples/mlflow-http-roundtrip.mjs
```

每个示例包含输入、分析、证据验证或复现。基础调用示例与 CLI 选项见 [README](../README.md)、[v4 API](v4-api.md)和[关系库流程](relation-library-workflow.md)。

## 自动采集与真实排障

启动插桩仅作用于指定对象，保留业务 fetch 的实际交付与 COMMIT 响应。同一 PostgreSQL 结构解析器处理不同配置的表、列、单列主键及受支持条件，不依赖新增业务 SQL 模板。可选 SQLGlot 识别结构，MoonBit 独立核验原始 SQL、参数及投射。[配置化会话](configured-session-v4.md)提供封存、诊断与独立重放；当前会话命名空间提供结构、返回行与来源组件核验，并明确保持 `sourceFactsProduced=false`、`isolationAnalysisReady=false`；完整隔离分析还需独立证明全写者范围和完整窗口。

已保留 dislock、FastAPI Users base-user 和原生 MLflow HTTP 的实际采集及回放路径。[MLflow 案例](mlflow-http-case.md)对原生 `log-batch` 路径执行修复前后各 30 个固定种子，并将真实 SQLSTATE `40P01` 死锁案例从 1,000 个键缩减至 623 个。最终同一请求修复前三次复现、修复后三次成功，保留真实运行记录。执行死锁单独诊断，不标成隔离级别违反。

## 测试与性能

CI 在 Windows 和 Linux 执行检查、构建、跨目标测试、独立历史与环证据核对、实际 PostgreSQL 18、旧胶囊兼容及全新源码／便携消费者。完整基线保留 10,320 份独立历史和 6,373 份环证据；后续版本额外增加来源、关系谓词、模型规则、配置化 SQL 与篡改测试。各目标测试数以最终运行原始收据为准，JS 专有测试与共同测试分别计数。

集成 v0.3.8 对公开 v0.3.1 的同作业完整 SDK 实测：五个目标场景几何均值提速 **2.3742 倍**，峰值 RSS 下降 **19.60%**，三个控制场景通过。测试完整保留 49,770 条依赖边，使用三批、每批五次预热与三十次正式样本。[性能报告](native-report-performance.md)给出测量提交、原始产物摘要、范围与指标；采集成本和新模型分析另行测量。

## 源码与可复现交付

当前源码与历史运行材料分开；历史源码通过 Git 标签恢复，兼容组件和固定测试输入按完整 SHA-256 校验缓存。核心、适配器、CLI、测试与示例分层维护，便携包保留离线兼容闭包。GitHub Releases 与 Mooncakes 发布后，另行执行匿名完整下载摘要核对和全新注册表消费者测试。

支持范围、查询语义及预算见[支持矩阵](stable-scope.md)。混合模型事务、NULL、JOIN、聚合、任意函数及复杂子查询保留明确边界。来源不足、缺少顺序或预算耗尽始终可见；哈希与语义回放证明复现一致性，不认证原观察者或数据库全局行为。
