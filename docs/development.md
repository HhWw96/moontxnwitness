# 构建、验证与发布

## 环境与构建

验证环境采用 MoonBit `v0.10.14+7d59c7ec9`、Moon `0.1.20260920`、Node 24 和 Python 3.12；具体补丁版本、操作系统和实际执行目标随每份收据保存。其他工具链需另行验证。运行便携 SDK/CLI 需要 Node ≥20；源码重建还需要外部 MoonBit 工具链。

核心不依赖 npm 安装或第三方 Mooncakes 包。可选数据库驱动、ORM 编译依赖及固定摘要见各自 requirements。`.local-toolchain.json`、凭据、数据库目录和环境缓存不进入公开包。

```powershell
npm run build
npm test
npm run demo
npm run postgres:verify
npm run package
```

`npm test` 检查格式与目标类型，运行 JS/Wasm GC/Wasm 核心及解析差分、独立串行重放、环证据、缩减、CLI、采集和模型 SDK 套件。各项数量取当前 `verification/summary.json` 的 `coreTestsPerTarget`、`executedTargets` 及子套件收据，不在文档硬编码旧计数，也不把重叠断言累加为不同业务场景。独立解释器实际重放整个事务，不调用生产依赖推导。

Windows 默认只对 Native 检查类型；支持 C 工具链的环境可运行 `node scripts/test.mjs --all`。Linux CI 实际执行 Native，是否执行及是否通过以该版本精确源码提交的 Actions 和收据为准；checkedTargets 与 executedTargets 分开记录。

## 数据库与性能

稳定18默认生产解析器与已发布17版完整文件逐字节一致；实验 helper 仅在白盒测试文件，原九项断言保留完整后缀。ASCII 复用候选首轮正式对照的正确性通过，但性能控制未满足，故保留试验并回退；不能把原5999/5b63试验或数据审查通过作为新81b稳定18或本版性能达标。稳定版本未进行新性能测量时保持未执行。

`npm run postgres:verify` 使用相同便携演示入口并保存版本化证据。按[数据库说明](postgres-capture.md)使用专属 PostgreSQL 18 测试环境和固定可选驱动。版本列采集、固定键存在性及其它受影响入口各有实际数据库检查；原 SQL、返回结果、提交/回滚应答、原始记录和模型输出分别保留。缺少数据库或未执行不记成通过。

`npm run benchmark` 运行专门的基线/协议入口，涉及重建和独立进程测量。完整报告比较应保持同机、工具链、输入和输出范围；标准协议为5次预热、30样本、3批，并记录环境、P95、峰值内存和原始样本。`--quick` 是开发检查；只测一个子组不能支持完整分析收益。旧版本数字仍属于其对应实现，不能代替当前版本的正式对照。没有实际样本就不填写新提速、RSS或采集开销结论。

## 全新目录与公开下载

`npm run package` 创建 source/portable ZIP 和版本摘要，在全新目录消费两种包。源码包用外部工具链重建；两者实际运行 CLI/SDK、旧证据、各模型示例、环解读及执行诊断包，核对随包输入与输出摘要。数量和逐项结果取 `verification/package.json`，其中 freshConsumerChecks 必须对应实际 checks。包内包含当前编译核心和依赖许可，不包含 Node、Python、PostgreSQL 或运行机私有配置。

发布前检查实际源码/运行时指纹、完整回归、适用数据库、独立技术复核、两个包的新消费者及精确提交 CI。发布脚本保留既有 scoped gate；本版稳定范围见[支持矩阵](stable-scope.md)，旧路线中尚未完成的全部业务/模型/性能目标不再共同绑定稳定发布。

GitHub 和 Mooncakes 发布后继续匿名下载、核对发行摘要和实际上传的注册表 ZIP，并从新项目安装运行。`python scripts/verify_publication.py VERSION` 使用对应版本的原验证流程；公开 Linux 手动工作流可在受限本机网络之外执行相同逻辑，源码提交与工作流提交分别绑定。记录失败与重试，不能仅从“上传成功”推定公开验证通过。

实际测试数量、跳过原因、独立审计原标签、旧包与失败记录均保留。公开发布、用户验收、生产采用及官方审核是不同状态；自动检查不能代填人工或官方回执。原历史计划见[固定原文](remaining-execution-plan-2026-10-21.md)，当前范围与后续安排分别维护。

## Windows 本地验证的输出编码与临时目录

验证器按 UTF-8 接收 Python 子进程输出。使用中文用户名或旧控制台编码的 Windows 环境，请先启用 Python UTF-8，避免测试已生成收据而汇总阶段无法按原路径读取。固定 ORM／驱动测试仍使用 `examples/orm-requirements.txt` 的版本；调整环境不能替代原有测试。

在目标工作盘的检出目录执行：

```powershell
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$taskTemp = Join-Path (Get-Location) 'artifacts\test-temp'
New-Item -ItemType Directory -Path $taskTemp -Force | Out-Null
$env:TEMP = $taskTemp
$env:TMP = $taskTemp
npm test
```

环境变量只影响当前终端及其子进程。建议使用英文临时目录，并在运行前核对当前 Python 已安装固定 psycopg、SQLAlchemy 和可选编译依赖。未完成的执行、路径编码失败和环境修正应保留记录，不标记为完整回归通过。
