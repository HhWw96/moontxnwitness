# dislock v3 固定 SQL 语义核验器

本模块核对冻结 dislock 组件的六种 SQL、参数、业务返回结果、版本来源与安装明细。默认分析保留原 v3 规则；开发入口可显式选择已核验的固定 SQL 策略，不认证采集数据来自真实数据库。

冻结对象为 Actticus/dislock 的提交 `f9946f07159054433d9071c3805e41223cb47856`，profile 为 `dislock-f9946f0-v3/1`。上游源码与来源锁见 `experiments/business/dislock/upstream/`；精确 SQL 见 `v3_registry.json`，受控安装器见 `v3_install.py`。它们是组件与实验集成，不能据此声称已验证完整生产系统。

## 接口和输出

MoonBit 独立诊断入口为 `dislock_sql_v3_proof_json(text)`，SDK 为 `inspectDislockCaptureV3(trace)`。算法标识为 `dislock-f9946f0-sql-proof-1`。

输出含：

- `analysisCoverageAccepted:false`：局部核对不能改变整个分析的覆盖结论。
- `verifiedStatements`：按序排列的已核对固定 SQL 事件序号。
- `verifiedFacts`：已核对的同 statement 读、写、条件事实序号。
- `verifiedProfiles`：已核对安装的身份，每项为 `[profile,schema,table]` 的 JSON 文本。
- `gaps`：核对不足或不匹配的原因；失败不返回部分豁免集合。

内部 `v3_dislock_sql_proof(root)` 返回上述三类集合和缺口，供后续经过独立验收的分派器使用。当前正常规范化仍保留 unmapped_statement、unverified_sql_mapping、unsupported_condition 与 unverified_sql_profile 等原覆盖缺口。诊断入口先调用原寄存器 v3 生命周期校验；格式或生命周期 invalid 时不返回 SQL 已核对集合。原始 SQL 覆盖不足导致 inconclusive 时，仍允许进行局部语义诊断。

未来若接入分析，调用方只能按具体 statement/fact/profile 集合消除对应的缺口，不能整体清除未支持 SQL、未消费结果、未知提交或其他来源缺口。

## 显式分析策略

默认结果及旧复现规则保持。选择 `sqlProof:"dislock-f9946f0-sql-proof-1"` 才按上述逐项集合核对对应 SQL 来源：

```javascript
const policy = {sqlProof: 'dislock-f9946f0-sql-proof-1'};
const normalized = normalizeCaptureV3(trace, policy);
const report = analyzeV3(trace, policy);
const reduced = reduceV3(trace, {analysisOptions: policy, maxChecks: 256});
```

规范化选项仅接受 `sqlProof`；分析选项还可带原数值预算。未知策略、null、布尔值或其他类型均返回 invalid，不静默降级。CLI 的 `ingest-v3`、`check-v3`、`reduce-v3` 对应 `--sql-proof dislock-f9946f0-sql-proof-1`；verify/replay 只读取报告内策略。

显式规范化算法为 `v3-lifecycle-sql-1`，报告为 `v3-register-sql-1`。`normalized.sqlProof` 保存原 profileEvidence、具体核对集合和缺口；`execution.analysisOptions.sqlProof` 绑定所选算法。复现包从经过完整重算的报告取得规范化内容，验证按记录策略重算。删除或篡改策略不能沿用其更强报告。

只有来源完整的 statement/fact/profile 才消除相应 SQL 缺口。初始快照不一致、未封闭写者、原始 gap、缺序号、零行缺来源和未知结局继续阻止完整结论。缩减在显式策略下只裁剪被删除事务的原 write 版本对应实际效果账本行；不改初始事实、元数据或剩余前驱，仍逐候选重新验证来源。

独立 [策略验收](../verification/v3/dislock-policy-independent-2026-10-21T04-14-03-848Z/receipt.json)对七份历史记录完成 186 项检查：默认七案仍无法判定；选择策略后三案一致、四案无法判定；旧七份复现包可按默认规则重放，36 项报告/复现篡改与 CLI 检查通过。这是该阶段源码 `f33c8675…` 的开发验收，不代表所有版本、成本或发布关卡完成。

## 六类 SQL 和精确边界

只匹配注册表中原始 SQL 及扩展投射后的 executedSql，保留空格、换行、WHERE、ON CONFLICT、NOW、参数顺序和 RETURNING 语义，不做通用 SQL 解析或模糊匹配。

