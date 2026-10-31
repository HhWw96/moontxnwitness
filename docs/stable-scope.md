# 当前支持范围

## v0.3.4 关系点分类与来源规则

关系点图入口 `classifyRelationV4` 提供 G0、G1c、G2-item 的独立搜索和原操作见证。原始捕获的 G1a、G1b 由 `inspectCaptureAnomaliesV4` 核对；事务内部读取由 `inspectInternalConsistencyV4` 核对。它们分别提供验证和完整来源胶囊，并保持各自的判断范围。

`reduceRelationCategoryV4` 指定要保留的关系异常类别，每次候选删除后重验来源、图和见证。保存点撤销只作用于写效果，读取观察仍保留；最小性与完成的候选检查绑定。直接运行 `node examples/relation-category-reduction.mjs` 可查看缩减和重放，完整用法见[关系库工作流](relation-library-workflow.md)。

旧 `classifyV4` 的关系结果保留原语义；调用者显式使用新的关系入口。新版图分类与六模型检查分开，谓词及更广模型由后续独立接口提供。

# v0.3.0 支持矩阵补充

## v0.3.3 来源诊断与列表图

`classifyV4` 可显式检查 `G-single`，要求环恰有一条项目反依赖；原默认三类别与全局最短环定义保持。`inspectAnomaliesV4` 提供来源身份、事务内未来读取与列表顺序冲突诊断；`inspectLostUpdatesV4` 依据同一版本的实际外部读取和最终写证明寄存器丢失更新。两者具有独立算法、预算、验证入口和原始来源胶囊。

列表分类的 `listGraph: "effective-v1"` 使用已交付读取及可撤销写效果，支持同一事务同键多次追加；精确解释器上限保持。缺失来源、冲突顺序和预算耗尽保留覆盖缺口；单独的来源诊断不表示完整模型检查。关系分类、14 模型及通用 SQL 映射仍依后续版本分别接入。

## v0.3.2 结构化基础库

`HistoryV4` 保留已核验的结构化快照，提供分析、类别检查、显式目标缩减和验证。MoonBit、JavaScript SDK 与 CLI 使用同一核心。

| 数据模型 | v4 分析、验证与显式模型缩减 | v4 类别检查 |
| --- | --- | --- |
| 唯一版本点寄存器 | 支持；声明历史可选择 Serializable／StrictSerializable，采集历史使用 Serializable | G0、G1c、G2-item |
| 追加列表 | 支持既有唯一身份与来源规则下的 Serializable 分析 | 既有受支持图范围内的 G0、G1c、G2-item |
| 关系集合 | 支持既有关系精确解释器及来源闭合缩减 | 本版返回 unsupported |

验证与胶囊重放由调用者提供独立预算，不接受报告自行授予更高预算。缩减候选来源闭合但分析未判定时，不声明事务单最小。原 v1/v2/v3 接口与已公开的重放规则继续保留。

接口、模型限额和命令见 [v4 API](v4-api.md)；完整测试的冻结输入和旧运行时见 [输入缓存](input-cache.md)。直接 MoonBit 示例见 `examples/core-v4/`。

v0.3.0 汇总下列已有稳定入口，保持原分析上限、版本顺序要求、预算和覆盖缺口。新增加原生 MLflow HTTP 执行故障的完整实验链路、623 键实际缩减与同一请求修复回归，及其[离线证据示例](../examples/mlflow-http-roundtrip.mjs)。该示例重放既有真实采集，不新执行数据库；死锁属于执行故障，不能替代 G2 或隔离级别反证。

`install_user_profile()` 和 `install_model_profile()` 新增可选 `source_write_buffer_bytes`，默认 0 保留旧同步路径，显式非零采用有界文件缓冲并在封存前等待 flush/fsync/索引。实际数据库验证分别保留受支持路径和无法判定路径；通用 `instrument_engine()` 不会因此获得完整来源。见[配置与性能](performance-v0.3.0-capture.md)。

SDK 先执行原公开输入预算，再进行兼容头解析；胶囊内嵌报告也执行原独立上限。v1/v2 沿用 UTF-16 单元约定，v3 沿用 UTF-8 字节约定。对象表示按原入口单次转换，超限不能先触发大段 JSON 解析或整请求序列化。

旧 v0.2.8 报告、执行胶囊及配置化来源包通过固定原运行时校验。含编译身份的证据严格匹配唯一来源；早期仅有版本号的格式使用有界的原校验器序列，任一完整原校验通过才接受。未知或混合身份不回退。保留三个原构建上下文的全部 156 份原预期与先前失败记录。

关系六模型分类、模型保持缩减、任意 SQL/NULL/JOIN/聚合及混合模型事务仍未支持。正式完整采集目标未达到，不等同于生产成本达标。完整 HTTP 原始记录在 Git 中保留，SDK 下载包包含完整文件索引与两份原始示例采集，避免为每次安装重复下载全部实验日志。

