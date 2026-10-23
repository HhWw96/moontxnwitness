# v0.2.5 稳定支持矩阵

新增 `classifyV3`、`reduceClassificationV3`、`verifyClassificationV3` 及独立分类复现包。分别搜索 G0（WW）、G1c（WW/WR，包含 G0 蕴含）和 G2-item（包含项目反依赖）；每类独立预算，不用全局最短环替代类别搜索。原 `analyzeV3` 与最短环定义保持。见[用法及完整契约](classification-sdk.md)。

分类首版支持来源完整、必要版本顺序明确的唯一版本点寄存器。图容量为128事务、4096操作、50000边；每类别最多100000状态、1000000边检查。分类缩减固定一个类别，最多256候选，并复核最终原始事实子集和来源。剩余单删遇到无法判定时不声明 `oneMinimal`。类别检查相容不代表整个隔离模型相容，可靠反证不会被其他类别的预算耗尽覆盖。

本版的分类功能与旧完整分析性能分别报告。[平铺索引候选](performance-v0.2.5-candidate.md)未通过正式尾部耗时控制，保留原默认实现和失败记录；未据此宣称提速或内存下降。更早版本的范围与历史证据如下。

# v0.2.4 稳定支持矩阵

新增固定 FastAPI Users SQLAlchemy base-user profile：显式安装来源配置，在首次业务连接前接入指定 engine，记录原始 SQL、交付结果、来源及完整窗口，再由 MoonBit 独立核验。支持按 ID 查询、创建、声明字段更新和删除；提供独立分析、缩减及复现包入口。见[采集步骤](configured-user-profile.md)、[映射条件](orm-profile-promotion.md)与[SDK/CLI](orm-profile-sdk.md)。

必须满足受控表、初始化、写者范围及完整窗口条件。lower(email)、OAuth JOIN、任意 SQL、完整认证系统和完整 dislock 生命周期继续单列未覆盖。通用自动诊断及旧局部来源入口保留原覆盖缺口。ORM `oneMinimal` 仅针对来源闭合且有确定异常的候选，计算预算未知会阻止最小性声明；日志摘要不能认证数据库真实性。

本版同时修复采集成本测量的零吞吐处理、启动同步和任务超时配置；是否达成性能目标以实际正式测量为准，不以这些修复推算提升。原有分析预算与公开版本重放保持，实际 v0.2.3 八份复现包加入兼容检查。

# v0.2.3 稳定支持矩阵

v0.2.3 增加可选 `GroupedSourceSink`、共享有界队列与批量同步、持久化水位和来源索引核验；旧来源入口保留逐条同步。关闭后失败、短写和损坏索引会显式拒绝，连接与事务完成后释放活跃内存记录。完整采集成本与模型覆盖分别记录；使用方式见[批量持久化](grouped-source-persistence.md)。

v0.2.2 增加指定 SQLAlchemy engine 和局部 psycopg 工厂的启动插桩：记录实际结果交付、异常、原生提交响应、连接池及批量参数观察；同步、异步及丢失提交响应已单独执行六项 PostgreSQL 测试。使用方法见[启动插桩](diagnostic-instrumentation.md)，本版证据见 `verification/releases/0.2.2/`。此入口始终保留诊断覆盖缺口，尚不提供自动版本来源和完整隔离分析。

以下原稳定分析入口继续适用；旧版本实验保留原始产生版本。v0.2.1 的结构化优化已撤回，本版不继承候选提速数字。

# v0.2.0 原稳定范围

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
