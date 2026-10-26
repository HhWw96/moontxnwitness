# 当前版本补充

本轮v0.2.8新增统一诊断和关系缩减优化，技术验证、最终打包与公开下载分别记录。已有寄存器／受限列表六模型检查、三种模型分析、启动插桩、配置化base-user CRUD及列表／关系事实映射。关系六模型、任意SQL、模型保持缩减及MLflow原服务HTTP故障闭环仍未完成。当前能力以[支持矩阵](stable-scope.md)及实际发行收据为准。

以下项目说明保留v0.2.0时的历史范围，不能替代当前支持矩阵。

# MoonTxnWitness 项目说明

**面向数据库与后端开发者的离线事务证据工具。** MoonBit 负责事务模型、来源校验、依赖分析、有界搜索、缩减与语义重放，Node 提供本地 SDK/CLI 和便携入口，Python 可选适配器记录受支持的 PostgreSQL 观察。

v0.2.0 整合七类明确入口：唯一版本寄存器、固定键普通表存在性与 CRUD、固定 ORM SQL 模板/缓存及局部诊断、追加列表、关系行集合、已选中寄存器环解读、独立执行诊断包。每类的前提、预算和限制集中在[稳定支持矩阵](stable-scope.md)。列表和关系需要显式模型事实，不自动把任意 SQL 变成完整历史；普通表入口只适用于受控两列表、固定键和同步生成 SQL。

读写边保留操作、版本和来源。搜索补全与采集事实分开；unknown COMMIT、来源不足、查询不完整和预算耗尽保持可见。缩减每次重新验证，事务单删最小与全局最小分开。原 v1/v2 及显式版本的 v3 模型胶囊继续重放，独立执行包的有效性只表示完整诊断能够重算。

下载 portable 包后运行 `node dist/demo.mjs`。列表、关系与环示例分别是 `node examples/list-roundtrip.mjs`、`node examples/relation-roundtrip.mjs`、`node examples/register-cycle-roundtrip.mjs`；`node examples/execution-roundtrip.mjs` 比较两份既有 MLflow 组件记录并保存原模型包和执行诊断包。它不运行数据库，不把原40P01改名为隔离异常，也不证明完整应用已经修复。旧记录未绑定当时 capture.py 执行字节的缺口继续保留。

真实 PostgreSQL 演示使用 `node dist/postgres-demo.mjs`；按说明配置专属测试数据库和可选驱动，缺少条件就明确记录未执行。每次运行创建新证据目录。项目提供 Mooncakes 核心库、JavaScript SDK、命令行和独立 Python 采集包。

验证包含独立串行解释、解析差分、环与来源核对、缩减复验、篡改、跨目标测试、真实数据库及全新消费者。输入、实际执行环境、源码/运行时摘要、失败与成功收据保留在 [verification](../verification/)；本版状态以 `verification/releases/0.2.0/` 实际记录为准，不预填测试或性能结果。

生产分析器不依赖 Elle。开发对照在独立环境调用固定上游检查器并限制共同原始事实；随源码的参考原文保留各自许可。算法与术语参考见 [THIRD_PARTY.md](../THIRD_PARTY.md)。全自动 SQL、完整 ORM、六模型分类、完整 dislock/MLflow 生产接入和更大规模性能仍属[后续工作](remaining-execution-plan.md)。

安装与使用见[首页](../README.md)。历史计划、独立审计和许可证不因范围收敛而删除；实际用户反馈、生产采用与赛事审核分别记录，不由自动验证代填。
