# v0.2.8 技术证据冻结

本次冻结绑定已完成原始 push CI 的源码提交 `27896a39f6c9df9963c0e2bfcb7d398fa8778eb5`：通用构建 `40329768202`、PostgreSQL `40329768118`，均为 attempt 1。冻结只更新文档、验证证据和本机发布运行时；可执行源码及固定输入保持原字节。

当前运行时、顶层 summary、PostgreSQL 执行前后 manifest 与 2,090 个执行文件摘要统一采用 Linux 原件。212 个 dist 文件与已完成独立 SDK 重放的数据库 CI 原件逐字节相同。Windows 的完整回归、126 项消费者验证及原始运行时另行备份并作为历史平台证据保留，没有改写为 Linux 执行。

技术声明见 `verification/releases/0.2.8/acceptance.json`；`passed` 和 `releaseReady` 仅表示同代码技术证据完成。`finalPackage`、`finalExactSourceCI`、`publicDownload` 均仍为 pending，`publicReleaseVerified` 为 false。冻结后新增和修正的元数据尚未进入最终 ZIP，也没有新的精确冻结提交 CI。

当前数据库证据见 `database.json`：20 轮 × 2 隔离场景、20 个实际 40001 回滚和新重试身份、6 个 presence 场景及 4 个初始化控制、10 个配置模型（7 个可分析、3 个 inconclusive）、列表 120 与关系 160 个原始案例。旧 `857ba52` 的 ci-originals 和 hosted 目录保留。拷贝证据没有启动新的数据库。

独立复核见 `freeze/independent-evidence.derived.json`、`freeze/sdk-replays.derived.json` 和两个新的 ci-originals 目录。公开文件明确标为派生摘要，列出未修改外部原件的字节数和 SHA256；含本机绝对路径的原始复核报告保留在项目外。原始工作流 ZIP 日志与所选原始步骤文本另行保留。

Linux 原始 summary 的六个临时 artifacts 引用没有原始子目录/receipt 留存在下载产物中，详见 `freeze/evidence-reference-index.json`。五项为辅助输出目录，一项为 18 项 driver 测试 receipt；其执行结论由精确源码的失败即退出控制流、原始 summary 和成功父步骤支持。没有伪造直接子日志，也没有用另一运行代替。116 项持久化测试的原始日志有独立 SHA 绑定，并提供 `.txt` 原字节公开副本；原 receipt 不改。

性能与 855 诊断证据继续使用各自实际运行记录，见 `freeze/development-evidence-bindings.json`、`performance-v0.2.8-relation.md` 和 `diagnosis-frozen855.md`。关系固定工作负载约 1.124× 的结果不扩写成整个 v0.2.8 的统一性能成绩。855 个生成历史仍全部保留原串行 inconclusive，仅额外报告 855 个直接 INT 证据；Windows 原始诊断运行时不冒充新 Linux 855 次执行。

后续必须完成：维护者独立复核冻结变更；重新运行现有打包器生成最终 source/portable、原始消费者回执和 SHA256SUMS；提交最终文档及证据后取得该新提交的通用与 PostgreSQL 原始 push CI；再进行公开发布与独立下载摘要、CRC 和运行核验。当前 artifacts 目录内旧包不代表最终冻结产物。参与者说明、人工验收与主办方状态另行确认。

## Post-freeze CI recording correction

This document retains the original freeze snapshot above. Final push [40364775509](https://github.com/HhWw96/moontxnwitness/actions/runs/40364775509) stopped before database execution because the historical runtime receipt already existed. The workflow now writes each before/after pair in a fresh run/attempt directory, keeps exclusive creation, and uploads only that current pair. Historical records remain unchanged. All 23 extracted-workflow simulation checks passed; this is separate from real PostgreSQL execution. Final archives and exact-commit CI must be completed again after this correction. See `verification/releases/0.2.8/freeze/final-ci-first-failure/` for the original failure and derived correction record.
