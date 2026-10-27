# v0.3.0 入口

运行 `node examples/mlflow-http-roundtrip.mjs` 可在无需 PostgreSQL 的情况下核对并重放同一 623 键真实 HTTP 案例的两份原始采集。输出保留原生 `40P01`、来源缺口和模型无法判定。新执行完整实验请按下列步骤准备固定环境；下文的候选／交付状态是原始证据准备时的记录，最终验收与发布状态另见 `verification/releases/0.3.0/`。

# MLflow 原生 HTTP 执行故障案例

这是后续稳定版／**v0.3.0 候选**的实验入口与原始证据说明。开发目录的 `v029` 名称仅为工作目录暂名，不代表一个已经公开的版本。当前候选尚未因本目录新增内容而完成独立交付审查或发布。

该案例通过原生 MLflow HTTP 路由 `/api/2.0/mlflow/runs/log-batch`，观察其实际 SQLAlchemy／psycopg／PostgreSQL 调用与原始 HTTP 返回。它支持复现一个执行故障并对比修复前后行为；这里的采集始终是 **diagnostic-only**，不会把原始 SQL 错误自动变成事务模型事实、G2 反例或数据库隔离级别认证。

## 已实际完成的范围

原始预注册计划有 30 个种子，每个种子依次运行 before、fixed，共 60 次真实 trial；两侧使用完全相同的 1000 个 metric 请求内容与调度策略，没有选择种子、campaign 的自动重跑或缩减请求；客户端重试为 0，上游内部原有重试语义不改。实际平台是 Windows x86_64、Python 3.12.5、PostgreSQL 18.6，依赖由 71 项带 SHA-256 的 lock 固定；环境另有 pip，共 72 份安装元数据。SQLAlchemy 为 2.0.55、psycopg 为 3.3.6。上述是这轮实际运行环境，不是跨平台兼容声明。

- before：30 次 trial 各有一次原生 `40P01`，与同一个业务 worker 最终 HTTP 503 对应，另一个 worker 为 HTTP 200。独立审查还将原始 PostgreSQL server.log 的 30 个 backend PID 与 trial 中的驱动错误逐项匹配。
- fixed：30 次 trial 的全部原 SQL 中均没有 `40P01`，两 worker 均收到 HTTP 200。每轮最终原生 GET 与最终 SQL 的 1000 个 metric 逐项一致，均为 `value=2.0`、`step=2`、`timestamp=seed*10+2`。
- 原始独立审查未参与 HTTP／控制器实现，核了完整 60 次 trial、9 个实际 runner 文件、34 个实际 collector 源文件、两侧各 5979 个上游源码文件与原归档、依赖身份和原始日志。其 290732 项检查通过，最终对该轮 owned PG 的只读 `pg_ctl status` 返回 3，且 `postmaster.pid` 不存在。

这是一轮 30 对 campaign，不等于三个独立 campaign 重复。已完成下面单独记录的 16 候选真实缩减；它保留 oneMinimal=false，不声称最终案例最小。没有执行或声称 Linux HTTP、正式性能、生产能力、完整隔离模型、人工／主办方认可或本候选公开发布通过。每 trial 的耗时和父进程总耗时只是原执行记录，不能作为正式性能结果。

## 实现与上游身份

`experiments/faults/mlflow_http/` 中九个文件按实际执行字节复制，未改算法、预算、lock 顺序或重试语义。`reducer.py` 也保留实际 runner 的原文件；原文件未改；本轮有下面单独记录的预算内真实缩减，但不代表 one-minimal。`requirements.lock` 是本轮实际 lock 的原字节。

| 角色 | 固定上游 Git 提交 | 原始官方归档 SHA-256 |
| --- | --- | --- |
| before | `c2dcdb96c62c75f35af3f28b5d493c0cf139a856` | `7a9f83aa0da2cefcc1f9bfbb0aef115997f44e6b511ec255ddeb9f8fc7023fcf` |
| fixed | `40c146a23518813e8488e55fc9752e08c3a8bad5` | `a13812814f3c47684602c6e222af74e4d1f1eb14e4082c76347395d4ec09289f` |

