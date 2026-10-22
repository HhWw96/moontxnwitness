# 独特性与公开检索范围

## 历史检索与当前主张

以下公开索引检索记录止于2026-10-10，不是本版重新联网检索。

截至 2026-10-10，当轮在 Mooncakes 公开包文档、GitHub 公开索引及 MoonBit 官方生态相关结果中，以 MoonTxnWitness、MoonBit transaction history / serializability checker / Elle 等关键词检索，没有找到与本项目同范围的成熟 MoonBit 事务历史检查器。公开索引可能遗漏仓库、未发布代码和新提交，不能据此保证绝对首创，也不能保证获奖。

本项目的主张是：在 MoonBit 中提供可运行的“读写历史 → 确定性分析 → 事务缩减 → 核心判断回放”流程，逐条解释依据及信息缺口。图算法、串行搜索、缩减、哈希封装本身都有既有研究与实现，不主张全球算法首创。

## 已核对的相邻项目

| 项目及公开来源 | 公开介绍的范围 | 与本项目的边界 |
| --- | --- | --- |
| [Elle](https://github.com/jepsen-io/elle) | Clojure 事务一致性检查器，依赖与反例解释 | 理论和术语参考；生产核心独立实现，不依赖 Elle 运行时。源码保留固定参考原文与其许可，当前不是完整 Elle 替代品 |
| [EvoWitness](https://skills.mooncakes.io/docs/CJR-ai-nb/evowitness) | 两版本结构化契约兼容性、最小 JSON 反例 | “witness”目标不同；本项目输入是事务操作历史，判断的是串行执行是否存在 |
| [moonbit-notary](https://mooncakes.io/docs/hcjbat/moonbit-notary) | 文件证据交接、摘要与审计流程 | 哈希交接理念相邻；本项目的复核重算事务语义，哈希只是传输完整性检查 |
| [moonbit-community/postgres](https://assets.mooncakes.io/assets/moonbit-community/postgres%400.0.8/client/transactions.mbt.html) | 数据库客户端事务与隔离选项 | 提交/回滚事务不等于分析一份历史的可串行化性 |

这些比较依据公开 README/包文档，不是对各项目全部代码或未来版本的穷尽审计。EvoWitness 的 Mooncakes 页面可读取；其页面所列 GitHub 仓库本次访问返回 404，因此没有把那个仓库当作已检查源码。

## 已落地的区别，可现场复现

1. **不完整顺序的诚实补全。** 小型完整日志缺少写入顺序时寻找实际可重放的整个事务序列；明确 searched 是一个可能执行。穷举无解与预算耗尽分开。
2. **没有环也能给出并复现确定异常。** fractured-observation.json 的原始必要依赖图无环，但混合读取两个原子写者的版本无法串行执行；复现包会重新计算这个结论。
3. **缩减不增加输入事实。** noisy-write-skew.json 的 7 个事务缩成 2 个；只裁剪原本声明的顺序，不把搜索结果当作采集约束。oneMinimal 仅在最后单删检查完成后为 true。
4. **同一日志的模型差分。** strict-realtime.json 定位“普通模型可行，加入共同观察时钟约束后异常”，完整导出两种报告及实时边。
5. **可携带的核心判断。** 自包含包存储日志、报告、摘要和版本，支持正常、直接异常、环及完整搜索无解；拒绝与重算语义矛盾的结论，即使内容哈希被重新计算。
6. **真实并发采集与来源解释。** 两线程 SQLite WAL 示例实际记录提交、回滚、重试；事务内审计表提供版本顺序。报告区分 asserted / single-writer / searched / missing，逐键说明读写覆盖。

运行 `node dist/demo.mjs` 可演示前五项。实际采集、环境及验证记录见 [SQLite 说明](sqlite-capture.md)、[开发复现](development.md) 和 `verification/`。SCC 定位用于缩小最短环搜索范围，不包装成未经证实的总性能提升。

## 当前仍有限制

当前还提供固定键普通表、固定 SQL 模板与局部来源诊断、有界列表和关系事实、已选中环解读及独立执行包，见[稳定支持矩阵](stable-scope.md)。关系支持受限 AND 谓词的完整结果事实，不能泛称任意 SQL 范围查询。图、搜索、缩减、字节与来源均有明确预算；全自动 SQL、完整 ORM、全部隔离分类及大型生产负载保证继续后续研究。公开下载和 Mooncakes 安装核验以对应 `verification/releases/VERSION/` 实际收据为准；技术发布不代表比赛提交、组织方接受或绝对首创。
