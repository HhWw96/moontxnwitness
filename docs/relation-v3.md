# relation-set-v1 开发模型

v3 现在可以分析完整谓词查询与实际行写入的关系集合事实。此入口属于实验实现，使用 [关系模型契约](relation-v3-contract-draft.md)，尚未冻结 v0.2.0。它不自动证明任意 SQL 或 ORM 的语义，也不提供六种隔离模型分类。旧 v1/v2 接口和证据重放规则保持原样。

## 支持范围

输入使用 `traceSchema:3`、`dataModel:"relation-set-v1"`、`relationSchema`，以及 v3 事件和覆盖声明。一个轨迹只能使用一种数据模型。

- 列类型为 int64、布尔和文本；int64 用规范十进制 JSON 字符串，文本按 Unicode 码点比较。主键为 int64 或文本。
- `row_read` 是实际交付的完整结果集合，谓词支持最多八项字段等值或区间 AND；空结果也有语义。
- `row_write` 是实际 insert/update/delete 效果。删除有独立墓碑版本，删除后重插引用它；同值更新仍产生新版本。
- 写入前驱与返回影响行不构成业务 SELECT。UPDATE RETURNING 不能充当完整谓词查询。
- 保存点回滚恢复行和墓碑，保留此前已交付读取；中间写被覆盖不等于被回滚。未知提交、缺失来源和不完整快照继续阻止完整结论。

不支持 NULL、任意表达式、JOIN、聚合、子查询或混合模型事务。PostgreSQL text 无法表示 U+0000，数据库适配明确拒绝该值；模型本身仍支持它。SQL 比较规则须另行核验。

## 使用与证据

统一 SDK 通过 `normalizeCaptureV3`、`analyzeV3`、`reduceV3`、`verifyV3` 按 dataModel 分派；CLI 使用原有 `ingest-v3`、`check-v3`、`reduce-v3`、`verify-v3` 和 `replay-v3`。无需切换旧入口的默认模型。

```text
node dist/moontxnwitness.mjs check-v3 TRACE.json --output NEW_REPORT.json --capsule NEW_CAPSULE.json
node dist/moontxnwitness.mjs replay-v3 NEW_CAPSULE.json
node dist/moontxnwitness.mjs reduce-v3 TRACE.json --max-checks 256
```

结果为 consistent、violation、inconclusive 或 invalid。consistent 附串行顺序；violation 是描述性的已知来源错误或完整串行重放无解，不自动称为 G2。复现包绑定原始记录、规范化、报告和预算，验证器重新计算。SHA-256 不认证数据库或采集者。

精确入口最多 **6 个已提交事务、全轨迹 128 个行操作、100,000 个候选状态、1,000,000 次语义检查**。结构额度与精确额度分开，预算耗尽返回无法判定。已知直接来源反证不消耗搜索预算，但不能绕过覆盖及精确容量检查。缩减逐次重验来源闭包；`oneMinimal` 仍表示事务单删最小。

## 已执行的验证

127 项 MoonBit 边界测试覆盖类型、来源、保存点、完整查询、墓碑和预算。独立 Python 解释器在生产实现之前冻结 **170 个边界及 1,000 个不同生成输入**；共 1,170 份输入与当前实现零差异，704 个串行见证独立重放。57 项验收包含 35 类篡改与八项 CLI，另核对 1,138 份规范化、924 份来源及十项预算计数。早期 439 处差异与修复前原件保留在 [验证目录](../verification/relation-v3/)，未改写预期来消除差异。

[受控 PostgreSQL 18.6 实验](../experiments/relation_v3/README.md)已将空结果、插入幻影、删除重插、跨谓词更新、写偏斜、Serializable 中止后全新事务重试、同值新版本和保存点完整查询各执行 **20 轮**。160 份原始 SQL、参数、实际完整 SELECT、写影响、提交状态与最终账本分别核对，100 consistent / 60 violation 与预登记结果一致；160 份复现包通过。数据库执行收据和离线模型收据分别保存在 [真实数据库证据](../verification/relation-v3/postgres-2026-10-21/)。这是固定 fixture 的实际执行，不冒充通用 SQL 插桩。

```text
python -B scripts/relation-v3-oracle.py --self-test
node scripts/relation-v3-acceptance.mjs
python -B experiments/relation_v3/run_postgres.py --output NEW_DATABASE_OUTPUT
node experiments/relation_v3/e2e.mjs NEW_DATABASE_OUTPUT NEW_MODEL_OUTPUT
```

实际数据库入口需要可选驱动及明确的连接配置；缺少时记录 notExecuted、passed:false 和退出码 3。Linux 数据库 CI 使用同一冻结计划。独立干净环境公开下载验收、完整采集成本、非 fixture SQL、ORM 来源证明及六模型/Elle 对照仍分别设门槛；本页不声明这些工作已通过。
