# v0.2.0 稳定支持矩阵

本版整合已经形成可运行入口的有界能力。稳定范围以本页、相应输入契约、实际算法标识和记录的预算为准；不表示早期路线的全部研究目标已实现。正式构建、独立复核、数据库回归、安装和公开下载分别见 `verification/releases/0.2.0/` 的实际收据。未执行项目不能用旧版本或候选成绩替代。

| 稳定入口 | 支持范围与运行方式 | 边界 |
| --- | --- | --- |
| 寄存器与明确映射采集 | 唯一写入版本的点读写；v1/v2 的 serializable / strict-serializable，v3 的显式 `register-serializable-v1`；依赖来源、最短环、有界补全、缩减及重放。可选 psycopg 同步/异步版本列采集。[格式](input-format.md) · [高级预算](balanced-profile.md) · [采集](automatic-capture.md) | 需要受控写者、完整初始事实及受支持 SQL 映射；不从时间戳、事务身份或补全结果发明采集顺序。 |
| 固定键存在性与 CRUD | `moontxnwitness_capture.presence`；受控两列表、最多64个固定文本键、同步点查询、插入/更新/删除、负读和墓碑来源。[用法](presence-capture.md) | 安装版本列、触发器和来源表；需满足 DDL、初始化确认与写者范围。域外写、任意条件 SQL、异步、保存点及 ORM 不在此入口。 |
| 固定 ORM SQL 模板与局部诊断 | `moontxnwitness_capture.orm` 编译固定 base-user 按 ID CRUD 模板并有界缓存；`inspectOrmSourceV3` 核验固定原始来源片段。[模板](orm-plans.md) · [诊断](orm-source-v3.md) | 模板入口不执行 SQL、不消费结果。局部诊断保留 `analysisCoverageAccepted:false`、`history:null`；不能提升为完整 ORM 历史。 |
| 追加列表 | 显式 `append-list-v1` 六个 SDK 入口，唯一元素身份、可重复字符串业务值、来源校验、有界分析/缩减/重放。[SDK](list-sdk.md) | 精确分析最多六个已提交事务、128个 append/read；未知来源、提交及预算耗尽保持无法判定。不混模型。 |
| 关系行集合 | 显式 `relation-set-v1` 六个 SDK 入口；完整结果/空结果、等值及区间 AND 谓词、插入/更新/删除和保存点。[SDK](relation-sdk.md) · [契约](relation-v3-contract-draft.md) | 精确分析最多六个已提交事务、全轨迹128个行读写；int64/bool/text，明确比较规则；NULL、JOIN、函数、聚合、子查询与任意 SQL 自动映射不支持。不混模型。 |
| 已选中环的类型和来源解读 | `explainRegisterCycleV3` / `verifyRegisterCycleExplanationV3`，从已验证且完整的点寄存器依赖环重算类型及原始来源。[用法](cycle-explanation-v3.md) | 解释现有见证，不搜索全部异常类别，也不据一个环接受隔离模型。首尾相邻与全部匹配来源均按原规则保留。 |
| 独立执行诊断包 | `makeExecutionCapsuleV3` / `replayExecutionCapsuleV3` 封存原始 v3 文本与完整执行诊断，使用独立 `moontxnwitness-execution/v1` 格式。[用法](execution-capsule-v3.md) | `valid:true` 仅指诊断可重算；40P01等仍是执行故障，unknown和覆盖缺口保持。不是模型结论、真实性认证、无故障或修复证明。 |

运行合成与离线示例：`node dist/demo.mjs`、`node examples/list-roundtrip.mjs`、`node examples/relation-roundtrip.mjs`、`node examples/register-cycle-roundtrip.mjs`、`node examples/execution-roundtrip.mjs`。最后一项比较两份既有 MLflow 组件记录，不执行数据库。原记录当时未绑定所依赖 capture.py 的执行字节，这个来源缺口保留在随包 `fixtures/execution-v3/source-origin.json`。

真实数据库证据保留其产生版本：ORM 记录来自 v0.1.3、列表来自 v0.1.4、关系来自 v0.1.5；v0.1.6 聚合中的这些记录另做了当前核心离线重放。它们与各版新执行的寄存器/采集/普通表/初始化 SQL 分开，不能改标为 v0.2.0 全套全新数据库执行。后续实际重跑以新收据单列。

寄存器默认及 balanced 入口的额度保持，列表/关系和诊断包分别使用自己的结构、计算和字节预算。范围超过约定、输入无效、观察不足与预算耗尽按对应契约返回 invalid 或 inconclusive，不能截断事实后出具完整结论。`oneMinimal` 仍只表示当前异常规则下完成事务单删检查；不保证全局最小。

v1/v2 保留原算法与重放规则；v3 模型报告和原胶囊显式兼容既有 v0.1.1 至 v0.1.8 引擎。执行包在 v0.2.0 中仅额外接受同算法的 v0.1.7、v0.1.8；未知引擎、算法、预算或语义篡改仍拒绝。兼容只处理引擎头，绝不改写业务 version、原始 SQL、错误或诊断字段。派生环解读与原报告/胶囊分开保存并重新验证。

后续继续研究：全自动 SQL 插桩、完整 ORM 采集与安装、全部六模型分类与扩展 Elle 对照、完整 dislock/MLflow 生产接入、更多真实业务回归，以及扩大规模和同条件性能优化。实验日志/来源窗口和其它预览入口按各自文档使用，不能据本表升级为稳定。默认生产解析器保留已发布17版完整实现。ASCII 复用候选首次正式对照的正确性通过，但性能控制验收未满足，已从稳定默认路径回退；原5999/5b63试验和首失败保持。新81b稳定18及本版不能继承其性能结论，不预填耗时、倍数或 RSS 成功。

[后续安排](remaining-execution-plan.md)与[方向路线](roadmap-v0.2.0.md)继续维护。原[30–40工作日及逐版大门槛计划](remaining-execution-plan-2026-10-21.md)按固定源码原文保留为历史，不是本版发布前置。公开安装、真实用户反馈、生产采用和赛事审核分别记录，技术发布不等于官方通过。
