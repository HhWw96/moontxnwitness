# v0.1.4 列表 SDK 候选独立审查

2026-10-22。审查者不是 SDK 包装或候选测试的作者；这是独立 AI 技术检查。只写 `artifacts/`，没有修改主线、编译、数据库、下载、安装或正式性能测量。

最终候选 `candidate-manifest-v2.json` SHA-256：`cda1b71bbfc2cb5e7c9b93f69f97065d5a9be950f1e8c059acc8a70ea093f9ff`。**10/10 独立检查组通过**；其中另行调用原作者套件，**92/92** 通过。71 份冻结手工历史均逐字段匹配通用 SDK。这些数字有重叠，不叠加为不同场景数。

最终收据：`runs/review-FCQouG/receipt.json`，SHA-256 `79fd9a3f46474200927f20dea2d9a4d6f6b80d2ddad54ad4e7e910687bb2406e`。原执行 Node 为 v24.13.0；核心是候选复制并验证的 v0.1.3 core/capture-core，不是新构建的 v0.1.4。

## 实际发现及修复复验

首版列表专用重放在通用胶囊验证之后再次解析 trace。通用 SDK 允许把非法 JSON 文本准确打包为 `status:invalid` 的可重算诊断，因此 `traceText:'{'` 的通用胶囊可以有效重放，但首版列表入口会抛出 `SyntaxError`。

独立失败保留在 `runs/malformed-gf67h3/receipt.json`：`{`、空文本、未闭合对象及非 JSON 文本四组全部复现该异常；胶囊原件同目录保存。首版候选完整快照和 manifest 保留在实现者目录 `artifacts/v014-list-candidate/freezes/initial/`，未被最终版本覆盖。

最终版本只在二次解析失败时返回固定模型拒绝。独立检查用相同四份输入重新生成真实通用胶囊：通用入口仍返回可重算的 invalid 诊断，列表入口全部稳定返回 `valid:false`，没有放宽为接受错误模型。

独立检查的首轮另有一个测试自身错误：把未编码的 `text` 当作合法 JSON 字符串根，误要求 `TypeError`；该输入本身不是 JSON，应产生 `SyntaxError`。失败 `runs/review-InUF62/receipt.json` 与当时的 `audit-implementation.mjs` 保留。修订仅把字符串根编码为 JSON 后再测试类型拒绝，未改候选、核心或预期语义。

## 已核对的行为

- 48 个冻结文件及九个原主线输入前后摘要保持；运行时 SDK 与 payload 相同，通用 SDK 和两份核心保留原字节。
- 用独立 spy 模块检查五个 capture 入口的实际调用参数：带空白、重复字段的原始字符串不被 JSON.parse/JSON.stringify 重写；对象只序列化一次。8 MiB UTF-8 的入口边界接受并原样传递，超过边界在核心调用前拒绝；多字节对象也按字节限制。spy 仅检查传输，所有语义比较使用真实原核心。
- 71 份冻结历史的规范化、完整分析报告及报告验证与通用入口逐字段相同；重复根字段和嵌套字段仍由核心判为 invalid。invalid 诊断可重放不代表模型成立。
- null、数组、数字、布尔、字符串根、空对象、寄存器、关系及缺失模型标识均不能误投列表入口；有效的非列表通用诊断胶囊也被拒绝。
- 未知来源、未来生产者、未知提交和零搜索预算保留 inconclusive、原观察及 `normalized.history:null`。`valid:true` 仅代表重放诊断有效，`status` 和不完整覆盖标记未被改成 consistent/完整。
- 精确容量仍为六个已提交事务、128 个 append/read；分析预算与缩减候选预算分开，预算未完成不宣称单删最小。输入和 options 未被修改。
- 篡改结论、模型、预算或覆盖，再重新计算报告摘要，仍被拒绝；篡改独立绑定的规范化事实也不能绕过语义验证。
- 原 92 项套件在独立输出目录重新通过，包括两次新目录示例、3→2 事务缩减、来源闭包、COMMIT 响应引用和独立 Python 解释器对原始/缩减/任意单删的对照。

最终候选未再发现未修复的 SDK 护栏问题。可接入范围是显式 append-list-v1 便捷入口及合成演示，核心模型、来源假设与预算没有扩大。新 v0.1.4 的版本兼容、构建、多目标、全新消费者及公开下载验证仍由实际发行流程完成；本次不声称它们已经通过，也不新增自动 SQL 列表采集或完整隔离分类能力。

复跑：`node artifacts/v014-list-independent/check.mjs`。所有输出写入新的 `runs/review-*` 目录；首次异常与修订后通过记录不会覆盖。
