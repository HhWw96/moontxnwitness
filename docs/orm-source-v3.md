# ORM 原始来源诊断

`inspectOrmSourceV3` 与 `inspect-orm-source-v3` 核验固定 FastAPI Users
SQLAlchemy v7.0.0 / PostgreSQL 18 来源记录。它们展示原始控制查询、同语句
读写来源、保存点撤销与最终效果账本之间的对应关系。

v0.1.3 将此显式入口作为稳定的**局部诊断接口**交付；本版尚在开发，
发布与验证状态见[开发记录](development-status.md)。固定 SQL 编译与有界缓存
另见[Python 模板入口](orm-plans.md)。

该入口只证明受支持来源片段的一致性。报告始终保留
`analysisCoverageAccepted:false`、`history:null` 和空的完整覆盖集合；默认
`normalizeCaptureV3` / `analyzeV3` 不自动采用这些局部事实。
`ProvenanceObserver`、来源安装/迁移和完整 ORM 自动采集仍为实验功能。
诊断入口不代表整个认证系统、任意 SQL 或完整 ORM 历史已覆盖。

## 运行已有原始案例

使用包含此入口的 portable 包，或从当前源码构建后：

```text
node dist/moontxnwitness.mjs inspect-orm-source-v3 verification/experimental-candidates/orm-source2-r3-2026-10-21/fixtures/diagnostic-trace.json verification/experimental-candidates/orm-source2-r3-2026-10-21/fixtures/source-observations.jsonl --output orm-sources.json
```

输出路径必须尚不存在。两份输入最多一份使用 `-` 从标准输入读取。
退出码 **0** 表示局部来源证明成功，完整事务历史仍然无法判定；**2** 表示
输入、执行或局部来源证明失败。此命令不连接数据库，也不重新运行原业务。

```javascript
import {readFileSync} from 'node:fs';
import {inspectOrmSourceV3} from './dist/sdk.mjs';

const result = inspectOrmSourceV3({
  schema: 2,
  profile: 'fastapi-users-sqlalchemy-7.0.0-pg18/1',
  traceText: readFileSync('trace.json', 'utf8'),
  sourceJournalText: readFileSync('source.jsonl', 'utf8'),
});
console.log(result.provenFacts, result.gaps);
```

SDK 保留调用者的 schema/profile，不自动补充 scope、提交确认或来源。
限制按实际 UTF-8 字节计算：外层信封64 MiB、原始 trace 8 MiB、原始 JSONL
16 MiB、单来源记录128 KiB；最多16,384条来源记录。核心还检查原生结果的
字段类型、格式、SQL/参数、来源摘要、初末目录与版本链。超过额度不产生
完整结论。

## 支持边界与证据

仅接受固定业务、固定适配器、受控写者及明确初始键域。没有观察到的
DDL/元数据变更、数据库认证、任意函数、JOIN 与完整 SQL 插桩均未证明。
条件事实不伪装成 SELECT 读取；COMMIT 请求不代替成功应答；回滚写不进入
最终已提交账本。读取结果必须来自实际交付给业务的原始记录。

集成前的独立组件验收包括四目标各616项核心检查、74项作者原始/篡改检查，
以及[实际公开下载后24项独立检查](https://github.com/HhWw96/moontxnwitness/actions/runs/39595025070)。
首次独立参考程序的参数选择错误及修正前后收据原样保留。
这些旧组件结果不外推到新的 SDK/CLI 构建；集成版须以新的测试摘要、
运行文件和独立重放结果为准，见[开发状态](development-status.md)。

本轮模板/缓存的 21 项主线离线检查及 32 项独立候选检查已通过，
其中独立检查包含 21 项复验；这些结果不计作当前包的真实数据库执行。
原始 SQLAlchemy 异步驱动、安装迁移及完整来源覆盖按各自实际验证范围记录。
