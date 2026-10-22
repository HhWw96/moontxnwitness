# v0.1.5 关系集合 SDK 隔离候选

只在本目录准备五个可接入文件，不改主线、版本、MoonBit 内核、构建或数据库。基于已构建 v0.1.4 的实际运行文件检查，不把本候选称为 v0.1.5 编译、真实数据库、正式性能或发布验收。

## 已有工作与本次新增

已有 relation-set-v1 MoonBit 实现、127项边界测试、独立Python解释器、170份边界及1,000份不同生成历史。最新 `verification/relation-v3/acceptance-2026-10-22T12-25-49-427Z/receipt.json` 已绑定v0.1.4 core，57组检查、1,170份历史零差异；本轮只读核对其原件和冻结文件，不重复开发或重跑全部历史。

现有 `verification/relation-v3/postgres-2026-10-21/` 包含8个真实PG场景各20次及160份离线模型核对。它们只证明其绑定的受控固定SQL映射，不能称任意业务SQL采集。本候选未重跑数据库。上述源码、输入及原收据摘要见 `prior-artifacts-review.json`；早期439处差异与原失败保留，不改冻结预期。

当前SDK已有通用v3和列表六入口，没有关系专用入口。本次新增：

1. `payload/cmd/sdk.mjs` 追加 `normalizeRelationCaptureV3`、`analyzeRelationV3`、`reduceRelationV3`、`verifyRelationV3`、`makeRelationCapsuleV3`、`replayRelationCapsuleV3`，JSDoc固定类型和根模型护栏。通用与列表六入口保留。
2. `payload/examples/relation-source-closure.json` 是独立冻结来源闭包反例的**原字节副本**，四事务P/A/B/N，未新造期望。
3. `payload/examples/relation-roundtrip.mjs` 运行异常→删除N→保留来源P与异常A/B→胶囊重放。每次使用新目录，保留事实、报告、缩减、胶囊、重放与摘要，错误留失败收据。
4. `payload/scripts/relation-sdk-test.mjs` 核对170原边界、71旧列表历史与六入口、模型误投、原始文本、invalid诊断、篡改、来源不足、计算/候选预算与示例，另调用独立Python解释器核对5份示例输入。
5. `payload/docs/relation-sdk.md` 说明接口、支持范围与来源闭包含义。

显式入口只接纳 `traceSchema:3`、`dataModel:"relation-set-v1"`，错模型不自动补标识或转换。护栏的JSON解析不替代内核校验，原始文本保持传给MoonBit；核心仍拒绝重复字段、未知列与混合操作。读取来源不足、未知结果、部分查询和未证明完整快照保持无法判断，不推断不存在。专用重放先执行完整generic校验，再拒绝无法声明关系模型的胶囊，包括可重算但trace非法JSON/null/array/number的invalid诊断；正确关系模型的invalid或inconclusive可按原规则重放。`valid:true`只表示重算一致，必须另看status与coverage。

保留原额度：精确分析6个提交事务、全轨迹128个行操作、100,000状态、1,000,000语义检查；缩减最多256候选。支持int64规范字符串、布尔、Unicode码点文本与已有AND谓词/墓碑/保存点；不扩大NULL、函数、JOIN、聚合、子查询、任意SQL或完整隔离分类。根检查额外开销有界，未做正式性能测量。

## 已执行结果

最终双入口作者检查：`runs/run-013cPQ/receipt.json`，**194/194通过**，170份关系边界及71份旧列表历史。两次独立示例均4→3事务，逐文件摘要一致、报告复核及胶囊重放通过。独立Python解释器确认原始/缩减后violation；删P为inconclusive，删A/B为consistent，因此不能仅保留两个异常事务而删去来源。

另外 `runs/run-6ADwGa/receipt.json` 用没有旧SDK副本的独立运行目录复跑，194/194通过，验证接入主线后的单运行时路径。该模式明确记 `priorSdkSnapshotAvailable:false`，没有冒充双版本比较；仍核对170关系及71列表冻结判定，统一原列表回归也继续保留。

首次191项通过收据为 `runs/run-SSPSHA/receipt.json`。扩充旧列表兼容测试时，`runs/run-KZKzXl/receipt.json` 为193/194通过，原作者测试误认为所有invalid-options报告都可打包；既有14也拒绝没有execution的诊断。最终将该项改为精确对照原函数的返回或异常类型/消息，保留 `negative-options-invalid` 的原拒绝，没有放宽生产验证。随后通过记录均保留。本候选作者自检不等于独立最终签署。

证据目录汇总脚本首次误用数据库收据字段 `cases`，实际数据库记录名为 `scenarios`；离线模型收据才用 `cases`。原错误记录在 `freeze-first-failure.json`，只修汇总脚本读取字段，未改原收据或候选实现。

## 复跑与安全接入

```text
node artifacts/v015-relation-candidate/payload/scripts/relation-sdk-test.mjs --repository . --runtime artifacts/v015-relation-candidate/runtime --output-root artifacts/v015-relation-candidate/runs --example-root artifacts/v015-relation-candidate/example-repository
```

`runtime/` 保留原14的core/capture-core/evidence/manifest、候选SDK和真正旧SDK `generic-sdk.mjs`。测试先核验编译文件摘要。`runtime-no-prior-sdk/` 用于集成形态复验；原示例工作副本在 `example-repository/`。全部新输出只写artifacts。脚本参数可另指定独立输出父目录；不编译、不连数据库、不下载。

最终以 `candidate-manifest.json` 为准。主集成先 `git apply --check artifacts/v015-relation-candidate/candidate.patch` 再应用。补丁只含上列5个目标文件；现有构建已自动复制sdk.mjs，示例在已分发examples下。接入时把 `node scripts/relation-sdk-test.mjs` 加入统一测试，并核对新源码/便携包可实际运行示例。Mooncakes交付MoonBit核心，JS入口对应GitHub源码/便携包，不新增Mooncakes安装机制。

版本号、旧报告兼容白名单、正式构建/跨目标、受控DB是否重跑、打包与公开下载应由主线最终范围独立验收。本候选不代替这些步骤。