# v0.2.8 支持矩阵补充

新增 diagnoseV3／verifyDiagnosisV3，将原串行分析、六模型检查、具体证据和覆盖缺口并列保留。入口接受不超过8 MiB的原始 v3 轨迹，报告使用独立格式和 diagnosis-host-1 算法；验证会重算完整报告。INT 不替换成 G2；可靠反证和检查是否完成分开显示。参见[诊断用法与预算](diagnosis-sdk.md)。

关系缩减复用已解析候选，保留原始来源、相同判断和最终完整重验。列表及寄存器维持原实现；固定负载的候选测量为1.1243倍，尚未达到1.25倍目标，[测量范围](performance-v0.2.8-relation.md)与最终版本成本分开。真实公开0.2.7的46类报告及复现包通过原始运行时重放；普通当前分析不启动历史 worker。

本次集成的实际回归、数据库与发布记录存于 verification/releases/0.2.8/，以相应收据的完成状态为准。下面逐版保留已有能力、预算和原版本证据；历史验收不会改标为本版新执行。

# v0.2.7 稳定支持矩阵

新增显式配置化列表与关系来源入口：`install_model_profile()`、`analyzeModelProfileV3`、`verifyModelProfileV3` 与完整来源复现包。从受支持的真实 SQL、参数、数据库返回、实际 fetch 和事务结果映射事实，由 MoonBit 独立核验。见[安装与 SQL 范围](configured-model-profile.md)和[SDK／CLI](model-profile-sdk.md)。

入口使用独立受控 PostgreSQL18 schema、同步 psycopg 工厂及明确初始化／写者范围；声明之外的 SQL、零行或多行条件写、缺失来源及未确认结果保留诊断和无法判定。列表与关系精确解释器维持6个提交事务、128操作的范围，耗尽返回无法判定。新配置化来源入口提供分析、验证和完整包重放；来源闭合缩减、关系六模型及混合模型事务留待后续。

实际 CI 已执行10个配置化数据库场景，7个支持投射与独立解释器核对，3个拒绝扩大覆盖；独立安装包复核还完成原公开0.2.6的35家族／623检查和当前10采集包重放及70项篡改拒绝。本机独立源码重编译未执行，源码消费者与Linux Native由实际CI执行。完整收据见 `verification/releases/0.2.7/`，公开发布与下载核验分别记录。

Unicode 流式 JSON 预检查保持旧错误与回退行为。[固定v0.2.6成对实验](performance-experiment-streaming-json-guard.md)中，128事务完整SDK约1.235倍、六模型组几何平均约1.202倍；128组峰值RSS未下降。该实验不是整个新版本或新增模型入口的统一性能结论。既有能力、范围和失败证据继续保留如下。

# v0.2.6 稳定支持矩阵

新增 `classifyModelsV3`、`verifyModelsClassificationV3` 及独立模型复现包，默认逐项检查六个固定定义：`adya-pl-1-v1`、`adya-pl-2-v1`、`adya-pl-2.99-v1`、`elle-generalized-si-v1`、`adya-pl-3-v1`、`strict-pl-ss-v1`。所选模型全部必要检查完成且适用条件满足，才报告这段所给历史相容；具体反证不被其它搜索的预算耗尽覆盖。见[入口与示例](classification-models-sdk.md)及[反证蕴含修复](classification-implication-v026.md)。

寄存器图限制保持128事务、4096操作、50000边；每个图规则分别受100000状态和1000000边检查约束。列表图首版要求每事务每键最多一次追加、完整来源顺序、无保存点，最多6个已提交事务和128操作。更广的列表输入可能提供可靠的直接 G1a/G1b 反证，同时图检查仍无法判定。关系六模型、混合模型、模型保持缩减未支持，原固定类别缩减仍可用。

严格模型要求单独绑定的客户端区间、事务生命周期和日志索引；不以 BEGIN 时间推断快照，也不以原 trace 的时间字段推断实时关系。摘要绑定不认证采集器，未提供的日志段内容不会被声称已重算。原始规则状态、预算和证据各自保留；模型的 `refutationWitnesses` 指向实际已证明的最具体规则，不能把 unknown 规则改写为完成。

示例中的严格来源正例为合成输入，保留的四个真实采集包仍按原始来源与覆盖状态解释；没有将它们提升为新的数据库严格隔离验收。旧版支持矩阵与失败证据如下。

本版实际验证与[性能结果](performance-v0.2.6.md)分别记录：三目标各748项核心测试、独立包内513项检查、当前基础数据库回归均通过；性能目标未通过，保留失败样本并继续优化。

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
