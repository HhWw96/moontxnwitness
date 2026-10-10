# 从日志到可携带的反例

## 缩减日志

```powershell
node dist/moontxnwitness.mjs shrink examples/noisy-write-skew.json --output reduction.json --history mini.json
node dist/moontxnwitness.mjs check mini.json --format markdown
```

`shrink` 按块删除事务，再尝试逐个删除。每次只有分析器仍给出确定 `violation` 才接受候选。它保留初始状态、事务内部操作和时间，按删除的事务裁剪原本声明的写入顺序。搜索得到的“可能版本顺序”不会被变成输入事实。

`oneMinimal: true` 表示：再删任意一个剩余事务，都不能在当前分析器下保留确定异常。它不是最少事务数的全局最优保证，也不最小化操作。预算是 64 个原始事务、2,048 个操作、128 次候选检查；未完成最后的逐个删除检查时，返回 `oneMinimal: false`。

## 自包含复现包

```powershell
node dist/moontxnwitness.mjs check mini.json --capsule case.capsule.json
node dist/moontxnwitness.mjs replay case.capsule.json
```

`check` 的异常退出码 1 是预期；成功复现 `replay` 退出码 0。

复现包格式 `moontxnwitness-replay/v1` 携带历史文本、报告文本、各自 SHA-256 和引擎版本。摘要覆盖**包内存储文本的 UTF-8 字节**，用于发现内容变化。复现时先检查结构和摘要，再由 MoonBit 当前引擎重算核心语义字段：状态、模型、完整性、统计、发现、依赖、环、串行顺序、版本顺序，以及已提供的搜索/版本来源字段。

这可以复现没有环的直接异常或穷举失败，避免仅导出一个无法重现的图。摘要不包含签名，不能认证日志是谁采集的。更改内容后重新计算摘要也不能让错误的核心判断通过重算检查；补充说明和展示字段不属于语义复核范围。包大小最多 32 MiB。

## 两种模型对比

```powershell
node dist/moontxnwitness.mjs compare-models examples/strict-realtime.json
```

结果 `realtime-only-violation` 表示：忽略实时先后时有可行串行执行，但共同观察时钟提供的先后关系导致严格模型异常。`data-order-violation` 表示普通模型已确定异常。时间缺失仍会在严格模型中返回无法判定，不补造时间。

## 两种“验证”

- `verify HISTORY CERTIFICATE` 复核环的每条依赖及闭合关系，不重跑找环，也不验证最短性。
- `replay CAPSULE` 验证存储文本摘要，并用当前引擎重现完整的核心判断；它会重新分析历史。

两者都不替代对原始采集过程的信任审计，也不能证明整个数据库在所有执行中可靠。
