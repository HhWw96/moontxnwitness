# v0.1.5 关系能力独立技术审查

正式 v0.1.5 审查 **9/9 组通过**，原始收据为 `actual-v015/run/receipt.json`。源码、运行时与独立给定的构建指纹前后相同；未修改核心、输入或预期来消除差异。此轮只离线执行实际核心和读取保留数据库证据，没有编译、连接数据库、安装依赖、下载或测量性能。

- 170 份关系边界与 71 份旧列表历史符合冻结预期，固定 SDK 与本版通用入口逐字段一致；原有非法诊断的打包拒绝保持。
- 4 个事务缩减为 P/A/B 三个事务，仅删 N；全部三次单删均核验。删 P 缺来源而无法判定，删 A 或 B 则可串行执行。来源缺口、未知提交、容量和预算不足保持可见，结论/模型/预算/来源即使重新计算摘要仍不能伪造。
- v0.1.4 实际 PostgreSQL 的 3 个寄存器胶囊和 120 个列表胶囊均由实际 v0.1.5 核心成功重放。
- 本轮 8×20 个真实关系场景全部核验：800 份原始文件与 800 份模型文件逐字节绑定，另独立检查 SQL 单元格、完整查询、写影响、保存点实例、服务器提交/回滚确认、存活写账本及新报告和胶囊。
- 冻结独立关系解释器核对 335 份输入全部通过（170 边界、5 个缩减前后/单删输入、160 个新数据库历史）；这些计数与其他检查重叠，不相加称作独立历史总数。

`candidate-v014/` 原样保留早期候选阶段的独立审查代码、完整可重放输入、通过结果、首失败及脱敏记录。该阶段使用 **v0.1.4 运行时**，与上述实际 v0.1.5 收据分开标示。168 份文件逐字节核对，原闭包摘要保持；详见 `candidate-copy-record.json`。准备期尚未运行的记录和带 `PENDING` 的旧预期副本作为历史保留，不表示当前仍未执行。

`check.mjs`、`raw-review.mjs` 和 `oracle-batch.py` 是正式审查的可重跑入口。`expected.actual.json` 绑定独立给定的实际构建和本轮 raw/同级 `-model` 两份数据库收据。脚本先验证版本、源码指纹及五份运行时文件，再加载核心。在项目根目录运行：

```powershell
node ./verification/releases/0.1.5/relation-independent/check.mjs --repository . --expected ./verification/releases/0.1.5/relation-independent/expected.actual.json --output-root ./artifacts/r15-actual
```

输出使用短路径父目录，每次创建新目录；不得把完整仓库再嵌套到很深的输出目录。需要已有 Node 24、Python 3，`MTW_PYTHON` 可指定现有 Python。

`reproduction/repository/` 包含完整实际执行输入副本：94 份源文件、5 份实际运行时、本轮 raw/model 文件、旧胶囊与必要收据。`actual-input-copy-bindings.json` 绑定每份原件与副本；`closure-manifest.json` 绑定整个公开审查目录。将完整审查目录复制到短路径后，也可直接用该副本运行：

```powershell
node ./check.mjs --repository ./reproduction/repository --expected ./expected.actual.json --output-root ./review-output
```

该完整副本已经实际复跑，九组、335 个解释器输入及全部数据库/旧胶囊检查再次通过，原始结果另存 `actual-v015/fresh-replay/`，未借用作者工作区输入。本轮正式语义审查没有失败；闭包整理器曾将既有公开源码中的固定 owned-DB 临时目录安全配置误报为个人路径，首失败实现和说明保留。`privacy-actual.json`/`privacy-final.json` 仅对该源文件的绑定摘要和唯一固定配置作精确例外，其余用户目录、个人工作区与凭据仍禁止复制；源码字节未改，离线审查不会执行该数据库启动辅助程序。

数据库只离线复核已有证据；不从响应顺序推断提交顺序，不将写返回结果当作 SELECT，不声称任意 SQL 自动采集或完整隔离分类。技术审查由实现作者之外的独立 AI 执行，不代表真人验收、生产采用、赛事审核或获奖。
