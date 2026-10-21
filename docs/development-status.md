# v0.1.1 / v0.1.2 开发状态

记录日期：2026 年 10 月 21 日。当前包仍为 v0.1.1 开发版；公开稳定版本为 v0.1.0。普通表 CRUD 使用独立实验入口，尚未作为 v0.1.2 稳定接口发布。实现、公开发布、人工验收及赛事审核分别记录。

## v3 共同底座的首批实现

### 第二批：列表、业务采集与显式 SQL 来源证明

第二批已验 MoonBit 源码指纹为 `f33c8675a69a0681bb7865e32f2ace5aed21b03fb2d03dc16265dee2dbe6d57b`。本地 [完整回归](../verification/summary.json)已通过 JS、Wasm GC、Wasm **各 398 项**核心测试，保留原 10,320 份独立串行历史、6,373 份环证据、2,542 份解析差分及原 CLI 验证。Linux Native 和公开下载核验须以这一批新的 CI 与独立收据为准，不能借用旧 187 项成绩。

[追加列表](list-v3.md)新增 88 项核心边界，独立解释器核对 20,071 份冻结历史无差异并重放 8,352 个串行见证。记录含 **10,118 个不同输入**；原批覆盖重复偏多的记录保留，新批具有 7,555 种程序形状。六个真实 PostgreSQL 场景各 20 轮的原始 SQL、数据库结果与成功的离线核对均保留；原第一次核对在并行写入解释器时发生一案语法错误，公开脱敏副本绑定原失败字节，后续只读核对使用冻结解释器，没有改动真实历史。

[dislock 全生命周期](dislock-v3.md)已实际执行主连接、心跳、退出清理、busy、owner 变更、业务异常及真实断连重连。最终 [数据库收据](../verification/business/dislock/v3-db5f87c5620c4f8e955172340023482c/database-receipt.json)与 [模型收据](../verification/business/dislock/v3-db5f87c5620c4f8e955172340023482c/model-receipt.json)各通过七案。新增 [明确 COMMIT 失败](../verification/business/dislock/v3-commit-fb56573a35ef415b872509cf1004ee90/commit-receipt.json)实测：真实提交阶段 `40001` 及事务状态支持服务器中止确认，原异常身份保持，随后 idle rollback 不添加伪造事务；提交应答丢失仍为 unknown。

固定 SQL 经过结构、返回列、条件、OLD/NEW 来源、实际效果账本和安装目录核验后，可显式选择 `sqlProof:"dislock-f9946f0-sql-proof-1"`。默认入口保留原有保守行为。七案显式结果为 **3 consistent / 4 inconclusive**；零行条件缺来源、未知事务和未映射失败语句保持缺口。独立 SQL 诊断 86 项、显式策略 199 项检查通过，包含旧复现包、36 项报告/包篡改和来源闭包缩减。合成缩减样本只删除噪声事务，保留异常依赖的来源事务；该样本不冒充真实数据库排障。

同步 v3 采集器使用磁盘分段日志，不持续保留 `_events`。35 项协议测试通过；64 项日志测试本地 62 项通过、2 项因符号链接权限跳过，独立存储 10 项及关闭后继续使用连接的 42 项检查通过。独立审计发现的关闭后漏记和 `snapshot.consistent=false` 覆盖错误均先保留失败，再修复重测。

这些结果仍是开发切片。来源闭包窗口、安全保留/清理、完整采集 C/A 成本、ORM 来源证明、关系模型、六模型与 Elle、真实 MLflow 故障闭环及最终性能尚未验收。v0.1.1 / v0.1.2 联合发布门槛保持未完成；独立 AI 技术验收与真人使用、生产采用及赛事审核分开记录。

第二批公开源码 `bb87f93` 的 PostgreSQL CI 首次成功；核心 CI 两平台首次均因缺少可选 psycopg 而在两项固定 SQL 组合测试失败。此前各 398 项三目标和旧 oracle/CLI 已执行通过，Native、打包与独立公开消费者尚未执行，不能借本地成绩补勾。见[独立首失败诊断](../verification/v3/independent-public-checkpoint-bb87f93-first-failure-2026-10-21.json)。修复是在核心 CI 安装原有 SHA 冻结驱动，保留原断言和失败运行，使用新提交重新验收。

