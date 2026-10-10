# MoonTxnWitness v0.0.1

发现确定的事务一致性异常
模型：serializable
事务：2；已提交：2；操作：4；依赖：2

## 异常环证据

1. T1 → T2 [rw，x]
   The reader observes an earlier version and must precede this later committed write.
   操作下标 0 → 1，版本 x0 → x1
2. T2 → T1 [rw，y]
   The reader observes an earlier version and must precede this later committed write.
   操作下标 0 → 1，版本 y0 → y1

证据包含构建图中事务数量最少的有向环；不声称整份历史已被全局最小化。

## 发现与缺失信息

- [violation] dependency_cycle: The dependency cycle prevents any serial order satisfying these observations and constraints；事务=T1, T2

范围：唯一版本标记的单键读写，可跨多个键组成事务。结果取决于所提供历史的完整性及版本顺序约束，不能直接证明整个数据库可靠。
