# 关系集合 SDK 与来源闭包演示

固定模型入口从 `dist/sdk.mjs` 导入：`normalizeRelationCaptureV3`、`analyzeRelationV3`、`reduceRelationV3`、`verifyRelationV3`、`makeRelationCapsuleV3`、`replayRelationCapsuleV3`。通用 v3 与列表六入口均保留。

```javascript
import {readFileSync} from 'node:fs';
import {analyzeRelationV3, reduceRelationV3, makeRelationCapsuleV3, replayRelationCapsuleV3} from './dist/sdk.mjs';

const text = readFileSync('examples/relation-source-closure.json', 'utf8');
const report = analyzeRelationV3(text);
const reduced = reduceRelationV3(text);
const capsule = makeRelationCapsuleV3(reduced.reducedCapture, reduced.report);
console.log(report.status, reduced.oneMinimal, replayRelationCapsuleV3(capsule).valid);
```

运行 `node examples/relation-roundtrip.mjs`，也可用 `--out-root` 指定已有的输出父目录。每次使用新目录，保留原输入、原报告、缩减结果、缩减输入、胶囊、重放结果及逐文件摘要。示例原字节来自独立冻结的四事务反例：P 提供被后续读取的版本，A/B 的完整谓词查询及插入形成不可串行执行的环，N 是无关事务。缩减仅删除 N；保留 P/A/B 三事务。删除 P 会失去读取来源而无法判断，删除 A 或 B 则可串行执行。这展示来源闭包的必要性，不能只保留看起来互相矛盾的两笔事务。

Capture 必须显式声明 `traceSchema:3`、`dataModel:"relation-set-v1"`。寄存器、列表或缺少模型标识时抛出 `TypeError`；超过 8 MiB UTF-8 时抛出 `RangeError`。原始 JSON 字符串保持，重复字段、模型内结构、列/谓词/版本约束、来源不足和预算由同一 MoonBit 核心核验。不会补充查询结果、转换业务值或把 RETURNING 当作完整 SELECT。列表、寄存器有效胶囊及无法声明关系模型的非法 JSON 诊断胶囊在关系专用重放中返回 `valid:false`；正确关系模型的可重算 `invalid` 或 `inconclusive` 报告仍可生成胶囊。`valid:true` 表示重算一致，必须另看 `status` 和覆盖情况。

`analyzeRelationV3` 使用 `{maxStates,maxOperationChecks}`；`reduceRelationV3` 使用 `{maxChecks,analysisOptions}`。原有精确额度保持6个已提交事务、128个全轨迹行操作、100,000状态、1,000,000语义检查；缩减最多256次候选。超出精确容量或预算耗尽返回无法判定，不能称为无解。来源直接反证也不能绕过原有完整覆盖和精确容量规则；`oneMinimal` 是同一异常谓词下的事务单删最小，不保证全局最小。

支持 int64（规范十进制字符串）、布尔和按Unicode码点比较的文本；完整行集合查询、空结果、最多8项等值/区间AND谓词、插入、更新、删除墓碑及保存点。NULL、任意函数、JOIN、聚合、子查询、混合模型事务、自动任意SQL映射和完整隔离分类仍不支持。示例为合成历史，不连接数据库、不认证采集真实性，也不代表正式性能收益。现有独立解释器、冻结历史与受控数据库证据见 [关系模型说明](relation-v3.md)。
