# 实验容量候选交接（尚未正式测量）

冻结源码：`b341ee4e5b10f7a852d4278746ce63dca96fce8d`。以 bf281 采集性能源码及另行审核的一行 flush 测试屏障为底座，未改主发布工作区。

只有显式选择 `full-capture-cost-capacity/v2` 才使用新有限额度：来源 2 GiB／600 万条，生命周期 6 GiB／1600 万条，journal 4 GiB，SQLite 1 GiB 写前页面限制，attempt 日志 1 GiB。每个 cell 仍使用一组共享 observer，15／60／30 秒、种子与业务请求保持。旧默认及旧 wire 保留；旧 journal 合法自定义 totalBytes 继续按原规则。实验存储不扩展 8 MiB 诊断／分析入口。

新计划按真实卷可用字节检查原始日志、最坏 ZIP、验证临时 SQLite、数据库／WAL及保留余量；已完成 ZIP 计入实际占用。估算不保证完成 36 单元。预算耗尽、存储失败或验证失败保持失败／不可达标。数据库／WAL保护为采样限制，SQLite 页面限制为写前保护。

作者最后检查：116 项，115 通过、1 项因本机不允许符号链接而跳过，0 失败、0 错误；没有真实数据库、没有正式性能测量。最终所有 Python SHA 与检查收据匹配。默认 plan 与首轮 hosted bf281 plan 逐字节相同。两个新 profile 仅执行 plan-only。

首轮新增套件曾有 1 个 KeyError：plan 的固定预算算术受测试中的磁盘 mock 影响。首错源码 0d1e697d、原日志和收据均保留；修正为纯 required_free() 后原 114 项断言通过，再新增 2 个 scratch 故障案例成为 116 项。没有修改原断言消除差异。

`FINAL-MANIFEST.json` 提供完整源码、首错与最终收据 SHA。完整运行命令：`python -B scripts/persistence-unit-test.py`。仅需 Python 标准库。请在全新 D 目录恢复固定 Git 对象，设置 D 盘 TEMP／TMP、MTW_JOURNAL_TEST_ROOT 及已建立的 MTW_JOURNAL_SCRATCH；清除 MTW_PG_DSN／MTW_PG_CONNECTION_FILE，避免借用数据库配置。不得将作者结果当作独立验收。

两次原正式实验失败另见上一层 `handoff-first-v1.zip`，均未重跑、未替换。当前未创建大包，避免占用低余量 D 盘。下一步是独立验收、下一版集成后的适用回归和新来源绑定的远程正式测量；当前不宣称采集成本或性能目标达标。
