# 构建、测试与交付

## 环境与命令

本轮实测：Windows、Moon 0.1.20260920 (914d7da)、moonc v0.10.14+7d59c7ec9、Node 24.13.0、Python 3.12.5 / SQLite 3.45.3。MoonBit 仍在发展，建议使用同一工具链复现；其他版本需要实际验证。

从源码 ZIP 解压后，安装 MoonBit，确保 moon 可运行，或设置 MOON_HOME 指向安装目录。包装脚本只设置当前子进程环境。本机 .local-toolchain.json 不进入交付包。

```powershell
node scripts/moon.mjs check --target all --deny-warn
node scripts/moon.mjs info --target js
node scripts/build.mjs
npm test
npm run demo
npm run package
```

build 输出 dist/core.mjs、CLI、SDK、证据传输模块、演示及运行时许可证。无需 npm install，不依赖外部 npm/Mooncakes 包。npm test 检查格式与四目标类型，在 JS / Wasm GC / Wasm 运行核心测试，再执行独立 oracle、CLI 和真实 SQLite 采集。

`node scripts/test.mjs --all` 额外运行 native 测试，需要系统 C 编译器。当前 native 类型检查通过，执行仍因未找到 cc/gcc/clang 未完成。运行包不包含原生可执行文件。

## 当前验证覆盖

| 验证 | 已通过 |
| --- | --- |
| 核心 | 71 测试 × JS / Wasm GC / Wasm |
| 独立串行重放 | 10,320 历史，两种模型 |
| 环证据及独立 DFS 最短性 | 6,373 份 |
| 独立缩减检查 | 33 份反例，47 次剩余事务单删核对 |
| CLI / SDK / 导出 / 回放 | 69 项，包括真实 SQLite 与一键演示 |
| 真实并发采集 | 3 次独立执行，每次 2 轮：4 提交、2 回滚 |
| Native | 仅类型检查；未执行 |

oracle 包含 6,192 份完整小历史、1,000 份固定种子多操作历史、3,128 份缺少/部分版本顺序的历史。它枚举整个事务的串行排列，实际重放读写及输入顺序约束，不复用生产依赖推导。正常报告的串行顺序也被重放。

这是有限可复现的证据，不能代替所有日志上的形式化证明。实际 SQLite 执行只证明这几份日志通过检查。

`npm run benchmark` 输出本机端到端分析时间及 SCC 统计。可用 `node scripts/benchmark.mjs --baseline PATH_TO_OLD_CORE.mjs` 与旧版对比。当前保存记录显示两事务环案例没有端到端加速，严格无环案例时间接近；SCC 缩小搜索范围并不等于整个程序总耗时一定下降。

## 交付包和干净目录检查

npm run package 生成：

- artifacts/MoonTxnWitness-v0.0.6-source.zip：源码、测试、文档、示例、验证记录；不含构建目录或本机配置。
- artifacts/MoonTxnWitness-v0.0.6-portable.zip：编译核心、CLI/SDK/演示、文档、示例、记录及许可证；运行需 Node.js ≥20。
- artifacts/SHA256SUMS 及版本专属校验文件：ZIP 摘要。
- verification/package.json 与 artifacts/release-index.json：打包及干净目录验收结果。

打包脚本在 artifacts/consumer-work 下创建新目录解压两种 ZIP。运行包直接执行；源码包不用私有配置，借助当前外部 MoonBit 工具链重建并运行 71 个 JS 核心测试。两者都检查全部主示例、证据导出/复核、缩减后重查、自包含回放、模型对比、SDK 和演示。临时目录不进入 ZIP，不重置或删除既有目录。

打包的验证记录不包含用户账号或本机绝对路径。verification/package.json 不进入 ZIP，避免包记录自己的哈希造成循环。SHA-256 用于完整性核对，不是签名或真实性认证。

## 迭代与外部状态

Git 保存 v0.0.1–v0.0.6 的开发历史；五轮改进及通过的检查见 verification/iterations.json。初版 ZIP 保留。公开仓库为 https://github.com/HhWw96/moontxnwitness，安装模块为 HhWw96/moontxnwitness@0.0.6。发布及公开下载核验结果见 verification/publication.json。

公开 CI 在 Windows 2022 / Ubuntu 24.04 检查核心、oracle、CLI、真实 SQLite 和干净目录交付流程，Linux 另运行 Native 核心。工作流固定官方工具与组件版本；实际结果以 Actions 页面和发布记录为准，不把已配置工作流当作执行通过。比赛提交与组织方接受仍是单独步骤。
