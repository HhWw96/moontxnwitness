# MLflow 原生 HTTP 原始证据

`full30/` 为 Windows / Python3.12.5 / PostgreSQL18.6 的原始30对、60trial白名单字节副本。`ORIGINAL-FILES-MANIFEST.json` 逐项列原件角色、逻辑来源、字节数与SHA256；producer-source 为实际采集器快照，9runner为实际执行字节。

`independent-review.derived.json` 仅为已有独立报告的派生摘要，引用外部原报告SHA；它不签署本次新交付改动。`DELIVERY-STATUS.json` 是交付准备时的快照：16 个候选、48 次实际 trial 的缩减已完成并独审，同一最终 623 键请求的 fixed 三次实际回归也已完成；该三次新控制器的独立复核随后另存。`oneMinimal=false`。Linux HTTP、正式性能、生产、隔离模型完整性与正式发布不由此快照声称通过，最终状态另见 `verification/releases/0.3.0/`。

所有server原件及其seal/receipt绑定完整保留，只有PG原日志按公开允许的文件名复制为 `.original.txt`。数据库连接、口令、PGdata、temp、venv、wheels、巨型tar和原独审全文均未导出。目录中的stdout/stderr是实际运行时已保留的sanitized原件，本次没有再次改写。

复现与离线校验见 `docs/mlflow-http-case.md`。producer-source 是运行时来源快照，不是下一版当前采集器实现的自动替代。
