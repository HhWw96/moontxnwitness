# v3 开发契约

起点：`6f3724582dc027be2d98aaa08960b8d520b425f7`。本文件冻结首个开发切片的线格式，不表示 v0.2.0 已验收。旧 v1/v2 API、预算与复现规则保持原样。

## 观察日志

根对象为 `{traceSchema:3,clockDomain,scope:{exclusiveWriters},events,gaps}`。`gaps` 是 `{code,message}` 数组。事件具有正安全整数 `seq`、非负安全整数 `time`、`kind`；序号从 1 连续，时间在时钟域中单调不减。序号和客户端时间不表示数据库提交顺序。

可选 `dataModel` 为 `point-register-v1`（缺省）或独立的 [append-list-v1](list-v3.md)。不支持混合模型事务。可选 `sqlProfiles` 最多 16 个，用于保留受控安装、初始来源和实际写入账本；它不因自报 `verified` 或给出摘要就获得完整覆盖。

| kind | 额外字段 | 含义 |
| --- | --- | --- |
| snapshot | initial、consistent | 一致起点，每键对应唯一版本身份 |
| begin | tx、connection | 新事务身份；重连和重试不能复用身份 |
| read | tx、key、version | 业务实际收到的寄存器读取 |
| write | tx、key、version、predecessor | 已确认写效果；前驱是来源事实，不是 SELECT |
| condition | tx、predicate、matched、sourceVersion（可选） | 条件判断事实；独立于读取，来源不足保持缺口 |
| statement | tx、sql、parameters（可选） | 原始 SQL 观察 |
| rows | tx、statement、rows、complete | 实际交付结果；statement 引用事件序号 |
| savepoint | tx、name、instance | 名称可重用，每次创建的实例身份不可重用 |
| rollback_to | tx、instance | 恢复该保存点的写状态，保留读取，删除后代作用域 |
| release | tx、instance | 释放该作用域及后代；没有提交事务 |
| commit_request | tx | 仅记录请求 |
| commit_ok | tx | 对应请求的成功确认 |
| rollback_ok | tx | 请求提交前的回滚确认；提交结果未知时不能据此推断回滚 |
| disconnect | tx | 连接终止，未确认的结果保留 unknown |

`read` / `write` 是有明确模型含义的事实入口，不是对任意 SQL 的猜测转换。首个切片对 condition 只验证、保留与报告，不声称已经证明其数据库条件语义。

## 不可变观察与效果日志

观察保持原样。规范化分别输出 observations、effects、transactions、coverage 和可安全投射的 history。效果带有原始 seq、来源和撤销事件；保存点回滚不会删除已交付的读取。事务最终写只取每键最后一个未撤销效果。

首版生命周期算法标识为 `v3-lifecycle-1`。安全寄存器投射不带客户端实时顺序。合法自身读先按作用域日志核验，再从外部可见的串行重放中消去。外部读取撤销效果、中间来源或来源不明，条件语义未证明，以及未确认提交均使完整性为 false，不能输出完整模型结论。

新增可靠 COMMIT 回滚回应使用 `rollback_ok.commitResponse`，使该日志采用 `v3-lifecycle-2`，旧日志继续采用原标识及规则。回应须引用同笔事务的 `commit_request` 序号，并且为实际 `commandTag:"ROLLBACK"`，或 `sqlstate` 与 `diagnosticSqlstate` 同为 `40001`/`40P01` 且 `transactionStatus:"IDLE"`。采集器还要求错误来自真正的驱动服务器响应；客户端构造的错误或随后的空闲 ROLLBACK 均不能证明未知提交已经中止。40P01 只表示执行死锁，不映射为 G2。

SQL 传输可保留 `statement.mappingId/executedSql`、`rows.serverRows/columns/error`；列描述使用 `{name,typeCode}`。映射事实附带 `statement/mappingId/evidence`，必须引用同笔事务的更早语句。业务已交付列与隐藏来源列分开保存。语句、参数、结果和安装来源尚未完整核对时保持覆盖缺口；传输绑定本身不是 SQL 语义证明。

SDK / CLI 上限：8 MiB UTF-8 输入、65,536 事件、512 事务、10,000 次读写、64 层保存点；超出主机字节额度拒绝执行。MoonBit 字符串入口另按 UTF-16 code units、深度及节点数限制解析。精确寄存器搜索继续采用已验证的 12 事务上限；新数据模型的额度单独验收。

## 分析、缩减与证据

新入口 `normalizeCaptureV3`、`analyzeV3`、`reduceV3`、`verifyV3` 与旧入口分开。v3 分析报告记录版本化模型定义、规范化结果、判断证据及实际预算和运行计数。覆盖不足不等同于符合模型。

v3 缩减删除整笔事务、重新编号并记录原始序号映射，每次候选重新规范化及分析。来源被删除后无完整证明的候选不能保留；声明 oneMinimal 必须检查最终每笔事务的单删候选。首版谓词是“确定的可串行化反证”，不能用隔离异常谓词缩减执行死锁。

所有保留的 SQL 事实与 rows 的 `statement` 引用，以及 `commitResponse.request` 均按相同序号映射更新；不把搜索补全或来源账本查询伪装为业务读取。

复现包 format 为 `moontxnwitness-replay/v3`，绑定原始记录文本、规范化结果文本、完整报告文本及判断证据文本的 SHA-256。验证重新执行规范化、分析和证据比较；摘要校验不能代替语义校验。自包含摘要不认证数据来源或作者身份。

## 持久化

独立 Python v3 分段日志默认队列 4 MiB、段 16 MiB；256 KiB 或 100 ms 同步，关闭同步尾部。磁盘索引绑定每段摘要、长度、序号和条数。流式读取先验证完整性；崩溃、写入失败、缺段或序号缺失产生缺口。尚未证明来源闭包时拒绝清理被引用记录。

## 验收状态

至少 24 个生命周期与 24 个篡改案例，由独立实现对照。未执行的真实数据库、完整业务生命周期、吞吐成本、多模型及最终发布关卡保持未完成；不得从本契约推导已经通过。

保存点规则依据 PostgreSQL 18 的 [ROLLBACK TO](https://www.postgresql.org/docs/18/sql-rollback-to.html)、[SAVEPOINT](https://www.postgresql.org/docs/18/sql-savepoint.html) 与 [RELEASE](https://www.postgresql.org/docs/18/sql-release-savepoint.html)。
