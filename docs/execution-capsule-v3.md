# 执行故障诊断包

`makeExecutionCapsuleV3(trace)` 将原始 v3 记录文本、MoonBit 完整执行诊断及其摘要封存；`replayExecutionCapsuleV3(text)` 重新计算全部诊断并逐字段校验。运行 `node examples/execution-roundtrip.mjs`，或传入 `BEFORE_TRACE.json AFTER_TRACE.json NEW_OUTPUT_PARENT`。默认示例使用两份既有 MLflow 组件夹具记录，不连接数据库。

```js
import {makeExecutionCapsuleV3, replayExecutionCapsuleV3} from './dist/sdk.mjs';
const capsuleText = makeExecutionCapsuleV3(originalTraceText);
const replay = replayExecutionCapsuleV3(capsuleText);
if (replay.valid) {
  console.log(replay.diagnostic.captureStatus,
    replay.diagnostic.captureCoverage,
    replay.diagnostic.transactionOutcomes,
    replay.diagnostic.faults);
}
```

`valid:true` 仅表示保存的诊断能从同一原始记录重新计算，不表示没有故障、记录完整、数据库真实性认证、隔离模型违反或业务已修复。原记录的 unknown COMMIT、缺失来源、无法判定及已观察故障均保留。40P01 是执行死锁，40001 是序列化中止，55P03 是锁不可用，57014 是取消；其它错误保留原类别和 SQLSTATE，不改称 G2。没有观察故障不构成无故障证明。现有模型分析可同时为 inconclusive。

新包格式为 `moontxnwitness-execution/v1`，`schemaVersion:1`、`diagnosticAlgorithm:"v3-observed-failures-1"`，与原 `moontxnwitness-replay/v3` 模型胶囊分开。SDK 的两个生产器/重放器不能互换，v0.1.8 除当前执行引擎外，显式接受同诊断算法的 v0.1.7 执行包；保留原引擎头、原 trace 和完整诊断，不重写业务字段。未知或未来引擎仍拒绝。旧模型胶囊继续按既有显式兼容规则重放；不能把模型兼容名单推定为执行格式的兼容名单。

包记录实际引擎、完整 `traceText`、`diagnosticText`、各自 SHA-256 及固定预算。外层 JSON 采用生产器固定字段顺序、两空格缩进及末尾换行，传入重排、删空白、重复或额外字段的外层文本会拒绝。trace 文本自身保持原样，包括原有空白、SQL、参数和 Unicode；不会为格式兼容而改写。重封摘要不能使篡改后的故障、来源、事务结果、覆盖缺口或诊断字段通过重算。摘要与重算不是签名：正确改写输入并重新计算诊断形成的是另一份调用者记录。

实际额度为 trace **8 MiB UTF-8**、诊断 **32 MiB UTF-8**、完整执行包 **32 MiB UTF-8**；核心解析原 trace 的上限是 **8 Mi 代码单元**，解析规范化结果的上限是 **32 Mi 代码单元**，规范化策略为现有 `normalize_capture_v3_json/defaults`。这些单位不能互换，包会因转义和重复表示而先达到整体额度。现有寄存器规范化还限制 **65,536 个事件、512 个事务、10,000 个初始键、10,000 个点读写操作、10,000 行交付结果和64层嵌套保存点**；超过限制返回原核心诊断，不能省略事件后宣称成功。包内 `modelSearch:false`，不进行模型搜索，也不承诺上述规模的精确模型枚举。

生产器在输入类型、Unicode、格式/生命周期、事件或字节额度无效时抛出 TypeError、RangeError 或 Error；重放要求字符串，非字符串抛 TypeError，其余不能支持或不能重算的包返回 `valid:false` 及原因。覆盖不完整但语义有效的记录可打包并有效重算，不能因而升级其覆盖结论。返回 scope 始终声明不执行数据库、不认证真实性、不证明故障不存在、不作模型违反结论、不代表完整应用集成。

默认示例保存两份原始 trace、执行诊断包和重放结果，并分别保存原模型报告及原模型胶囊。原 MLflow 固定提交是修复前 `c2dcdb96c62c75f35af3f28b5d493c0cf139a856` 和修复后 `40c146a23518813e8488e55fc9752e08c3a8bad5`。记录观察到故障 1→0；两份模型报告仍覆盖不足。它们来自原受影响方法/模型及受控调度器，没有完整 MLflow 服务。`fixtures/execution-v3/source-origin.json` 绑定原文件和上游许可；当时 `capture_v3.py` 依赖的 `capture.py` 未被原执行收据绑定，该缺口保持，不用后来快照追补认证。示例重放不是新数据库复现、任意并发种子修复证明或完整应用接入。

实际旧包兼容输入在 `fixtures/execution-v3/compat/v017/`：两份原包来自实际 v0.1.7 发布回归的 SDK 输出，原文和生产 source/core/SDK 绑定保留；它们并非从 GitHub v0.1.7 发行包下载。`node scripts/execution-compat-sdk-test.mjs` 用当前引擎重放两份真实17原包，核对完整诊断、原 trace 文本、错误头和重封摘要篡改。旧 capture.py 来源缺口不因此补齐。

`node scripts/execution-sdk-test.mjs` 执行 54 项固定断言；`--output-root NEW_PARENT` 将新结果保存在指定父目录下，保留每轮收据及首失败。它只做离线检查，结果与实际构建、数据库执行、安装和公开发布收据分别记录。