| mappingId | 核对内容 |
| --- | --- |
| dislock.acquire-schedule/1 | 绑定键、owner 和 aware datetime；真实 INSERT/冲突 UPDATE、OLD/NEW 身份、不可变候选前驱、到期条件与实际新 expiry |
| dislock.acquire-run/1 | 同上；实际新 expiry 等于事务 NOW 加绑定 TTL 的 interval 结果 |
| dislock.read-current/1 | 交付的 expiry/owner 与同语句 token 及已捕获版本来源一致 |
| dislock.renew/1 | 实际 OLD.owner 等于绑定 owner；实际新 expiry 与 NOW、TTL 一致 |
| dislock.expire/1 | 实际 owner 条件与原 RETURNING key；新 expiry 按精确 SQL 为事务 NOW，并与实际效果账本核对 |
| dislock.server-now/1 | 原始单列 NOW，不能额外生成键读取或写入；同事务 NOW 必须保持一致 |

所有业务 rows 必须逐项等于实际 serverRows 的业务列前缀；业务列名称和 PostgreSQL OID 也逐项核对。点 SQL 最多返回一行，必须明确完成结果消费。事实绑定同一事务的前序 statement，引用真实累计 serverRow 序号，并且必须记录在相应实际返回行之后。写的前驱只作为独立元数据，不伪造成 SELECT。

零行可以表示不存在、owner 不符或到期条件失败。没有完整的同语句来源时一律保留缺口，不生成负读，不把失败 guard 当作已证明的点读。失败 SQL、未知模板、错误返回类型、未消费结果以及缺失来源也不能获批。

业务键使用现有核心标识符约束，安装域固定为 1–128 个已声明键；只支持单个受控 dislock 安装，schema 必须为 `mtw_provenance_*`。扩展到其他表形状、删除、任意谓词和自动 SQL 识别需要另行设计。

## 安装、来源与真实效果账本

核验不会读取 `verified:true` 之类标志来放行。它逐项比对：

1. 实际 PostgreSQL 18 serverVersion、关系 OID、安装 nonce 与 marker 的一致性。
2. BEFORE、AFTER、predecessor 的完整实际 pg_proc.prosrc，逐字匹配冻结模板；同时核对真实函数 catalog 的 namespace、name、SECURITY、volatility、search_path、参数数、返回类型和语言。
3. 触发器 OID、函数 OID、事件位、enabled、参数与固定 triggerDefinition。
4. 实际业务表及四个元数据表的 relation、columns、PK/UNIQUE/NOT NULL 约束、完整 user trigger 列表和 indexCount。
5. 外键、rewrite rule、CHECK/EXCLUDE、自定义或复合类型、生成列、表达式/部分索引、继承、非 B-tree/custom operator 和不确定排序规则等风险计数全部为零。
6. 成功 BEGIN → ACCESS EXCLUSIVE 锁 → catalog → 初始快照 → COMMIT 的原始初始化观察；初始 presence/owner/expiry/token 完整覆盖声明域，并与原 snapshot token 一致。
7. 最终 actual effectLedger 与每个已提交、未被保存点撤销的实际写一一对应，包含同一事务的中间版本。已中止或已撤销的效果不应出现在最终数据库账本，但它们的原始 SQL、OLD/NEW 与交付观察仍保留。

BEFORE INSERT 候选不等于实际 INSERT：ON CONFLICT 的 guard 失败时可能留下候选而没有业务效果。因此候选前驱只证明其候选身份，不能代替 AFTER 实际效果账本。核验器从不使用 UUID 大小、identity、自增值或客户端 ACK 顺序推断提交顺序。

本地纯 MoonBit SHA-256 将 raw source 与声明摘要绑定，并重算完整生成 DDL 的 Python ASCII JSON 摘要；标准向量和真实采集文本摘要均有回归。摘要只是字节绑定，不是数据库认证。所有结论仍以原始采集事实真实、声明 writer 范围封闭，以及运行窗口没有未观察的 DDL/触发器禁用等部署前提为条件。

## 时间规则

只接受实际 aware datetime 的类型编码：

```json
{"captureType":"datetime","value":"2026-10-21 11:41:18.596548+08:00"}
```

按 Gregorian 日历与 UTC 微秒比较，保留时区偏移和最多六位小数，接受年份 1–9999、分钟级 offset；拒绝 naive、额外精度、非法日期与未支持的特殊值。不会按时间字符串的字典序比较到期条件。

