# 重放 v0.2.4 的 ORM 证据

当前 SDK 支持直接验证和重放实际公开 v0.2.4 生成的 ORM 报告与复现包。普通分析和新证据使用当前版本；只有明确属于 v0.2.4 的旧 ORM 证据才加载固定的旧运行时。同步 API 保持，支持 Node.js 20 及以上。

```javascript
import {readFileSync} from 'node:fs';
import {replayOrmProfileCapsuleV3} from './dist/sdk.mjs';
const result = replayOrmProfileCapsuleV3(readFileSync('old-orm.capsule.json', 'utf8'));
console.log(result);
```

未知引擎、被修改的来源、结论或预算仍会被拒绝。验证成功表示原证据可按其原规则重算，不改变未知提交、覆盖缺口或原有异常结果。

## 固定依赖与按需加载

`cmd/legacy/v024` 保存原公开的 `core.mjs`、`orm-profile.mjs`、许可及来源摘要。构建只将这两个固定文件已知的导入/导出语法转换成同步加载包装；原文件和派生文件分别记录 SHA-256。构建、打包和首次加载都会核验绑定，复现包不能提供或选择可执行文件路径。

在实际 Node 20.20.2 和 Node 24.13.0 上，15 类原始公开证据各通过 107 项检查。普通 SDK 导入、新分析和新报告验证加载的旧模块数为 0；首次旧 ORM 重放后仅加载所需的 2 个模块。完整版本回归、全新安装及公开下载结果分别保存在当前版本的发布收据中。

## 自行检查兼容性

源码包与便携包均包含固定输入及验证程序。选择一个尚不存在的输出目录运行：

```text
node scripts/compat-v024-test.mjs dist fixtures/compat-v024 NEW_OUTPUT
```

检查保留原报告、原复现包和业务字段的全部字节。v1/v2 验证回执中的顶层 `currentEngine` 会反映当前版本；`recordedEngine` 及其他结果必须与原版一致。旧期望结果不会重新生成。原始下载、首次失败和兼容检查记录见 `verification/compatibility/`。
