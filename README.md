# MoonTxnWitness v0.0.1

MoonTxnWitness 是一个离线的事务历史检查器。它用 **MoonBit** 分析多键读写记录，找出阻止串行执行的依赖环，解释环上的每条边，并导出可以单独复核的证据。

首版已提供 MoonBit 库、Node.js 命令行、JavaScript 接口、7 个示例和真实 SQLite 日志采集示例。所有分析在本地完成，无需联网或数据库账号。

English: An offline MoonBit checker for versioned point-read/write transaction histories, with shortest dependency-cycle witnesses and certificate verification.

## 先运行一次

运行包需要 **Node.js 20 或更新版本**；本次实测为 Node.js 24.13.0。解压 portable ZIP 后，在解压目录运行：

```powershell
node dist/moontxnwitness.mjs --version
node dist/moontxnwitness.mjs check examples/write-skew.json
node dist/moontxnwitness.mjs check examples/consistent.json
```

第一条输出 `0.0.1`。第二条演示合成的写偏斜异常，返回退出码 **1**，给出 `T1 → T2 → T1` 的两条 RW 依赖。第三条返回退出码 **0**，给出可行的串行执行顺序。Windows 也可以双击 `run-demo.cmd` 查看异常示例。

异常示例退出码 1 是预期结果。输入不足时返回 3；输入、文件操作或证据无效时返回 2。

## 导出并复核证据

以下命令在当前目录创建新文件；已有文件不会被覆盖。

```powershell
node dist/moontxnwitness.mjs check examples/write-skew.json --format markdown --output report.md --witness witness.json
node dist/moontxnwitness.mjs verify examples/write-skew.json witness.json
node dist/moontxnwitness.mjs check examples/write-skew.json --format dot --output graph.dot
```

支持 `text`、`json`、`markdown`、`dot` 四种报告格式，默认 `text`。JSON 报告保留全部已构建依赖、发现和操作下标；`--witness` 导出精简的环证据。`verify` 也接受完整 JSON 报告。DOT 可交给 Graphviz 渲染，工具本身不依赖 Graphviz。

验证器检查输入约束、每条边的来源、事务路径和环是否闭合。它重新推导依赖，**不重新寻找环**。证据不包含数字签名或历史文件哈希；验证通过表示该证据能由当前提供的历史推出，不表示日志真实、最短性已复核或原始日志身份已认证。直接读写异常没有环证据，仍可在报告的 `findings` 中查看。

## 首版支持什么

- 单个事务中的多键点读写，唯一版本标记和明确提交结果。
- `serializable`：寻找满足读取观察及提供的同键版本顺序的串行执行。
- `strict-serializable`：再加入同一观察时钟下明确先完成、后开始的事务顺序。
- WR、WW、RW、RT 依赖，已构建图中事务数量最少的有向环。
- 读取回滚数据、外部中间写入、自己的未来写入、未读到自己的最新写入、无自身写入时重复读取不同版本等异常。
- 对缺少写入顺序、写入来源、提交结果或时间信息的情况，明确返回无法判定。

**每次写入必须有同键唯一的版本标记。** 例如即使两次写入的业务值都是 `100`，也要记录不同的版本 `x:T1:1`、`x:T2:1`。不能仅凭相同业务值认定读到了某次写入。

首版采用显式版本寄存器模型，尚不支持范围查询、谓词冲突、append/list 模型、SQL 自动采集、Jepsen 日志直接导入或完整的隔离级别分类。它检查提供的历史，不据此认证整个数据库。

## 输入示例

```json
{
  "schemaVersion": 1,
  "model": "serializable",
  "initial": {"x": "x0", "y": "y0"},
  "transactions": [
    {
      "id": "T1", "status": "committed",
      "ops": [
        {"type": "read", "key": "x", "version": "x0"},
        {"type": "write", "key": "y", "version": "y1"}
      ]
    },
    {
      "id": "T2", "status": "committed",
      "ops": [
        {"type": "read", "key": "y", "version": "y0"},
        {"type": "write", "key": "x", "version": "x1"}
      ]
    }
  ]
}
```