原始来源是 [MLflow 官方仓库](https://github.com/mlflow/mlflow)；保留的 manifest 引用[上游修复 PR 24941](https://github.com/mlflow/mlflow/pull/24941)。本指南依据已保留的官方获取记录与实际归档字节，不声称本次交付重新进行了网络认证。完整文件表、原生路由绑定、版本和每项字节数／SHA 在 `experiments/faults/mlflow_http/upstream-manifest.json`。

`upstream-licenses/MLflow-LICENSE.txt` 为两个固定提交相同的 Apache-2.0 原始许可证。逐项检查了两份原归档，各有 10781 个成员，根目录均没有 `NOTICE`、`NOTICE.txt` 或 `NOTICE.md`；`NOTICE-PROVENANCE.json` 是这一事实的派生说明，不是上游 NOTICE。这里没有分发完整上游源码或依赖 wheel。另行获取完整源码和依赖时，应保留其各自原始许可及适用通知，不能将此单份许可证当成所有依赖的许可清单。

## 公共原件与独立审查边界

`verification/faults/mlflow-http/full30/` 保留原 plan／case／RESULT、9 个执行 runner、34 个 producer-source、每次 trial 的 case／PROCESS／已存在的 sanitized stdout、stderr，以及 `server/` 的完整原始封印闭包。`producer-source` 是本轮实际导入采集器的来源快照，不会替换下一版当前实现。原 PG 日志逐字节复制为 `full30/postgres/server.log.original.txt`。

`ORIGINAL-FILES-MANIFEST.json` 逐个列公共原件的逻辑来源、角色、字节数与 SHA-256；`PUBLIC-COPY-OFFLINE-VERIFY.json` 是交付准备时对副本的离线检查。原始日志、收据、capture、journal、索引和事务索引文件未修改。诊断 metadata 中的 `actualDatabaseExecution:false` 表达该诊断格式本身不认证数据库真实性；外层 HTTP 收据的真实执行声明与完整性校验分别保留，不回填诊断缺口。

`independent-review.derived.json` 只是既有独立报告的精简派生摘要。外部完整原报告 SHA-256：

```text
db2d90fab5647303b496082bc40e4f5600a416e416992b752c25365a66461c08
```

完整独审原件仍在外部原目录保持原字节。本次复制、文档和清单检查由交付准备者完成；摘要不冒充一份对本次新改动重新独立签署的报告。`DELIVERY-STATUS.json` 记录预算内缩减已独审及同一最终案例 fixed 三次实际执行；本次新控制器／执行没有额外独立签名，正式性能与公开发布仍未验证。

导出仅采用白名单。连接文件、口令、PGdata、temp、venv、wheels、巨型上游 tar、父进程日志、未被当前闭包需要的诊断 progress／stack 和完整独审全文均未纳入。上游完整源码、解释器、依赖环境与私有 PG 实例仍是新执行的外部输入；不是一个无需环境准备即可运行的自包含二进制包。隐私扫描检查实际私有口令的 raw／URL 形式，以及个人 home 的斜杠、JSON、Unicode、URL 和 UTF 编码变体；命中时应停止导出并保留原件，不能编辑原件后仍沿用旧 SHA。

## CLI 复现步骤

以下命令使用 **PowerShell 7+**，用于在 Windows 上进行新的显式执行，**不会由本次交付准备自动执行**。使用仓库外一个全新工作目录和自己的全新 loopback-only PG 实例。需要足够空间容纳两份原归档、展开源码、环境和新证据；不要复用既有业务库、既有证据目录或已存在的计划目录。

### 1. 准备固定环境与官方源

使用实际已验证的 Python 3.12.5 Windows x86_64。以下路径只是可替换的示例，均不应放入 Git。

```powershell
$ErrorActionPreference = 'Stop'
$Work = 'C:\mtw-http-work-new'
$Repo = (Get-Location).Path
$Module = Join-Path $Repo 'experiments\faults\mlflow_http'
New-Item -ItemType Directory -Path $Work -ErrorAction Stop | Out-Null
python -c 'import sys,struct; assert sys.version_info[:3] == (3,12,5) and struct.calcsize("P") == 8'
if ($LASTEXITCODE -ne 0) { throw 'Python3.12.5 x86_64 required' }
python -m venv (Join-Path $Work 'env')
if ($LASTEXITCODE -ne 0) { throw 'new environment failed' }
$Py = Join-Path $Work 'env\Scripts\python.exe'
& $Py -m pip install --require-hashes -r (Join-Path $Module 'requirements.lock')
if ($LASTEXITCODE -ne 0) { throw 'locked dependency install failed' }
& $Py -m pip check
if ($LASTEXITCODE -ne 0) { throw 'dependency check failed' }
```

在不携带无关 API／账户凭据的独立终端中工作。下载以下两份官方固定提交归档，确认各自 SHA 后才解包；不要拿主分支或仅同版本号的代码代替。

```powershell
$Upstream = Join-Path $Work 'upstream'
New-Item -ItemType Directory -Path $Upstream -ErrorAction Stop | Out-Null
$BeforeArchive = Join-Path $Work 'before.tar.gz'
$FixedArchive = Join-Path $Work 'fixed.tar.gz'
Invoke-WebRequest 'https://codeload.github.com/mlflow/mlflow/tar.gz/c2dcdb96c62c75f35af3f28b5d493c0cf139a856' -OutFile $BeforeArchive
Invoke-WebRequest 'https://codeload.github.com/mlflow/mlflow/tar.gz/40c146a23518813e8488e55fc9752e08c3a8bad5' -OutFile $FixedArchive
if ((Get-FileHash -LiteralPath $BeforeArchive -Algorithm SHA256).Hash.ToLowerInvariant() -ne '7a9f83aa0da2cefcc1f9bfbb0aef115997f44e6b511ec255ddeb9f8fc7023fcf') { throw 'before archive differs' }
if ((Get-FileHash -LiteralPath $FixedArchive -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'a13812814f3c47684602c6e222af74e4d1f1eb14e4082c76347395d4ec09289f') { throw 'fixed archive differs' }
New-Item -ItemType Directory -Path (Join-Path $Upstream 'before'),(Join-Path $Upstream 'fixed') -ErrorAction Stop | Out-Null
tar -xzf $BeforeArchive -C (Join-Path $Upstream 'before') --strip-components=1
if ($LASTEXITCODE -ne 0) { throw 'before source extraction failed' }
tar -xzf $FixedArchive -C (Join-Path $Upstream 'fixed') --strip-components=1
if ($LASTEXITCODE -ne 0) { throw 'fixed source extraction failed' }
```

运行前逐个验证 manifest 所列原始文件。这个纯检查不连接数据库：

```powershell
& $Py -I -B -c 'import json,sys; from pathlib import Path; mod=Path(sys.argv[1]); sys.path.insert(0,str(mod)); from protocol import check_sources; manifest=json.loads((mod/"upstream-manifest.json").read_bytes()); print(check_sources("before",Path(sys.argv[2])/"before",manifest)); print(check_sources("fixed",Path(sys.argv[2])/"fixed",manifest))' $Module $Upstream
if ($LASTEXITCODE -ne 0) { throw 'frozen upstream source check failed' }
```

### 2. 创建私有的新 owned PG 实例

下面需要 PostgreSQL 18 工具，原运行使用 18.6。`initdb` 目标必须不存在；只对本次新建路径执行 start／stop。`connection.json` 与 password.txt 均位于仓库外，不要显示、提交或随证据导出。

```powershell
$PgBin = 'C:\postgres18\bin'
$Private = Join-Path $Work 'private'
$Data = Join-Path $Private 'data'
New-Item -ItemType Directory -Path $Private -ErrorAction Stop | Out-Null
$Password = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(24)).ToLowerInvariant()
$Utf8 = [Text.UTF8Encoding]::new($false)
[IO.File]::WriteAllText((Join-Path $Private 'password.txt'), $Password + "`n", $Utf8)
$Listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,0)
$Listener.Start()
$Port = $Listener.LocalEndpoint.Port
$Listener.Stop()
& (Join-Path $PgBin 'initdb.exe') -D $Data -U mtw_http --locale=C --encoding=UTF8 --auth-host=scram-sha-256 --auth-local=trust ('--pwfile=' + (Join-Path $Private 'password.txt'))
if ($LASTEXITCODE -ne 0) { throw 'new owned initdb failed' }
[IO.File]::AppendAllText((Join-Path $Data 'postgresql.conf'), "`nshared_buffers='64MB'`nmax_connections=32`nlog_min_error_statement=error`nlog_error_verbosity=verbose`n", $Utf8)
$Connection = @{host='127.0.0.1';port=$Port;dbname='postgres';user='mtw_http';password=$Password} | ConvertTo-Json
[IO.File]::WriteAllText((Join-Path $Private 'connection.json'), $Connection + "`n", $Utf8)
```

### 3. 注册并执行新 campaign，始终清理 owned PG

`prepare-plan` 先写 30 个原种子及其原请求哈希。`run` 在显式 `--execute-real-http` 下执行真实服务和数据库操作，依次产生 60 个 trial；每 trial 原预算 150 秒，原子目录写入拒绝复用。不要通过删除失败 trial、修改预算或换 seed 来替代一次结果。

```powershell
$PlanDir = Join-Path $Work 'preregistered30'
$Campaign = Join-Path $Work 'campaign'
& $Py -I -B (Join-Path $Module 'campaign.py') prepare-plan --output $PlanDir
if ($LASTEXITCODE -ne 0) { throw 'new plan failed' }
try {
    & (Join-Path $PgBin 'pg_ctl.exe') -D $Data -l (Join-Path $Private 'server.log') -o "-h 127.0.0.1 -p $Port" -w start
    if ($LASTEXITCODE -ne 0) { throw 'owned PG start failed' }
    & $Py -I -B (Join-Path $Module 'campaign.py') run --execute-real-http --plan (Join-Path $PlanDir 'plan.json') --connection-file (Join-Path $Private 'connection.json') --upstream-parent $Upstream --project-root $Repo --output $Campaign --python-before $Py --python-fixed $Py --manifest (Join-Path $Module 'upstream-manifest.json')
    if ($LASTEXITCODE -ne 0) { throw 'campaign failed; keep all original evidence' }
} finally {
    $PidPath = Join-Path $Data 'postmaster.pid'
    if (Test-Path -LiteralPath $PidPath) {
        $PidLines = @(Get-Content -LiteralPath $PidPath)
        if ($PidLines.Count -lt 2 -or [int]$PidLines[0] -le 0 -or [IO.Path]::GetFullPath($PidLines[1]) -ine [IO.Path]::GetFullPath($Data)) {
            throw 'refuse stop: PID does not identify this owned data directory'
        }
        & (Join-Path $PgBin 'pg_ctl.exe') -D $Data -m fast -w stop
        if ($LASTEXITCODE -ne 0) { throw 'owned PG stop failed' }
    }
    & (Join-Path $PgBin 'pg_ctl.exe') -D $Data status
    if ($LASTEXITCODE -ne 3 -or (Test-Path -LiteralPath $PidPath)) { throw 'owned PG stop unconfirmed' }
}
```

实际 campaign 只通过 `server_worker.py` 启动原生完整 MLflow app，源文件在执行前后按 manifest 读取核验；调度控制发生在 SQL 事件回调旁，未抽取／改写上游函数、锁顺序或重试语义。新执行的 collector 来自 `--project-root` 指定仓库；若它与本轮 `producer-source` 不同，应保留新的身份与证据，不能把本轮结果冒充新代码结果。

### 4. 离线校验已经保留的公共副本

下面只验证现有原始观察，不启动服务或数据库。验证器返回的 `valid` 表示闭包与判定重算有效；仍须检查 `passed`，不能把一个有效的“不复现”结果写成通过。

```powershell
$Evidence = Join-Path $Repo 'verification\faults\mlflow-http\full30'
foreach ($Seed in 1297372928..1297372957) {
    foreach ($Label in 'before','fixed') {
        $Replay = & $Py -I -B (Join-Path $Module 'verify_evidence.py') (Join-Path $Evidence "campaign\$Seed-$Label\server") --manifest (Join-Path $Module 'upstream-manifest.json') | ConvertFrom-Json
        $VerifierExit = $LASTEXITCODE
        if ($VerifierExit -ne 0 -or $Replay.valid -ne $true -or $Replay.passed -ne $true) { throw "retained evidence invalid or predicate not passed: $Seed-$Label" }
        if ($Label -eq 'before' -and $Replay.result.faultPredicate -ne $true) { throw "before predicate not reproduced: $Seed" }
        if ($Label -eq 'fixed' -and $Replay.fixedBehaviorChecked -ne $true) { throw "fixed behavior not passed: $Seed" }
        $Replay
    }
}
```

离线校验能复核保留字节、原 HTTP／SQL 故障谓词和 fixed 最终行为，不认证远端服务器或收集器本身的真实性，不消除 `initialization_unproven`、`source_unsealed`、`diagnostic_only` 等原始缺口。本轮原独审全文与未公开的大型／私有环境仍由外部原件保留。

## 已完成的预算内缩减与同案例 fixed 回归

原始 1000-key 输入按最多 16 个候选、每个候选三次真实 before trial 执行，包含 baseline 和最终复验，共 48 次。只删除原 metric key／请求单位，没有改保留请求的顺序、值、step 或 timestamp；被接受的路径是 1000 → 749 → 623。最终案例原 SHA-256 为 `9fddccaffd9d300ab23c1cd5b1bdd1d5f6075a75eabdca13a8a2ec36f127d69d`，同一个案例最终三次均复现。

必须区分单 trial 与三次组合谓词：48 次实际为 **16 次复现、32 次完整未复现、0 unknown**；候选组合为 4 组全部三次复现、12 组未全部三次复现。check-005（另一个623-key集合）是 `[false,true,false]`，check-011（560 keys）是 `[false,false,true]`，check-012（560 keys）是 `[true,false,true]`。因此组合的 `not-reproduced` 不等于其中每次都没有死锁。完整16×3真实矩阵见 `verification/faults/mlflow-http/reduction-16-candidates/independent-review.derived.json`，原始CHECK、48份原HTTP／SQL与PG日志完整保留。

`oneMinimal=false`；最终合法单删单位625，完成0，unknown单删0。预算内缩减没有证明全局最小或单删最小；更小候选中也有偶发复现，不能把623这个数量说成必要边界。原独审报告保持外部原字节，SHA-256 为 `2476a45d6c1732b7ca22d3473fe57d3273f8eab3e574d35d6a2bb4f9fe696685`。

随后使用审过并冻结的独立控制器，在另一个全新 owned PG 上运行 **三次 fixed**，输入严格是同一 SHA `9fddccaffd9d300ab23c1cd5b1bdd1d5f6075a75eabdca13a8a2ec36f127d69d`，不是只比较623这个数量。三次均双200、原SQL无40P01，最终GET／SQL的623个metric值与该不可变请求一致。它们与 before 最终三次分别存储；fixed 原件位于 `verification/faults/mlflow-http/final623-fixed-three/`。原每trial150秒预算、9runner与34collector均保持，未挑选或自动重跑；控制器／输入case／原缩减报告前后SHA不变，owned PG最终status3且pid不存在。

这一段 fixed 结果是执行已审控制器的 producer 收据及副本校验，不额外冒充对该新控制器／执行的独立签名。完整48次缩减的独审、这3次fixed执行、原full30独审分别标明角色与原SHA。全部仍为Windows实验证据，不扩张为LinuxHTTP、正式性能、完整事务模型、生产能力、正式发布或主办方认可。
