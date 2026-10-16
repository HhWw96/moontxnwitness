# 构建、测试与发布

## 可重复环境

本机：Windows x64、Node 24.13.0、Python 3.12.5、Moon 0.1.20260920、moonc v0.10.14+7d59c7ec9。CI 固定同一 MoonBit 编译器、Node 24 和 Python 3.12，实际环境随每份记录保存。其他工具链需要另行验证。

源码不依赖 npm 包或第三方 Mooncakes 包。安装 MoonBit 后，让 moon 可运行或设置 MOON_HOME。本机 .local-toolchain.json、凭据、数据库数据、虚拟环境和临时输出不进入交付包。

```powershell
npm run build
npm test
npm run demo
npm run benchmark
npm run postgres:verify
npm run package
```

`npm test` 检查格式、四目标类型，在 JS / Wasm GC / Wasm 各运行 94 项核心测试，然后执行 2,542 份解析差分、10,320 份独立串行重放、6,373 份环证据、旧/新缩减核对和 75 项 CLI/SDK/导出/回放检查。独立 oracle 枚举整个事务的串行排列并实际重放，不复用生产依赖推导。更大搜索案例另有 8 份独立可验证样本。

Native 在 Windows 本地只检查类型；本机没有配置 C 编译器。Linux CI 另外实际执行相同 94 项 Native 核心测试。已安装支持的 C 编译器时可运行 `node scripts/test.mjs --all`。实际远端运行证据以各版 publication.json 和对应 Actions 为准。

## 性能和真实数据库

`npm run benchmark` 会先重建，再自动准备固定摘要的公开 v0.0.6 基线。固定输入在 verification/fixtures/v006-comparison；计时、环境、峰值内存、输出大小和阶段数据在每版目录。完整协议是 5 次预热、30 次测量、3 批交替独立进程。默认推荐 balanced，可显式 `--profile compat`。`--quick` 或 `--group reduction` 用于开发，不能满足全部性能验收。每次测量保存带时间戳的独立记录，标签文件仅为最近结果的便捷入口。

`npm run postgres:verify` 使用与便携包相同的 postgres-demo 入口，并额外保存版本化证明。按 [PostgreSQL 说明](postgres-capture.md) 安装 hash 固定的可选驱动、配置专属测试数据库；缺少条件明确未执行。独立 PostgreSQL 工作流实际运行 20+20 轮并保存服务器日志。此前失败的 v0.0.11 工作流记录和修复源码核对单独保留。

## 全新目录交付检查

`npm run package` 创建 source / portable ZIP 和版本专属 SHA256SUMS，然后在新目录解压两种包：源码包用外部 MoonBit 工具链重建并运行 JS 核心测试；两者验证 CLI、SDK、示例、导出、旧证据、v2 回放、缩减、一键演示、缺失数据库明确未执行，以及随包真实 PostgreSQL 的三个 capsule。当前为 50 项全新消费检查。

运行包需要 Node ≥20；真实数据库采集另需 Python 和可选驱动。不包含 Node、Python、PostgreSQL 或原生可执行文件。包内有编译 MoonBit 核心与标准库许可证。打包记录不递归记录自己的 ZIP 摘要；既有目录与文件不会被重置。

## 发布与外部状态

发布脚本绑定 HhWw96，先推送已测试的候选提交，等待该提交的 Windows/Linux、Linux Native 和独立 PostgreSQL CI 实际通过，再上传 Mooncakes、推送版本标签并创建 GitHub Release。最后匿名下载公开 ZIP、核对摘要和实际运行，并核对 Mooncakes 上传/下载字节，在无 workspace 覆盖的新项目从注册表安装后运行 JS / Wasm GC 各 8 项接口测试。

`python scripts/verify_publication.py VERSION` 可重复公开验收。只读 CI 和证据下载需要可访问 GitHub 的已登录 GitHub CLI；匿名 ZIP 下载本身不使用认证。所有失败记录保留。仅当历史工作流配置需要修复时，分别记录工作流提交和实际检出的不可变发布源码；源码 SHA 必须从 CI 产物核对。

公开发布、参赛者本人解释验收、报名、入群及官方审核是独立状态。说明与清单见 project-brief.md / human-acceptance.md。自动检查不能代填人工签字或官方回执。
