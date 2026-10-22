# 已验证点寄存器环的类型与来源解读

从 `dist/sdk.mjs` 导入 `explainRegisterCycleV3(trace, report)` 和 `verifyRegisterCycleExplanationV3(trace, report, explanation)`。核心先完整重算原报告，只有已提交事务、完整覆盖、显式点 read/write 的现有依赖环才输出类型；不重新构图或寻找其他类别的环。

```javascript
import {readFileSync} from 'node:fs';
import {analyzeV3,explainRegisterCycleV3,verifyRegisterCycleExplanationV3} from './dist/sdk.mjs';
const trace = readFileSync('examples/register-cycle.json','utf8');
const report = analyzeV3(trace);
const explanation = explainRegisterCycleV3(trace,report);
console.log(explanation.status,explanation.subtype);
console.log(verifyRegisterCycleExplanationV3(trace,report,explanation).valid);
```

运行 `node examples/register-cycle-roundtrip.mjs`，可加 `--out-root` 指定已有输出父目录。每次创建新目录，保存原输入、报告、独立派生解读、原格式 v3 胶囊和两项复核结果；收据包含所有文件的字节数及摘要。示例使用合成点历史，不连接数据库或外部 checker。报告文件和胶囊中的 reportText 使用相同原始字节，复核无需猜测序列化格式。

`trace` 和 `report` 接受 JSON 原文或对象，`explanation` 必须是已经解析的对象。原始 trace/report 分别绑定摘要；即使只改变空白，也需要从新的原文重新生成解读。对象入口使用 JSON 序列化后的文本。重复字段和非法结构交给原 MoonBit 核心验证。新解读没有塞回原报告或 v3 胶囊，因此旧格式的重放语义保持。v0.1.6 的显式版本兼容延续至已发布 v0.1.5；观察到的版本身份、业务字符串及预算不作替换。

支持 `traceSchema:3`、`point-register-v1` 的既有 `register-serializable-v1` / `v3-register-1` 报告。每条解读包含原边、事务及投影操作索引、全部匹配的原始观察 seq、版本链及其声明来源。`asserted` 是输入声明，不认证采集真实性；重复读取返回所有匹配，不推断唯一发生位置。保存点的读取/写入效果仍由原核心处理：保留已交付读取，撤销写不能成为存活投影操作。

五类标签只描述选中的已证环。规则依据固定 Elle commit `4e359e597c52938b0afebb8bc42273914d68a424` 的 [cycle-explainer](https://github.com/jepsen-io/elle/blob/4e359e597c52938b0afebb8bc42273914d68a424/src/elle/txn.clj#L477)，本 SDK 独立实现其 ww/wr/item-rw 子集，不调用 Elle。

| 选中环边型 | 标签 |
| --- | --- |
| 全部 WW | G0 |
| 仅 WW/WR 且有 WR | G1c |
| 恰好一条 item RW | G-single-item |
| 多条 item RW，两两不相邻 | G-nonadjacent-item |
| 多条 item RW，存在相邻一对 | G2-item |

首尾两条边也相邻。已有最短 WW 环不排除其他位置存在 G2；结果明确 `searchesOtherCategoryCycles:false`、`acceptsIsolationModels:false`。这不是六隔离模型、完整 SI、G1a/G1b/INT、列表/关系、谓词、RT 或 process 分类；也不接受任意 typed graph 作为可信事务来源。40P01、40001 等执行故障继续由独立诊断单列，不改名为依赖环异常。

`status` 为 `explained`、`not-applicable`、`inconclusive` 或 `invalid`；原判定另存 `sourceStatus`。只有 `explained` 的 `subtype` 非空。原报告无法复算时拒绝；缺少覆盖、来源或预算时保持无法判定；没有适用环时不输出类型。复核的 `valid:true` 表示原报告和派生字段都可重算，可以对应 invalid/inconclusive 诊断，不能据此断言无异常或模型接受。

输入上限保持 trace 8 MiB UTF-8、report 32 MiB；派生对象输入及输出 8 MiB，最多解释 512 条现有环边。超过输入字节额度会抛出 `RangeError`，不合法参数可抛出 `TypeError`；超出可支持的投影环不适用，派生输出超额返回 inconclusive 且不输出半份标签。解读不扩大原分析/搜索预算，也没有新的性能提升声明。部署前仍需核对实际版本的测试、下载及安装收据。
