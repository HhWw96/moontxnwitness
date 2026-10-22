# append-list-v1 有界列表模型

v0.1.4 在声明的来源和预算范围内支持追加列表分析、缩减及复现。元素使用唯一身份，值为字符串；它提供该模型的有界串行判断，不代表通用 SQL 采集、关系谓词、完整隔离级别分类或 Elle 等价实现。旧 v1/v2 接口与复现规则保持原样。当前版本的实际公开交付状态见[开发与发行记录](development-status.md)。

使用方法及六个显式 SDK 入口见[列表 SDK 与演示](list-sdk.md)。运行 `node examples/list-roundtrip.mjs` 可将三个事务的合成异常缩成两个事务，并保存原输入、分析、缩减、复现包和重放结果。

## 输入与业务值

根对象使用 `traceSchema:3` 和 `dataModel:"append-list-v1"`，并保留 `clockDomain`、`scope:{exclusiveWriters}`、`events`、`gaps`。事件序号从 1 连续，时间全局单调不减；它们不提供服务器提交顺序或实时一致性约束。

列表事件：

| kind | 字段 | 模型含义 |
| --- | --- | --- |
| snapshot | initial、consistent | `initial` 将每个键映射为有序的 `[{id,value}]` 数组，包括空列表 |
| append | tx、key、id、value | 在列表尾部追加一个新身份 |
| list_read | tx、key、items | 业务实际收到的完整有序列表快照 |

`value` 目前只接受 JSON 字符串，允许重复业务值。身份 `id` 在所有初始列表与 append 事件之间全局唯一；不能用业务值代替身份，也不能用客户端序号推断列表位置。返回列表中的重复身份、错误业务值或错误键属于模型反证，保留原观察，不把它们改写为格式错误。未知身份或记录在读取之后才出现的生产事件属于采集来源缺口，后续日志不能追认其先前已被观察。

生命周期继续使用 [v3 契约](v3-contract.md) 的 begin、savepoint、rollback_to、release、commit_request、commit_ok、rollback_ok 和 disconnect。SQL statement、rows 与 condition 原样保留；列表入口没有证明 SQL 到列表事实的对应关系，因此它们会留下覆盖缺口。寄存器 read/write 不能混入列表记录，关系操作也不能混入。

简例：

```json
{
  "traceSchema": 3,
  "dataModel": "append-list-v1",
  "clockDomain": "example",
  "scope": { "exclusiveWriters": true },
  "events": [
    { "seq": 1, "time": 0, "kind": "snapshot", "initial": { "messages": [] }, "consistent": true },
    { "seq": 2, "time": 1, "kind": "begin", "tx": "T", "connection": "c" },
    { "seq": 3, "time": 2, "kind": "append", "tx": "T", "key": "messages", "id": "m1", "value": "hello" },
    { "seq": 4, "time": 3, "kind": "list_read", "tx": "T", "key": "messages", "items": [{ "id": "m1", "value": "hello" }] },
    { "seq": 5, "time": 4, "kind": "commit_request", "tx": "T" },
    { "seq": 6, "time": 5, "kind": "commit_ok", "tx": "T" }
  ],
  "gaps": []
}
```

## 保存点与已交付读取

规范化输出保留原始 `observations`，另列 append `effects` 和事务账本 `transactions`。每个效果有原始 seq、真实 key/id/value 与 `revertedBy`。保存点回滚只撤销效果，不删除已经交付的读取。列表事务的 `finalWrites` 是全部未撤销 append 的序号；同键的多个追加均保留。

精确串行解释器只要求**已提交事务的完整日志**能串行重放，其中包括该事务后来回滚的保存点内已经交付的读取。合法的自身追加、读取、再回滚仍可通过。已中止事务的读取保留观察，但不强加 opacity；未知来源仍是采集缺口。

已提交事务读取已知中止事务的追加，或读取明确撤销的追加，是来源可证的反证。自身读取先于同笔事务后来的回滚时，不按最终状态倒推它非法；自身读取发生在撤销之后则可以反证。

底层只复用寄存器 v3 的生命周期与保存点校验。内部每个 append 使用独立的记账槽，list_read 使用无效果的生命周期记号；这个适配不参与模型判断。记账键、版本与合成 history 不进入公开观察、来源证据或判断。真实列表语义由独立列表解释器验证，公开 `normalized.history` 始终为 null。

## 精确判断与证据