TTL 接受有限 JSON Number，绝对值不超过一年秒数。对于固定的 `INTERVAL '1 second'`，按 PostgreSQL 18 interval_mul 的 float8 微秒乘法及 nearest-even 取整核对。其他 numeric 编码或超出额度的值保留缺口。实现依据 [PostgreSQL 18.6 的 interval_mul 源码](https://github.com/postgres/postgres/blob/REL_18_6/src/backend/utils/adt/timestamp.c)；本模块不推广为任意 interval/月/天或时区运算解释器。

## 本轮实际验证及快照

80 项快照的 focused JS 测试实际运行 80/80 通过，JS deny-warn check 也通过。覆盖固定 SQL、参数/owner/TTL、完整返回前缀、source identity、同语句先后顺序、初始化与 catalog 篡改、异常/零行保守拒绝、aborted 效果、同事务中间版本和诊断/分析覆盖隔离。

其中七项是下列**既存真实 PostgreSQL 采集的离线重核**；测试嵌入原始 capture 文本并校验其 SHA-256，未重新运行数据库，也未改原件：

| 场景 | 当前诊断 | 原 capture SHA-256 |
| --- | --- | --- |
| schedule-and-server-clock | 固定 SQL/安装/实际账本可核对 | 236ab50e0b4864becd46e5314d693012ce83221ba41de59135aed554e5aaf07f |
| acquire-heartbeat-cleanup | 固定 SQL/安装/实际账本可核对 | 53ac038833b07a0f348757aeb411034e127b44965b0bbe5472e8056e0c89b8b2 |
| body-exception-cleanup | 固定 SQL/安装/实际账本可核对 | 50b337a0482002b9c4fe8645c8c09ba36878e0562366ddb0ca3de2ef46d073f5 |
| busy-acquisition | 零行缺完整来源，不授予集合 | e5219b6d78e610721b6b3a5eb5654e2ba024f7bfdcd73ed0c0fbf41e7136fe7a |
| heartbeat-reconnect | 失败/来源缺口，不授予集合 | d5e342982416e81824cd2c94182fca0e1cf6572eee14335e0081dd168a4d8bfc |
| ownership-lost | 零行/来源缺口，不授予集合 | 9469c2fcf81e2b6c2ded732ff7388cb043df6837e0683a09a8e7377760124f98 |
| aborted-commit-response | 无固定 SQL profile，不授予集合 | 972f10c803aa1239fa4d59c2aebf8741c8eef2ed2799b1ad04fef0f76bc4b831 |

原件位于 `verification/business/dislock/v3-647afacfcbe14586b46714bac34c8f30/<scenario>/capture.json`。当前所有七份正常分析仍为 inconclusive/history:null；上述三个局部核对通过不改变这一事实。

首轮本地 SQL 测试曾出现正例未获批：66 项中 65 通过、1 失败，原因是模板替换错误地只处理首个 schema 引用。改用 replace_all 后 66/66 通过；没有放松 source/template 比较。随后增加真实采集与诊断顺序等案例达到 76 项；该版本曾构建并交给独立审查。之后又增加四项语义案例，成为当前 80 项源快照。**76 项构建不能作为 80 项源码的构建验收**；两次快照与已有失败记录均保留，后者必须重新构建绑定。当前文档不宣称后续独立审查、全目标回归、完整真实业务生命周期或性能验收已完成。

独立审查随后在冻结的 59 项篡改中发现：将 snapshot.consistent 改为 false 后仍能取得完整局部来源集合。普通分析当时仍为 inconclusive，这不构成已输出假 consistent，但不满足完整来源 profile 的前提。原失败收据保留在 `verification/v3/dislock-sql-independent-2026-10-21T03-58-09-440Z/receipt.json`，SHA-256 为 `fdc14b2d6b769ec897b9fe5d51b50538f5e156cc7624bc4335cf598242218814`。

按该审查修复后，完整集合必须先满足：首事件为 consistent=true 的 snapshot、其原始 seq 为 1、全部观察 seq 连续且完整、exclusiveWriters=true、原始 gaps 为空。新增七项本地回归，源码测试数变为 87；本段落盘时尚待 root 统一编译和独立重核，不把旧 80 项构建当作新 87 项源码的验收。冻结的 59 项独立预期与失败原件不变。

后续退出条件：独立实现核对真实七案及篡改、统一构建绑定当前源码、全目标正确性回归、来源闭包与预算验证。只有这些完成后，才讨论按具体事件集合消除对应 SQL 覆盖缺口。稳定发布和官方审核另行记录。