以下首批 187 项和 CI 收据仅属于 `16ba355` 的历史公开底座。

### 首批公开底座收据

已从 `6f37245` 按[剩余执行计划](remaining-execution-plan.md)开发；当前切片契约见 [v3](v3-contract.md)。新增独立 `normalizeCaptureV3` / `analyzeV3` / `reduceV3` / `verifyV3`、对应 CLI 及 v3 复现包。MoonBit 区分不可变观察和可撤销写效果；同名保存点按实例处理，未知 COMMIT 不当作回滚，条件写和未映射 SQL 保持覆盖缺口。

首批公开下载收据记录其当时本地 JS、Wasm GC、Wasm **各 187 项**核心测试，以及原有 10,320 份历史、6,373 份环证据和 2,542 份解析差分。新增独立解释器 57 条轨迹及 SDK/CLI/证据 167 项检查；其中注册篡改变体 32 种。磁盘日志本地 55 项测试中 54 通过，因账户无法创建符号链接跳过 1 项；独立存储故障审计 10 项通过。

源码 [16ba355](https://github.com/HhWw96/moontxnwitness/commit/16ba3552f08d134f55795e6d95286c1d43a374ad) 的 [Windows/Linux 核心 CI](https://github.com/HhWw96/moontxnwitness/actions/runs/39534758059)与 [PostgreSQL CI](https://github.com/HhWw96/moontxnwitness/actions/runs/39534758057)均在首次运行通过。两平台各三目标 187 项，Linux Native 也为 187 项；CI 磁盘测试两平台均 55 项通过、无跳过。[独立 AI 公开下载验收](../verification/v3/independent-public-checkpoint-16ba355-2026-10-21T02-50-23.105113Z.json)核对 3 份实际 artifact 的 GitHub 摘要、两平台各 191 项源码绑定及真正下载的 core/capture/manifest/wrapper；在独立新目录用两个平台的下载运行文件完成 66 项检查，未借作者 dist/cache，也没有重新执行数据库或正式性能测量。此 CI 已上传实际编译 core，补齐前一实现只能核对运行时摘要的限制。

分段日志使用默认 4 MiB 队列、16 MiB 段、256 KiB 或 100 ms 同步、SQLite 磁盘事务索引及流式验证；4,100 个已完成事务的历史身份不会持续保留在内存集合中。独立审计实际发现并修复双重 IO 失败后误判完整、WAL 归档缺失和读取期间重开竞态。原失败、原 52 例冻结清单与参考解释器时态修正说明均保留在 [v3 证据目录](../verification/v3/)及 [修正记录](../fixtures/v3/protocol-correction-1.json)。

[PostgreSQL 18.6 的六个实际场景](../verification/v3/postgres-7b441738d1a545f4b8aefc0b9a421c5a/database-receipt.json)核对回滚前后自身读、释放子保存点后父回滚、重复名称恢复、重复回滚及游标位置；六份原始日志的 [MoonBit 核对及复现](../verification/v3/postgres-7b441738d1a545f4b8aefc0b9a421c5a/model-receipt.json)通过。原始 SQL 尚无映射证明，六份报告都保留 `unmapped_statement`，没有声称完整 SQL 分析。

这是共同底座的首批切片。旧驱动仍需迁到新存储；来源闭包窗口选择、安全清理、完整 dislock、ORM、多模型、最终性能和发布验收尚未完成。`prune` 保守拒绝删除全部来源，不能称来源 GC 已实现。技术验证按独立 AI 验收记录，真人反馈、生产采用及赛事审核仍分别记录。

## 已验收的前一实现基线

| 工作 | 当前证据 | 状态 |
| --- | --- | --- |
| 同步、异步 psycopg 采集 | 62 项驱动接口单元测试；一致快照、真实 fetch、提交/回滚、日志及聚合预算 | 已实现，本地通过 |
| MoonBit 跨目标回归 | JS / Wasm GC / Wasm / Linux Native 各 153 项；独立历史 10,320 份、环证据 6,373 份、解析差分 2,542 份 | 本地与独立 Windows / Linux CI 通过 |
| SDK / CLI | 原 75 项检查、14 项采集检查、新增 26 项 presence 检查 | 本地通过；失败或覆盖缺口不导出历史 |
| 稳定采集实测 | 7 个真实 PostgreSQL 场景、4 份复现包，异常缩至 2 事务 | 本地通过 |
| 原有数据库流程 | RR 及 Serializable 各 20 轮，3 份复现包 | 本地通过 |
| 既存行 SQL profile | 4 个场景、11 项拒绝、2 份复现包 | 实验，本地通过 |
| 冻结 dislock 业务切片 | 原 MIT 续约函数、7 个场景、4 份复现包，含真实 RC 锁等待后的 OLD 来源 | 本地通过；全应用采用未完成 |
| 普通表 CRUD / 负读 / 墓碑 | 6 个场景、10 项安装拒绝、8 项篡改检查、3 份复现包，写偏斜缩至 2 事务且单最小 | 实验，本地及独立审计通过 |
| 实验 Python 接口 | 22 项旧 profile、16 项 RETURNING、11 项冻结业务、22 项 presence | 本地通过；不是数据库执行次数 |
| 证据发布字节 | 2 份 dislock 收据与 1 份 presence 收据，共 84 项文件绑定 | 工作树、Git HEAD 与公开源码 ZIP 均逐字节核对通过 |
| 测试回执及打包 | 测试前后绑定可执行源码、JS / Python 包装层及运行文件摘要；旧回执打包被实际拒绝 | 已修复，完整回归通过 |
| 文件保存可靠性 | 9 项真实文件故障测试；原子替换、读回摘要、有界文件重试 | 通过；不重试计算来规避失败 |
| 同版本完整输出 | 20 / 20 份完整报告逐字节一致；15 份内部阶段编码中 8 份字节一致、7 份逻辑值一致 | 严格 35 项结果仍为 28 / 35，保留失败及独立解释 |
| 性能 | 新实现完成 20 个完整负载、15 个阶段、6,300 样本及 38 快照独立审计 | 20 / 20 原 P95 回退门槛通过；后续更高目标未全部达到 |
| 公开源码核对 | e6d57a1 的源码 ZIP：44 个 MoonBit 文件指纹、121 项测试源码摘要、84 项证据绑定 | 独立下载核验通过，8 项运行时摘要不冒充源码 ZIP 内编译文件 |
| 新实现独立 CI | e6d57a1 的两工作流、三任务及三份 artifact；各平台 121 项源码绑定、9 项文件故障、60 项消费者及真实 PostgreSQL 全链路 | 已下载摘要、日志及完整证据，逐项核验通过 |
| GitHub / Mooncakes 新稳定版 | 须完成适用发布门槛 | 尚未发布 |

前一实现的 MoonBit 源码指纹为 `c00c514defb7f551aae417245c5f6642284874cbdaf1a0fe77e717a433265bb1`，分析 core 为 `a8b94cd9e8db7a643523e7cd201ff5bce65b4382d25e41892cb6e431eebca3c3`，采集 core 为 `33c14cf537fb454e2177eaa17c4f7467c4c28316b9de04e1e8d4c9c665e57506`。本轮运行文件以新 summary 的逐路径摘要为准，不借用旧源码的 CI 或正式性能成绩。

## 普通表实验的完整证据

[最终 PostgreSQL 收据](../verification/provenance-presence/run-6089a462bdbd43e9ab80edc94b481c61/presence-receipt.json)包含实际 SQL、服务器结果、事务结局、审计来源、覆盖报告、历史、分析、缩减和复现包。它的 [独立审计](../verification/provenance-presence/run-6089a462bdbd43e9ab80edc94b481c61/independent-audit.json)重算 30 项文件绑定与 11 项源码绑定，并核对投射操作、回滚、数据库审计链及版本顺序；该审计本身没有重跑数据库。其他四套流程连同 presence 共 16 份复现包独立重放通过。

此能力仅支持固定已知文本键、规定的单表点读写模板、同步 tuple 游标以及受控安装窗口。不存在键也必须在初始键域内。存在性是单独采集的事实；版本前驱不是业务读取，身份 UUID 不是提交顺序。`normalizePresenceCapture` / `ingest-presence` 使用 traceSchema 2，旧入口继续拒绝它。详见 [实验契约及运行方式](../experiments/provenance/PRESENCE_PROFILE.md)。

## 性能及兼容性

固定公开 v0.1.0、同工具链、同输入、同完整输出。每场景 5 次预热、30 次样本、3 批独立进程，原 P95 门槛保持。上一实现的第六轮完整测量中，512 事务缩减 P95 已改善，但 sparse-512 与 small-cycle-noise-64 超限，因此整体失败。各轮原始结果及不可覆盖快照保留于 [性能诊断记录](../verification/releases/0.1.1/performance-v010-diagnosis.md)，不拼接通过项。

当前第七轮通过全部 20 个共同负载门槛，独立核对 120 份完整输出及 38 个快照；[完整审计](../verification/releases/0.1.1/performance-v010-formal-2026-10-20T15-55-43-611Z-persistence-audit.json)对应本页的 c00c… 源码。图组几何平均提速 1.236 倍、峰值 RSS 比 0.914；大型搜索组提速 1.329 倍，大型缩减组 1.515 倍。后续图组 1.3 倍 / RSS 0.8、搜索 1.5 倍及完整采集成本目标并未全部完成。

新实现的 20 份完整报告字节全部一致。7 份内部阶段对象的编码差异来自随机种子的 Map 桶布局；相同旧 core 的两个独立模块实例也能出现该差异。逐 key/value、插入顺序及其他字段核对一致，但严格字节失败记录没有改写，见 [单独评估](../verification/releases/0.1.1/common-paths-compatibility-assessment-2026-10-20T15-31-08-087Z.json)。内部对象编码不是公开报告契约，正式测量继续核对全部完整报告。

## 尚未完成的门槛

v0.1.1 / v0.1.2 已有七项真实 dislock 生命周期和六条固定 SQL 来源证明，仍欠完整采集 C/A 成本、来源闭包窗口/保留、每项目 30 个预登记并发种子及正式联合发布。零行条件等未证明路径继续无法判定，不能称完整业务已全部覆盖。

v0.1.2 仍欠完整采集 C/A 成本、并发锁/死锁与保留成本及更广业务验收。先前两种来源方案的 9,000 笔单客户端实测均有吞吐/延迟回退，不能只用 B/A 来源成本宣布完整采集达标。列表和 v3 保存点已有实验实现及独立证据；SQLAlchemy 来源证明、关系谓词、六类模型反证及 Elle 对照继续按 [执行计划](remaining-execution-plan.md)推进，不列为稳定支持能力。

[上一实现的独立 CI 收据](../verification/releases/0.1.1/independent-ci-f76aebf.json)对应 f76aebf 的源码 4f1a5135…及 134 项核心测试。CI 未上传编译 core 原始字节，因此其中 core 摘要是运行时记录，不声称下载复算了二进制。其公共 GitHub 源码 ZIP 与 Windows 原始 27 项业务绑定已另行逐字节核验。

新实现的 [公开源码字节审计](../verification/releases/0.1.1/capture-public-bindings-e6d57a1.json)直接读取固定提交的 GitHub ZIP，全部 121 项非 dist 测试文件摘要与源码字节一致；84 项原始采集绑定也全部匹配。旧收据仍按各自执行时的构建摘要记录，不被改写为当前构建。3 份 presence capsule 使用匹配本地运行文件离线重放有效，该步骤没有重新执行数据库。

源码 e6d57a1 的 [核心 CI](https://github.com/HhWw96/moontxnwitness/actions/runs/39452756585)及 [PostgreSQL CI](https://github.com/HhWw96/moontxnwitness/actions/runs/39452756244)均通过。[新独立 CI 审计](../verification/releases/0.1.1/independent-ci-e6d57a1.json)核对三份下载产物的 GitHub 摘要、双平台测试与源码绑定、Linux Native，以及数据库的 22 项来源绑定、70 项当前产物绑定和 16 份复现包内部摘要/历史/报告。CI 未上传编译 core 字节的限制仍保留。后续文档及证据提交不改变这份已验实现的可执行源码摘要。

参赛者人工安装与解释验收尚未记录，组织方审核未重新提交；自动验证及公开仓库不代表官方通过或获奖。所有公开场景为受控测试数据，真实应用采集记录发布前仍需审查。