读初始版本 `x0` 要求 T1 在写 `x1` 的 T2 之前；读初始版本 `y0` 要求 T2 在写 `y1` 的 T1 之前，两者形成矛盾。

每个键必须声明 `initial`。`status` 必填，可为 `committed`、`aborted`、`unknown`。同一键有多个已提交事务的最终写入时，需要提供该键的 `versionOrders`，如 `{"x":["x0","x1","x2"]}`。顺序必须来自可信的采集证据；工具不会把数组位置、版本名字或提交时间当作写入顺序。

完整约定见 [输入格式](docs/input-format.md) 和 [JSON Schema](docs/history.schema.json)。

## 看懂结果

| 状态 | 退出码 | 含义 |
| --- | --- | --- |
| `consistent` | 0 | 在当前模型和提供的约束内存在可行串行顺序，且没有缺失信息 |
| `violation` | 1 | 已有确定读写异常或依赖环证据 |
| `invalid` | 2 | 输入格式或约束不合法 |
| `inconclusive` | 3 | 信息不足或分析预算不足，不能作出完整判断 |

`violation` 可以同时包含缺失信息，此时 `complete` 为 `false`；已确定的异常仍有效。`complete` 仅表示没有检测到的输入错误、信息缺失或预算截断，不是对采集完整性或数据真实性的外部保证。

## 接入自己的程序

JavaScript 接口只需要运行包中的文件：

```javascript
import { analyze, verify, version } from './dist/sdk.mjs';
const report = analyze(historyObject); // 也可传原始 JSON 字符串
console.log(version(), report.status, report.serialOrder);
if (report.witness) console.log(verify(historyObject, report));
```

MoonBit 库接口包括 `parse_history`、`analyze`、`report_json`、`history_json`、`render_report` 和 `verify_cycle`。源码暂使用 `local/moontxnwitness` 名称；该名称是本地占位，尚未发布到 Mooncakes。接口类型见 `src/pkg.generated.mbti`。

## 真实 SQLite 基线

需要 Python 3，使用标准库 `sqlite3`，无需安装依赖：

```powershell
python examples/capture_sqlite.py sqlite-history.json
node dist/moontxnwitness.mjs check sqlite-history.json --format json
```

采集器实际执行 3 个顺序事务，读版本来自真实 `SELECT`，写版本在真实提交后加入版本顺序。该基线应符合严格可串行化模型。异常示例均为合成日志；此基线不声称复现了 SQLite 并发漏洞。

## 从源码构建和验证

需安装 MoonBit、Node.js 和 Python。验证所用 MoonBit 编译器为 `v0.10.14+7d59c7ec9`；Moon 工具为 `0.1.20260920`。设置好 `MOON_HOME` 或 `moon` 的运行路径后：

```powershell
node scripts/build.mjs
npm test
npm run package
```

无需 `npm install`，没有外部 npm 或 Mooncakes 依赖。核心推导、环搜索、证据复核和报告生成使用 MoonBit；Node.js 负责本地文件和命令行，Python 负责测试基线与 ZIP 打包。开发细节见 [开发与复现](docs/development.md)。

本次验证记录在 [verification/summary.json](verification/summary.json)、[独立穷举检查](verification/oracle.json) 和 [命令行检查](verification/cli.json)。独立检查枚举 6,192 份完整的小型历史，另检查固定种子生成的 1,000 份多操作历史；通过枚举整个事务的串行执行来核对读写结果，不复用生产分析器的依赖规则。

资源上限：512 个事务、10,000 个操作、50,000 条依赖；历史文件最多 2 MiB UTF-8，核心解析最多 1,048,576 个 UTF-16 单元，JSON 嵌套最多 64 层。依赖预算截断不能返回 `consistent`。这些是首版边界，尚无大型生产负载保证。

## 许可证与比赛状态

项目采用 [Apache-2.0](LICENSE)。理论参考和依赖说明见 [THIRD_PARTY.md](THIRD_PARTY.md)。本项目通过 AI 辅助开发，并以可运行源码和独立测试提供验证证据。

v0.0.1 是本地首版交付，包含源码包和运行包。尚未公开发布、提交比赛、获得组织方接受或获奖。技术实现以真实完成的能力为准，不能保证一等奖。