MoonBit 入口为 `normalize_list_capture_v3_json(text)`；统一 SDK 通过 `normalizeCaptureV3`、`analyzeV3`、`reduceV3`、`verifyV3` 的 dataModel 分派访问。核心内部分析入口为 `list_v3_analysis(text,options_text)`。

显式列表 SDK 提供 `normalizeListCaptureV3`、`analyzeListV3`、`reduceListV3`、`verifyListV3`、`makeListCapsuleV3` 和 `replayListCapsuleV3`。它们要求明确模型标识，保留原始 JSON 字符串交给核心校验；列表专用重放拒绝其他模型或无法声明列表模型的诊断胶囊。胶囊 `valid:true` 只表示报告能够重算，也可以对应 invalid 或 inconclusive，不能代替 `status` 与覆盖检查。

规范化算法为 `v3-list-lifecycle-1`，报告算法为 `v3-list-1`，模型定义为 `append-list-serializable-v1`。ready 表示事实覆盖足以分析，不表示符合模型。分析结果分别为 consistent、violation、inconclusive 或 invalid。

| evidence.kind | 内容与边界 |
| --- | --- |
| serial-list-replay | `serialOrder` 给出可独立重放的已提交事务顺序 |
| source-proven-list-anomaly | `findings` 给出读取序号、事务、键、身份和描述性错误码 |
| bounded-serial-exhaustion | 有界精确搜索完整结束且无串行执行，code 为 `no_serial_list_execution` |
| search-incomplete | 计算预算耗尽；不能把未完成搜索称为无解 |

`sourceEvidence` 保留真实身份、值、键、生产序号、生产事务及撤销序号。描述性 finding 包括 duplicate_list_item、item_key_mismatch、item_value_mismatch、read_from_aborted_append 与 read_from_reverted_append；它们尚未自动映射为 G2 或其他隔离级别分类。同一回滚效果可能同时具有 aborted 与 reverted 两条事实。

搜索按原事务顺序尝试候选前缀，完整重放每笔事务的 append/read/savepoint 日志。列表状态使用整数身份和可回滚追加日志；候选前缀不复制整张状态表。读取必须匹配完整长度和身份顺序。报告的 sampleBlockers 最多保存 16 条失败读取样本，它们不是完整搜索证明树；完整性由预算与可重算的精确搜索共同保证。

`verifyV3` 必须重算完整报告，不能只验证摘要、sampleBlockers 或用户提供的结论。摘要不认证输入真伪。来源被一致伪造的记录无法仅靠自包含报告辨别。

## 固定额度

| 项目 | 当前额度 |
| --- | ---: |
| SDK/CLI 输入 | 8 MiB UTF-8 |
| 直接 MoonBit 输入 | 8,388,608 UTF-16 code units，JSON 最大嵌套 64 |
| 原始事件 | 65,536 |
| 初始化键 | 10,000 |
| 初始与追加身份合计 | 10,000 |
| 原始 append 与 list_read 合计 | 10,000 |
| 所有读取的返回身份引用合计 | 100,000 |
| 生命周期事务 / 保存点深度 | 512 / 64 |
| 精确分析已提交事务 | 6 |
| 精确分析原始 append/read | 128 |
| maxStates | 默认及最大 100,000，可设为 0 |
| maxOperationChecks | 默认及最大 1,000,000，可设为 0 |

超出结构额度返回 invalid；超出精确分析容量或计算预算返回 inconclusive。完整来源反证无需枚举事务顺序，因此在覆盖完整时可先于精确容量限制成立。一次候选事务尝试消耗一个 state；每个模型/保存点动作及每个实际身份比较各消耗一个 operation check。额度恰好够完成最后一次比较时可以成功；尝试未完成则必须保留无法判定。

这些是项目额度，不是竞赛评分线或未经测量的性能承诺。当前没有列表模型的正式性能验收结果。

## SDK 接入验证

接入候选使用已有 v0.1.3 核心，通过 10 组独立检查及独立目录中的 92 项 SDK 回归；71 份冻结手工历史的结果逐字段匹配通用入口。检查覆盖原文传递、显式模型、UTF-8 入口预算、来源与未知结果、独立搜索/缩减预算和胶囊篡改。首版重放非法 JSON 通用诊断胶囊时的异常与原始快照保持，修复后同四份输入全部拒绝列表模型而不抛异常。

这些候选检查不是新 v0.1.4 的编译、数据库或公开安装结果；后续实际运行按[发行记录](development-status.md)单独保存。下列模型开发及数据库证据按各自原始构建记录保留。

