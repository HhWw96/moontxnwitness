# 远程采集成本首轮记录与独立修复候选

冻结候选源码：bf28179a40aa2d1325f4f1484acb30362eea4f18。不是已经发布的 v0.2.4 性能成绩。

- column：https://github.com/HhWw96/moontxnwitness/actions/runs/39951311723 。实际启动 PostgreSQL 18.6，但仅首个 A 单元触发 100,000 尝试上限；协议成功单元 0/36。失败单元原始记录已封存；没有 B/C 比值。
- sidecar：https://github.com/HhWw96/moontxnwitness/actions/runs/39951325418 。离线测试竞态失败；数据库准备及测量均跳过，不能称为已测量。

`results-first/assessment-first.json` 分别记录实际执行、协议完成、目标达标，并绑定原始日志。两个原始 GitHub artifact ZIP 完整保留；ZIP 内含既有历史收据，不能把历史通过当成本次通过。本次实际 sidecar 离线日志另存 `results-first/sidecar/metadata/capture-persistence/unit-20261023T121057Z-ef4f3b6f/first.log`。

`duplicate-race-fix-v1/duplicate-flush-only.patch` 仅在原 duplicate 测试快照前加入公开 `sink.flush()`。FileExistsError 与字节相等断言均保留，生产 collector、harness、workflow 和预算不变。独立提交 8a6c5ddce17762363c7b27aaef134b56fc9cceb2，提交元信息与差异见 patch-commit.json。

独立受控调度保留原测试失败与修后通过（各 1 项），修后该 source-sink 文件 21 项通过；`evidence/receipt.json` 不是数据库或正式性能验收。为原样复测受控调度，请在新目录复制本包 `source/`、`duplicate-race-fix-v1/source/` 与 `reproduce_race.py`，不要复制既有 evidence/，再运行 `python -B duplicate-race-fix-v1/reproduce_race.py`。工具拒绝覆盖首轮 evidence。

`budget-readiness-v2-draft/` 是不可执行的容量草案。1M 尝试给当前 A 单 worker 约 8.59 倍 60 秒投射余量，但四/八连接线性容量压力已超出现有 source/lifecycle 条数上限；字节与长期磁盘容量仍待证明，warmup 还没有尝试计数上限。该草案不是下一轮正式协议。六项静态检查通过不代表容量足够。当前未重跑远程、未执行本机数据库或正式测量。

原始文件逐文件 SHA 在 handoff-manifest.json。ZIP 本身 SHA 在相邻 handoff-first-v1.receipt.json。无需凭据重放本地故障测试；本包不含 token。所有首失败均保留。
