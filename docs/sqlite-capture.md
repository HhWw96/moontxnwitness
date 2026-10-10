# 实际并发采集示例

需要 Python 3.11 或更新版本的标准库 `sqlite3`。运行在新建的本地临时数据库，不使用用户的现有数据库，也不上传数据。

```powershell
python examples/capture_sqlite_concurrent.py race.json --rounds 3
node dist/moontxnwitness.mjs check race.json --format json --capsule race.capsule.json
node dist/moontxnwitness.mjs compare-models race.json
node dist/moontxnwitness.mjs replay race.capsule.json
```

采集器建立 WAL 数据库，启动两个线程、两个连接。两者在一个同步点前完成读取，再竞争修改不同键。失败的事务记录为 `aborted`；重试使用新事务 ID、新写入版本，并重新读取当前版本。实际 SQLite 返回的 BUSY/LOCKED 错误名称保留在标准错误中的采集说明，标准输出/历史文件仍符合历史 Schema。

只记录成功完成的 SELECT 和 UPDATE。提交后的版本顺序从**同一数据库事务内写入的 audit 表**按序查询；不用线程返回次序或时间戳猜测。采集结束时核对 audit 与已提交写入集合一致，并确认每个键最后一个版本等于数据库实际最终值。

开始/结束来自同一进程的单调时钟。初始状态在启动工作线程前写入。线程调度、谁先成功和时间值会变化，所以不要求日志字节相同；要求实际采集证据与当前读写模型兼容。SQLite 的隔离和 WAL 说明见 [官方隔离文档](https://www.sqlite.org/isolation.html) 和 [WAL 文档](https://www.sqlite.org/wal.html)。

`verification/cli.json` 记录三次实际采集的元数据，`verification/sqlite-concurrent.json` 保存其中一次历史，配套报告保存在 `verification/sqlite-concurrent-report.json`。

这个例子展示“采集 → 版本审计 → 检查 → 复现”的真实链路，不是 SQLite 漏洞演示、通用 SQL 自动插桩，也不保证全部 SQLite 运行符合所有模型。合成异常日志仍单独标注为 Synthetic。