## 模型开发验证记录

本地 `src/list_v3_wbtest.mbt` 含 88 项 MoonBit 边界测试：完整顺序、重复业务值、保存点回滚与同名隐藏、已交付读取、来源反证、来源缺口、未知提交、可靠 COMMIT 回滚响应、连接重用、输入篡改和预算精确边界。每例也核对原始观察完全保留、公开 history 为 null，并比较规范化入口与分析内规范化结果。第 88 项专门防止初始身份来源错误指向事件 0。

2026-10-21 首轮 focused JS：87 项中 86 通过，1 失败。原输出：

```text
test "list v3 23 committed reader of aborted append has source proof"
FAILED: 2 != 1
Total tests: 87, passed: 86, failed: 1.
```

失败来自本文件对应的**本地单元测试期望**只列了一条 aborted finding；生产结果同时保留明确的 aborted 与 reverted 事实。仅将本地测试改为逐项核对这两条已存在的来源证据，未改变生产判断，也未修改独立冻结 oracle。随后 focused JS 87/87 通过，构建成功。本记录保留首轮失败，不将重试写成首次通过。

该次构建 sourceSha256 为 `2bf27626d9a4bfd0220a6a9665540eefba17d8f7b55fedbd01261fe786388477`，coreSha256 为 `9b0be7d8e64c942c06a97cd39a1a0052c9da65b1715d86152e192049831756db`，captureCoreSha256 为 `ef53593d7565b297f74cef112d6ce6cabcbb9c0a9dc45ccc99b2ba537b8933d5`。它是供独立对照使用的开发快照；后续代码修改需要重新绑定构建。

## 独立核对与真实数据库

独立 Python 解释器先冻结 71 项手工边界及首批 10,000 输入。首批虽然逐条核对，但实际上只有 60 个不同输入，不能把这些重复数称为同等数量的结构覆盖。原输入和失败收据保留；随后追加[第二批 10,000 个不同输入](../fixtures/list-v3/extension-unique.json)，具有 7,555 种初始列表长度和事件程序形状。累计 20,071 份记录、10,118 个不同输入摘要。

首轮独立对照发现初始来源指向不存在的事件 0；33 项来源事实比较失败，同时旧缩减器未重排 COMMIT 响应引用。原[失败收据](../verification/list-v3/acceptance-2026-10-21T03-20-46-369Z/receipt.json)保持。修正生产代码及缩减引用后，[严格对照收据](../verification/list-v3/acceptance-2026-10-21T03-35-51-436Z/receipt.json)的 20,071 份判断、71 份完整作用域账本、8,352 个串行见证独立重放、31 种篡改、来源闭包缩减及 CLI 均通过，共 45 项检查、零差异。冻结期望没有依据生产结果重写。

六个[真实 PostgreSQL 场景](../experiments/list_v3/postgres.py)各执行 20 轮：重复业务值、RR 读后追加环、Serializable 回滚重试、合法自身读取后回滚、同名保存点及明确注入的 COMMIT 确认丢失。SQL 与实际返回结果分别保存，使用的 SQL 到列表映射只适用于该受控 fixture，不能称通用 SQL 采集。

[数据库收据](../verification/list-v3/postgres-2de835316d5f40d6b7e4bfeab4e4b8e4/database-receipt.json)记录实际 120/120 执行。首轮离线模型比较的一例遇到正在保存的解释器脚本，保留[119/120 的失败公开副本](../verification/list-v3/postgres-2de835316d5f40d6b7e4bfeab4e4b8e4/model-receipt.public.json)；其中私有路径已脱敏，原字节摘要与本地保留状态另列。随后冻结执行脚本字节，在[新的离线目录](../verification/list-v3/postgres-offline-recheck-20261021-0340/model-receipt.json)只读重核原数据库记录，120/120 分析、独立解释及复现通过，没有重跑数据库或覆盖失败结果。

这些通过结果绑定源码 `08cfa47947b2d31ea7ee5f5b2ebd626d399ee5bee06bceede0de0ca5dd23f4d9`、分析 core `bb2c807187ae7b447e323830de111e891bdb4ce30d3e78f249bbf93849ad1333`、采集 core `ba0589b63f6b669e1b3840ebb845b592d484241e5f2597d664a4d8f5a9847f21`。后续改动需要按新构建重新回归。正式性能、多目标最终检查、公开安装及版本发布各自记录；上述结果不代表其已经通过，也不代表赛事审核通过。
