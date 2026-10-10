# 构建、测试与交付

## 前提

验证工具链：Moon `0.1.20260920 (914d7da)`，moonc `v0.10.14+7d59c7ec9`，Node.js `v24.13.0`，Windows。建议使用同一版本的 MoonBit 工具链；其他版本可能存在语言/API 变动。Python 使用标准库即可。

从源码 ZIP 解压后，安装 MoonBit 并确保 `moon` 可运行；也可设置 `MOON_HOME` 指向安装目录。包装脚本只修改当前子进程环境，不改全局安装。开发机器的 `.local-toolchain.json` 是忽略文件，不在交付包内。

```powershell
node scripts/moon.mjs check --target all --deny-warn
node scripts/build.mjs
npm test
npm run package
```

`build` 输出 `dist/core.mjs`、`dist/moontxnwitness.mjs`、`dist/sdk.mjs` 和运行时许可证。`npm test` 检查格式、四目标类型检查，执行 JS / Wasm GC / Wasm 核心测试、独立 oracle、命令行测试和实际 SQLite 采集。

`node scripts/test.mjs --all` 还尝试执行 native 测试，需要系统 C 编译器。当前机器 native 执行因缺少 `cc`、`gcc`、`clang` 未完成，不计为测试通过。运行包只交付 JavaScript 核心，不包含原生可执行文件。

## 验证覆盖

- MoonBit 核心：41 个测试，在 JS、Wasm GC、Wasm 分别运行。
- 独立 oracle：2/3 个事务、两个键、每事务一读一写，穷举写键、读键和来源、版本顺序，检查两种模型，共 6,192 份历史。
- 固定种子扩展：1,000 份 2–4 事务、三键、多次写入和重复读取的历史。
- oracle 对整个事务作全排列重放，核对读取版本和每键最终写入顺序；正常报告的串行顺序也实际重放。
- 环证据经复核器检查，最短性经测试内的独立 DFS 检查。
- 命令行：输出格式、退出码、UTF-8、大小限制、篡改证据、文件保护、导出回滚、真实 SQLite 等。

这些是可复现的有限测试，不能代替所有日志上的形式化证明或生产稳定性验证。

## 包和干净目录检查

`npm run package` 先构建运行文件，再生成：

- `artifacts/MoonTxnWitness-v0.0.1-source.zip`：源码、测试、文档、示例；不包含本机工具链路径或构建目录。
- `artifacts/MoonTxnWitness-v0.0.1-portable.zip`：已编译核心、CLI/SDK、文档、示例和许可证；无需 MoonBit 编译器，需 Node.js。
- `artifacts/SHA256SUMS`：两个 ZIP 的 SHA-256。

打包脚本把两个包解压到新的测试目录：运行包直接执行 CLI、导出并复核证据；源码包通过当前可用 MoonBit 工具链重新构建并运行示例。验证结果写入 `verification/package.json`。临时目录在 `artifacts/consumer-work/`，不会进入两个 ZIP。

验证记录没有用户账号信息或本机绝对路径。Git 为本地版本管理，不配置远端；公开发布、远端 CI、Mooncakes 和比赛提交属于后续工作。
