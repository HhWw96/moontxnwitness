# v0.1.4 列表 SDK 隔离候选

本目录只准备五个可接入文件，不改主线、版本、构建、数据库或既有冻结预期。基于现有 v0.1.3 编译产物执行轻量检查；不是 v0.1.4 发布验收。

## 已有能力和本次新增

已有 MoonBit append-list-v1 核心、88 项边界测试、独立 Python 解释器及冻结历史已经存在。本轮只核对其源码与收据，未重复实现或重跑 20,071 份全部输入。最新 2026-10-22 11:38:04 严格对照绑定当前 v0.1.3 core，记录 20,071 份输入、10,118 个不同输入摘要、31 种篡改，零差异。早期 33 处差异与第一份不兼容研究胶囊仍保留，不能宣称所有早期研究产物都支持重放。

现有真实 PostgreSQL fixture 六场景各20次（合计120次）和离线重核收据已存在；它们只证明当时绑定的受控 SQL 映射。本候选没有运行数据库、自动 SQL 接入或新的性能测量。具体原件、摘要与历史状态见 `prior-artifacts-review.json`。

本次新增：

1. 在原 `cmd/sdk.mjs` 追加 `normalizeListCaptureV3`、`analyzeListV3`、`reduceListV3`、`verifyListV3`、`makeListCapsuleV3`、`replayListCapsuleV3`，有 JSDoc 固定模型类型及运行时护栏。保留原通用 v3 函数。
2. `examples/list-cycle.json` 从已冻结 `two-key-read-append-cycle` 输入扩展一个无关读取事务。唯一身份与重复业务值均保留。
3. `examples/list-roundtrip.mjs` 实际执行异常→删除噪声→两事务单删最小→胶囊重放；每次生成新目录，保存逐文件摘要，失败留收据。
4. `scripts/list-sdk-test.mjs` 逐字段比较71份原手工历史；核对模型误投、类型/字节边界、原始字符串、重复字段、混合模型、未知提交、来源不足、搜索和缩减独立预算、篡改及完整示例。另用独立 Python 解释器确认示例无串行执行，删除任何剩余事务后可串行执行。
5. `docs/list-sdk.md` 只说明本次固定列表入口和真实边界。

固定入口要求显式模型，不会添加默认模型或序列化后重写调用者的原始字符串。JSON.parse 只用于根模型护栏；原文本仍直达 MoonBit 的有界重复字段、深度与语义校验。错模型 capture 抛 TypeError；模型内非法事实保持 invalid。有效的非列表胶囊返回 valid:false。与现有 v3 相同，invalid 或 inconclusive 诊断也可以被如实重算，valid:true 不能代替 status。

额度与核心算法均不改：精确分析6个已提交事务、128个原始append/read，默认及最大100,000状态和1,000,000语义检查；缩减最多256次候选。来源不足、未知结果、结构和计算额度仍可见。不新增完整隔离分类、不提高规模、不宣称正式性能改善。入口额外的有界 JSON 根检查有开销，正式性能尚待后续测量。

## 运行与接入

隔离测试（已有 Node/Python，不编译）：

```text
node artifacts/v014-list-candidate/payload/scripts/list-sdk-test.mjs --repository . --runtime artifacts/v014-list-candidate/runtime --output-root artifacts/v014-list-candidate/runs --example-root artifacts/v014-list-candidate/example-repository
```

候选 `runtime/` 是复制的现有 v0.1.3 core、capture-core、evidence及构建清单，加候选SDK。`generic-sdk.mjs` 保留旧SDK，用于真正的双入口比较；编译 core 和采集 core 的摘要必须匹配原清单。`example-repository/` 为演示隔离工作副本。所有测试输出只写新 artifacts 目录。

接入时先 `git apply --check artifacts/v014-list-candidate/candidate.patch`，再由主集成应用。补丁只修改 SDK 并新增示例、说明和测试五个目标文件；不修改版本、核心、构建或工作流。现有 `scripts/build.mjs` 已复制 sdk.mjs，示例位于已分发的 examples；主集成应将 `node scripts/list-sdk-test.mjs` 加入统一测试，然后按实际 v0.1.4 构建重核。Mooncakes 主要公开 MoonBit 核心，JS SDK 对应 GitHub 源码/便携包，不冒充 Mooncakes 新增 Python/JS 安装机制。

本候选只提供安全接入材料。原版本胶囊兼容仍须由实际新版本验证规则核对，候选没有改引擎版本白名单。发布前需新构建、多目标及统一回归、实际分发包安装与独立验收；是否重跑列表原PG或离线重核由主集成按最终声明范围决定。

## 本轮结果与失败保留

最终作者检查 `runs/run-TunYYE/receipt.json`：**91/91通过**，71份手工历史全部匹配。示例连续两次生成不同目录；每次3事务缩至2事务，真实重放通过。独立解释器执行4份输入：原始与缩减后为 violation，任意单删后为 consistent。本轮没有数据库或编译执行。

首轮 `runs/run-10GQaH/receipt.json` 为86/87通过，唯一失败是作者误把可重算 invalid 诊断的打包当作必须抛异常；原通用v3允许它，测试改为逐字段核对其仍是invalid，而不修改生产判断或冻结预期。随后87、90项通过记录保留。额外自查发现有效的 foreign-null invalid诊断胶囊应按模型拒绝而非空指针；候选增加根对象检查及null/array/number/empty-object四项回归。

作者测试不等于独立最终签署。独立审计由另一路执行；本目录不声称审核、生产采用、正式性能或发布完成。
