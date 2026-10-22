# 追加列表 SDK 与本地演示

固定模型入口从 `dist/sdk.mjs` 导入：`normalizeListCaptureV3`、`analyzeListV3`、`reduceListV3`、`verifyListV3`、`makeListCapsuleV3`、`replayListCapsuleV3`。通用 v3 入口继续保留。

```javascript
import {readFileSync} from 'node:fs';
import {analyzeListV3, reduceListV3, makeListCapsuleV3, replayListCapsuleV3} from './dist/sdk.mjs';

const text = readFileSync('examples/list-cycle.json', 'utf8');
const report = analyzeListV3(text);
const reduced = reduceListV3(text);
const capsule = makeListCapsuleV3(reduced.reducedCapture, reduced.report);
console.log(report.status, reduced.oneMinimal, replayListCapsuleV3(capsule).valid);
```

运行 `node examples/list-roundtrip.mjs`，或用 `--out-root` 指定已存在的输出父目录。每次生成独立的新目录，保存原输入、判断、缩减、缩减后输入、复现包、重放结果及逐文件摘要。示例包含三个事务：两个事务分别读取另一列表的原值后追加自身列表，一个事务仅作无关读取。解释器证明不存在串行顺序，缩减删除无关事务，保留两事务反例，再从同一事实与判断生成复现包并重算。

所有 capture 入口要求明确的 `traceSchema:3`、`dataModel:"append-list-v1"`。误传寄存器、关系模型或缺少模型标识时抛出 `TypeError`；输入超出 8 MiB UTF-8 时抛出 `RangeError`。模型内的结构校验、重复 JSON 字段、混合操作、来源不足及预算由原有 MoonBit 内核处理，结果与通用 v3 入口一致。不会自动补上模型标识、重写输入或把预算耗尽变成无解。列表专用重放会拒绝其他模型的有效胶囊；`valid:true` 仅表示报告可重算，也适用于如实记录的 `inconclusive` 或可重算的 `invalid` 诊断，必须另看 `status`，不能把它当作无异常。

`analyzeListV3` 接收 `{maxStates, maxOperationChecks}`；`reduceListV3` 接收 `{maxChecks, analysisOptions}`。默认与最大额度维持 6 个已提交事务、128 个原始 append/read、100,000 状态、1,000,000 次语义检查；缩减最多 256 次候选检查。完整覆盖时可直接证明的来源反证沿用原规则。更大的结构日志仍可能只能返回 `inconclusive`，不是扩大了精确枚举范围。`oneMinimal` 只表示同一异常规则下的事务单删最小，不保证全局最小。

每项元素需要唯一身份，业务值可以重复。列表值目前为 JSON 字符串，首版不支持混合模型事务。保留保存点回滚前已交付的读取，不从客户端时间或 COMMIT 回复先后推断提交顺序。示例是合成历史，不执行数据库，不代表自动 SQL 采集、完整隔离级别分类、正式性能收益或来源真实性认证。模型及现有独立验证、真实数据库证据详见 [列表模型说明](list-v3.md)。
