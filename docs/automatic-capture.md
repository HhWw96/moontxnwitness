# PostgreSQL 自动采集开发版

v0.1.1 开发版增加可选 Python 驱动适配器。应用通过连接入口接入，配置已有版本列和点查询映射后，由适配器记录实际执行并生成采集文档；MoonBit 校验完整性和事务生命周期，再交给原有分析器。

该版本要求已有的文本版本列、每键唯一的写入版本、单列主键和普通表。普通无版本列业务、ORM、保存点、插入删除和范围查询属于后续版本；当前遇到这些操作会保留业务执行并给出覆盖缺口。详细 API、同步及异步例子见 [适配器说明](../integrations/python/moontxnwitness_capture/README.md)。

## 安装与使用

安装 Node、MoonBit 和可选 psycopg 3 驱动后构建本项目。将 `integrations/python` 加入应用的 Python 导入路径，使用 `CaptureSession` 的连接工厂，或包装由应用创建的空闲连接。

推荐通过表声明生成已知 SQL 结构；保留原 SQL 时可显式注册映射。自定义映射是用户提供的语义约定，工具只精确匹配语句，不能证明任意 SQL 都符合声明的语义。它不会自动重写业务 SQL、插入业务锁或重试。

该可信声明还包含 SQL 涉及的约束及函数语义。稳定适配器在初始化时保守拒绝传出或传入外键、重写规则及传统继承父子关系，但没有全面审计任意 CHECK 函数、表达式和数据库函数中的隐藏读写；生成模板也不代表自动证明所有数据库副作用。

初始化使用独立的空闲自动提交连接，持有 setup-only SHARE 表锁采集一致初始状态。必须在业务事务开始前完成，不能把首次读值当初始版本。`exclusive_writers=True` 表示受控窗口内相关写者全部接入，是明确的部署假设，不代表包装器能够发现任意外部客户端。

结束采集后，保存 `capture.document()` 的 JSON，再运行：

```sh
node dist/moontxnwitness.mjs ingest capture-trace.json --output coverage.json --history history.json
node dist/moontxnwitness.mjs check history.json --profile balanced --format json --capsule case.capsule.json
node dist/moontxnwitness.mjs shrink history.json --profile balanced --output reduced.json
node dist/moontxnwitness.mjs replay case.capsule.json
```

SDK 提供 `normalizeCapture(trace)`。它与命令行共同使用 MoonBit `normalize_capture_json`，不在 JS 中另写判定逻辑。`ingest` 接受文件或标准输入，输出文件必须尚不存在。

普通表 CRUD 的实验使用独立 `traceSchema: 2`，调用 `normalizePresenceCapture(trace)` 或 `ingest-presence`。它在固定已知键集合内记录存在性、墓碑和同语句版本来源，详情见 [实验说明](../experiments/provenance/PRESENCE_PROFILE.md)。原 `normalizeCapture` / `ingest` 继续拒绝该新格式；实验不是任意 SQL、ORM 或范围查询支持。

## 采集结果和分析结果分开

| 归一化状态 | 含义 | 是否导出历史 |
| --- | --- | --- |
| `ready` | 记录在声明范围及输入预算内完整，可交给现有分析器 | 是；不表示符合隔离模型 |
| `inconclusive` | 有覆盖缺口、丢失事件、未知提交、未结束事务或未证明写者范围 | 否，`history: null` |
| `invalid` | 格式、身份、事务顺序或资源约束不符合契约 | 否，`history: null` |

命令行退出码分别为 0、3、2。指定 `--history` 而结果不能导出时，不创建历史文件。不会把部分采集记录包装成完整历史继续判断。

未知提交不会被当成回滚；服务器明确报告 40001/40P01、诊断匹配且 libpq 确认已经空闲时，才可确认中止。保存点和未支持方法不被粗暴展平成一组已经提交的操作。

