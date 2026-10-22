# 普通表点查询与 CRUD 采集

v0.1.2 提供独立的 Python 入口，用于受控 PostgreSQL 18 表的点查询、负读、插入、更新和删除。业务表无需预先维护版本；初始化会安装版本列、事务性来源表、触发器和辅助函数。必须先评估这些数据库变更，在专用的 `mtw_provenance_*` schema 中使用。

将 `integrations/python` 放入应用导入路径，并安装可选 psycopg 3 驱动（验证环境使用 3.3.6）：

```python
from moontxnwitness_capture.presence import PresenceCapture, PresencePointProfile

profile = PresencePointProfile("mtw_provenance_my_app", "items")
# 原表为 items(id text PRIMARY KEY, value text)，可空 value 也受支持。
capture = PresenceCapture(profile, keys=("a", "b", "new"), exclusive_writers=True)
capture.initialize(dedicated_idle_autocommit_setup_connection)

connection = capture.wrap(idle_business_connection)
assert connection.execute(profile.read_sql, ("new",)).fetchone() is None
connection.execute(profile.insert_sql, ("new", "created"))
connection.execute(profile.update_sql, ("changed", "new"))
connection.execute(profile.delete_sql, ("new",))
connection.commit()

# 业务停止、事务结束后保存完整 JSON 文档。
capture.close()
trace = capture.document()
# 最后停止全部业务连接，再按需卸载本次安装。
capture.uninstall(dedicated_idle_autocommit_setup_connection)
```

初始化必须先于业务连接和并发事务。原表恰有主键和值两列，主键为文本、不可变；最多声明 64 个键，每键不超过 512 个 UTF-8 字节，需包含全部现有键。原表不能有默认值、生成列、用户触发器、RLS、外键、继承、CHECK/EXCLUDE 或不受支持的索引。初始化会核对实际 DDL，拒绝超出范围的表。

固定键范围包含明确不存在的键，支持后续插入、删除及重新插入。域外写入和主键变更会被安装的触发器拒绝，应用必须遵守这一约定。相关写者须全部接入同一受控窗口；`exclusive_writers=True` 是部署声明，不能自动发现外部写者。

初始化仅在服务器明确确认 COMMIT 后发布初始快照。失败或应答未知的采集器不能重试初始化或包装连接；保留原始异常，并人工检查本次数据库安装是否已经提交，再使用全新采集器。ROLLBACK 命令返回不能补作提交确认。

普通查询仍向业务交付原来的零/一行，新增的来源列对业务隐藏；只有实际交付行或 EOF 才记录读取。写入来源和删除墓碑来自同一语句的不可变记录，元数据前驱不会伪造成业务读取。未消费结果、未知 SQL、零行更新/删除及未确认提交保持覆盖缺口。

输出为完整 `traceSchema: 2` 文档。保存后执行：

```sh
node dist/moontxnwitness.mjs ingest-presence capture.json --history history.json
node dist/moontxnwitness.mjs check history.json --profile balanced --capsule case.json
node dist/moontxnwitness.mjs replay case.json
```

SDK 对应 `normalizePresenceCapture(trace)`。旧 `ingest` / `normalizeCapture` 仍处理 schema 1。为重放既有证据，schema 2 的投射标识保留历史字符串 `column-presence-register-v0.1.2-experimental`，它不是新版本号。

本入口使用同步标准 tuple 游标和生成的 SQL；UPSERT、原始 RETURNING、任意条件/多行 SQL、保存点、异步与 ORM 使用各自预览能力。schema 2 目前保存有界完整文档，不支持 `jsonl_path`；默认记录预算为 8 MiB、262,144 节点及 65,536 事件，读写来源合计上限 10,000，耗尽时无法导出完整历史。可持续日志和来源窗口另行迭代。

现有 `experiments/provenance` 导入保留为兼容入口；新代码使用上面的包路径。完整来源与游标规则见[协议细节](../experiments/provenance/PRESENCE_PROFILE.md)。
