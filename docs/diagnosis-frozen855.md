# 冻结历史的补充诊断

原2,000份共同范围对照保持1,142份可比较一致、0份可比较差异、858份未比较；其中寄存器855份原串行分析无法判定。新版诊断对这855份生成测试历史另行执行并验证，独立复核又逐份重跑诊断和验证，报告及验证结果均逐字节一致。

855份均有INT直接证据：433份读到的版本不符合当前自身写，422份在没有中间自身写时重复外部读取发生版本变化。此处INT表示事务内部读取不一致，不等同于G2。Generalized SI定义由INT反证；其余五模型及原串行分析仍全部无法判定，没有把缺口改成完成。

输入事实、旧比较口径和旧报告未改。本补充没有运行数据库或新的Elle，不作为新业务接入或生产案例，也不是性能测量。输入来自公开冻结测试数据集，SHA256为 4b7ef85eb4a2f4a74020d6e6c65f5345f7c4c3b576afbe02b3f7a0cfc6033507。

公开摘要及独立原始复核见 verification/releases/0.2.8/development/frozen855-diagnosis-summary.json 与 frozen855-diagnosis-independent.original.json。完整输入、实际运行时、原始报告及重跑证据封存在发行附件 MoonTxnWitness-v0.2.8-frozen855-diagnosis-evidence.zip；以公开下载核验记录确认附件交付状态。