`traceSchema: 1` 文档包括时钟域、写者范围、连续编号事件和覆盖缺口；事件分为一致快照、事务开始、实际读写、SQL 原始观察及事务结束。MoonBit 限制输入为 8 Mi UTF-16 单位、65,536 事件，归一化结果还须满足已有历史的资源约束。

## 采集器资源边界

参数或返回行的整棵树共用预算，默认最多访问 16,384 个节点、生成 256 KiB 紧凑 UTF-8 JSON，包含转义和有类型编码的膨胀。逐步计费后才复制对应子树；嵌套最多 8 层，单容器最多 10,000 项，单个原始字符串或二进制缓冲区最多 65,536 字符或字节。`memoryview` 按实际 `nbytes` 在 base64 分配前检查，非连续视图直接产生不支持值缺口，不另行复制成连续缓冲区。

单事件默认最多 512 KiB、65,536 节点；会话默认最多 65,536 个事件，保留事件和缺口的紧凑 JSON 计费不超过 8 MiB、262,144 节点，并预留文档外壳及终止缺口空间。普通缺口最多 64 个，另外最多保留一个预算耗尽标记；缺口代码和说明分别限制 128、512 字符。SQL 原文采集最多 65,536 字符。可通过 `CaptureSession` 的 `max_value_nodes`、`max_value_bytes`、`max_event_bytes`、`max_events`、`max_session_bytes`、`max_session_nodes`、`max_gaps` 参数调整，不能据此扩大核心分析器的独立预算。

初始状态最多保留 10,000 个键；SQL 只获取剩余键额度加一行用于检测溢出，适配器每批最多取 64 行，并在每个键和版本加入前检查共享字节及节点预算。超限会使初始化失败并留下缺口。原始参数或返回值超限时，省略其原始编码并留下缺口；事件或会话预算耗尽后停止保留后续事件，业务 SQL、原始参数、返回对象和异常仍按驱动行为继续。

这些限制约束采集器复制、遍历和保留的证据，不是整个进程的内存上限。应用原有对象、驱动及 libpq 结果缓冲、配置映射和同时执行中的调用不计入；初始化分批也不限制单个数据库字段或驱动缓冲大小。`document()` 复制已限额的证据，序列化时仍可能短暂持有额外副本；美化输出、原始日志封装及核心输入另有大小限制。

## 原始日志

JSONL 包含 header、event、gap 和带计数及摘要的 footer。`load_jsonl()` 可以恢复有效前缀；缺失或损坏 footer、非对象记录、预算超限及摘要不匹配都会保留缺口。原始日志默认限制总量 32 MiB、单行 1 MiB 和 65,536 个事件，文档预算独立生效，不能截去记录后伪称完整。

原始 SQL、参数和读取结果可能含业务数据；发布前需审查。大整数等值使用有类型编码，避免 JS 数字精度改变证据。摘要用于检测变化，不认证采集者，也不证明日志从未被伪造。

## 验证入口

```sh
npm test
npm run capture:verify
npm run benchmark:baseline
```

`npm test` 包含跨目标核心、独立历史重放、证据和 CLI 回归，以及使用假驱动的适配器单元测试；假驱动测试不算真实数据库执行。

`capture:verify` 要求 `MTW_PG_DSN`，或仅指向本地连接配置文件的 `MTW_PG_CONNECTION_FILE`，以及可选 `MTW_PYTHON`。受控实例可用 `scripts/capture-local-postgres.py` 启动，验证后关闭，日志保存在被忽略的本地 artifacts 目录；凭据不进入公开记录。正式 PostgreSQL CI 另行运行相同测试。

受控场景用于验证采集、归一化、异常分析、缩减和复现，不能替代真实业务采用证据。v0.1.1 的已有外部业务接入验收仍需单独完成；尚未完成时保持开发版状态。

直接性能基线见 [固定 v0.1.0 基线](../verification/baselines/0.1.0/README.md)。新记录不会把历史测量拼接成当前提速结论。
