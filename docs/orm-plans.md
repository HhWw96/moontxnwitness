# ORM 固定 SQL 模板与缓存

Python 包提供独立的 `moontxnwitness_capture.orm` 入口。复制
`integrations/python/moontxnwitness_capture` 整个目录，加入 Python 模块搜索路径即可。
普通导入不要求数据库驱动或 SQLAlchemy；编译模板时需要可选的
SQLAlchemy 2.0.55，测试依赖见 `examples/orm-requirements.txt`。

```python
from moontxnwitness_capture.orm import UserScope, SQLContext, StructuredSQLCache

scope = UserScope('mtw_orm_v3_example', 'observed_user', (
    '00000000-0000-4000-8000-000000000001',
))
cache = StructuredSQLCache(context=SQLContext(registry_epoch=1))
plan = cache.prepare(scope, 'get')
assert cache.match(scope, plan.original_sql, 'get') is plan
print(plan.original_sql)
```

支持固定 FastAPI Users SQLAlchemy v7.0.0 的 base-user 按 ID 查询、创建、
修改及删除 SQL 形状，采用 PostgreSQL 18 / psycopg 3.3.6 约定。模板匹配要求
原始 SQL 完全一致；不自动识别任意 ORM、JOIN、函数、动态主键域或认证流程。
本入口本身不执行 SQL，也不读取业务结果。

缓存只保存不可变 SQL 计划，键包含 schema、表、完整已声明 UUID 域、操作、
修改字段、参数绑定布局和编译上下文。参数值、查询结果、连接及事务状态不进入缓存。
数据库安装、元数据假设或连接配置发生变化时，调用方必须更换 `registry_epoch`
或创建新的观察器；缓存不会自动监测数据库目录。

默认最多保留 128 项、1 MiB 计费条目字节。可配置范围为 1–256 项、
4 KiB–2 MiB；超大计划正常返回但不保留，关闭缓存同样保留模板校验。
字节预算包含条目对象图及每项 512 字节的容器开销额度，不表示整个进程的 RSS
上限，也不包括观察器单独持有的固定模板映射。

已有观察器在构造阶段编译 35 个模板，再在首次执行时重复编译。
新实现复用构造阶段的同一缓存：固定 35 形状、每形状调用三次的对照中，
实际编译次数从 70 降为 35。这个结果仅说明消除了重复编译；未将其换算为
业务吞吐、耗时或内存的提升比例。

局部来源记录的 MoonBit 核验见 [ORM 来源诊断](orm-source-v3.md)。
`ProvenanceObserver`、`SourceSink`、来源安装及完整自动采集仍是显式实验入口。
局部证明不会授予完整事务历史覆盖，未知提交及缺失来源仍保留为无法判定。

开发验证：安装上述测试依赖后，执行 `python -B scripts/orm-unit-test.py`。
它验证实际编译器、旧实现对照、缓存隔离、逐次参数检查及结果/异常身份，
并禁止测试访问数据库。数据库验证和离线测试分别保存结果。
