# MoonBit v4 核心库示例

这是独立的 MoonBit 消费者项目，仅通过公开 API 导入 `HhWw96/moontxnwitness`。运行不需要数据库、Node.js 或 Python；需要 moonc 0.10.16 或以上版本。

本示例的 `moon.mod` 已固定使用公开发布的 0.4.1。在本目录运行以下命令：

```powershell
moon update
moon run --target wasm-gc . --deny-warn
```

示例解析一次输入得到不透明的 `HistoryV4`，直接调用 `analyze_v4`、`classify_v4` 和 `reduce_v4`，再使用 `verify_v4` 等核心验证接口逐字段核对结果。寄存器样例会缩掉一个无关事务；缩减必须显式指定 `preserve=Serializable`。列表样例检查追加后的完整读取，关系样例检查空关系快照。

预期输出：

```text
register: violation; category witness and reduced counterexample verified
append-list: consistent; complete analysis verified
relation-set: consistent; dedicated category report independently verified
```

寄存器和列表通过通用 v4 入口检查 G0、G1c 和 G2-item。关系样例使用专用分类入口 `classify_relation_v4_json` 和 `verify_relation_classification_v4`。类别报告与隔离模型分析分别验证。输入是显式提供的模型事实。

源码开发期间可使用临时 MoonBit workspace 将依赖指向当前源码；公开安装验证应使用上面的注册表版本，不保留本地依赖替换。
