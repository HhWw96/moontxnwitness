# relation-set-v1 有界关系模型契约

状态：本文件描述 v0.1.5 起明确提供的有界 `relation-set-v1` 事实模型，归一化算法为 `v3-relation-lifecycle-1`、分析为 `v3-relation-1`；路径保留 draft 名称以兼容旧链接。当前支持与入口见[关系模型](relation-v3.md)、[SDK](relation-sdk.md)及[稳定矩阵](stable-scope.md)。以下语义与额度继续适用；独立解释器预期必须先冻结，不能根据生产结果生成。

## 输入及类型

沿用 v3 原始观察、可撤销效果与执行信息分离。根对象增加 `dataModel:"relation-set-v1"`、`relationSchema`。不支持同一轨迹混合寄存器、列表或关系模型。通用 statement/rows 仍可保留原始观察并产生未证明 SQL 缺口，不自动转换语义事实；寄存器 read/write 或列表 append/list_read 出现于此入口时为混合模型 invalid。

```json
{
  "relationSchema": {
    "accounts": {
      "primaryKey": "id",
      "columns": {"id":"int64","balance":"int64","active":"bool","region":"text"}
    }
  },
  "scope": {"exclusiveWriters":true,"completeSnapshotTables":["accounts"]}
}
```

首版允许 1–8 个关系，每关系 1–16 列。关系与列标识符遵循 `[A-Za-z_][A-Za-z0-9_]{0,62}`，大小写敏感；版本身份为非空有效 Unicode 标量字符串，最多 256 个 UTF-16 单位。主键为 int64 或 text；普通列为 int64、bool、text。int64 以规范十进制 JSON 字符串传输，完整支持有符号 64 位范围，禁止加号、前导零、`-0` 和浮点替代。布尔值使用 JSON boolean。文本为有效 Unicode 标量序列，允许空串和 U+0000，不做大小写折叠或规范化，按 Unicode 码点字典序比较；不能直接使用 UTF-16 code unit 排序。采集 SQL 必须另行证明其比较规则与此一致；PostgreSQL text 无法表示 U+0000，其适配器须明确拒绝或保留缺口，不能混淆模型和数据库值域。

行格式：`{key,version,values}`。key 按主键类型编码；values 含全部非主键列且不重复存主键。version 为跨关系全局唯一的不透明版本身份，不表示提交顺序。内部键须结构化编码 `(关系,主键类型,主键值)`，不能用分隔符拼接。

`snapshot.initial` 为关系名到行数组的映射，数组顺序无语义；每个声明关系都必须显式有数组，缺少关系为 invalid，空数组是合法空集合。快照必须一致，并在 completeSnapshotTables 中明确声明关系的初始完整集合，才能把未列出的主键视为初始不存在。任何声明关系未列入 completeSnapshotTables 都产生覆盖缺口，首版不给完整结论。该声明是语义输入前提，不认证采集器真实性；原始 SQL 路径必须另有覆盖证明。重复初始主键或重复生产版本属于格式无效。NULL、自定义函数、JOIN、聚合、子查询或未支持的排序规则由采集层保留原观察并产生缺口，不生成伪造的受支持事实。

## 原子关系操作

| kind | 字段 | 含义 |
| --- | --- | --- |
| row_read | tx、relation、predicate、rows、complete | 完整谓词查询的实际交付集合，顺序无语义 |
| row_write | tx、relation、key、action、version、predecessor、values | 实际单行 insert/update/delete 效果，不能当作完整谓词查询 |

predicate 是最多 8 项的 AND 数组，项为 `{column,op,value}`。op 支持 eq/lt/le/gt/ge；bool 仅支持 eq；主键也可作比较列。空 AND 表示全关系。矛盾条件是合法的空集合查询。首版没有 OR、NOT、LIKE、隐式类型转换或任意表达式。

row_read.rows 使用行格式，complete=false 或关系快照覆盖不足均阻止完整结论。完整查询结果与匹配的全部当前存活行比较；不能把 UPDATE RETURNING、受影响行集合、LIMIT 或提前停止的游标结果标为完整查询。重复返回主键、已知版本的错误行内容、错误关系或不满足谓词的返回行保留为观察，并在已提交事务及完整覆盖条件下产生模型反证。未知读取版本在该观察时永久记录来源缺口；后来的生产事件不能追认其当时已经被观察。

row_write.action 为 insert/update/delete。每次写都产生新版本，即使内容相同；delete 也生成独立墓碑版本。insert/update 的 values 为完整非主键行，delete 的 values 必须为 null。update/delete 的 predecessor 字段必须为非空版本身份，null 为 invalid；在串行重放时还必须是当前存活行的版本。insert 必须针对当前不存在的主键：从初始完整快照证明一直不存在时 predecessor 为 null；删除后重插则引用墓碑版本。写前驱在该事件时未知或只在未来出现，同样永久记录来源缺口；已提交效果引用已知错误关系/主键、中止或撤销来源时可给出描述性来源反证。首版初始快照不接受墓碑格式，引用窗口前删除 token 仍是来源缺口，不能用完整不存在声明将其改为 null。来源前驱是写效果事实，不是伪造的 SELECT。主键更新拆为有明确来源的 delete+insert，不支持静默改 key。

数据库 RC 多行写的重检、等待及目标搜索未获得完整证据时保持缺口；仅有实际写效果不能证明完整谓词读取。此模型入口先接受明确语义事实；任意原始 SQL 不会自动转成上述操作。

## 生命周期及解释器

使用现有 v3 begin/savepoint/rollback_to/release/commit_request/commit_ok/rollback_ok/disconnect。保存点恢复行状态和墓碑，但保留已交付读取。重复名称仍按独立实例和最新同名作用域规则处理。RELEASE 不是提交；未知 COMMIT 保持 unknown。

精确解释器只串行重放已提交事务的完整操作日志，包括其后来撤销的保存点内读取；已中止事务读取不附加 opacity 约束。未知来源仍阻止完整结论。已提交读取来源于已知中止/撤销或墓碑版本可给出描述性来源反证，但不得直接改名为 G2 或隔离级别分类。

同事务先前合法的中间写不能因最终被覆盖而倒推无效；外事务读取已提交事务中间版本通过完整重放判断，不自动添加中间版本异常分类。归一化 effects 保留所有写入效果及保存点撤销状态；同一主键的中间写被后续写覆盖不等于 reverted。transactions.finalWrites 只列每个 `(关系,主键)` 最后一个未撤销写的事件序号，包含删除墓碑，不能将全部效果都放入该字段。状态以主键映射保存存活行或墓碑。每个候选事务依序执行操作与保存点：完整查询必须逐项符合谓词、版本和全部列；实际写必须满足存在性与前驱。独立解释器使用不同实现方式，不调用生产模型/依赖图函数。模型结论为 consistent/violation/inconclusive/invalid；串行搜索无解只证明所定义的串行关系模型无解。

首版精确额度：6 个提交事务、全轨迹 128 个 row_read/row_write 语义操作（包含中止和撤销操作）、100,000 候选状态、1,000,000 次语义检查。原始结构额度另设：最多 512 事务、65,536 事件、10,000 操作、1,024 个不同关系主键、100,000 个返回行引用。超出结构约定为 invalid，超出精确容量或计算预算为 inconclusive，不能返回无解。先检查容量与覆盖缺口，再处理直接来源反证和搜索；不能通过直接反证绕过容量。已知直接来源反证不消耗搜索预算，因此 maxStates/maxOperationChecks 均为 0 时仍可给出反证；该预算的 scope 必须明确为搜索。

预算在搜索开始前记录：每次候选事务尝试计一个状态；read/write/savepoint/rollback_to/release 每个动作计一次检查。查询按规范主键顺序扫描存活行，按谓词原输入顺序逐项比较、失败短路，每项比较计一次。结果集合先比较长度计一次，再按规范主键排序，每行的 key、version 及每个非主键字段按声明 schema 顺序逐项比较计一次，首差异短路。主键排序本身不计语义检查，int64 按数值、text 按码点字典序。最后一个允许的检查恰好完成时可得结论；下一项工作所需预算不足时必须返回无法判定。初版不使用失败状态缓存；后续若加入，键必须包括墓碑、完整行版本及全部有关约束。

## 缩减与验收

删除整笔事务后重新验证所有来源、初始事实、谓词覆盖和模型。仅裁剪原输入事实，不把搜索结果写成采集事实。oneMinimal 表示当前异常规则下完成剩余事务全部单删检查；缺失来源的候选不能被当作保留异常。

原预登记覆盖目标及逐版实际解释器、边界、数据库结果保留在[开发历史](development-status.md)与 `verification/releases/`；不能把计划数量当作当版实际成绩。后续修改仍核对文本码点、int64 边界、空结果、矛盾 AND、插入/删除/重插、跨谓词更新、同值不同版本、多次写、保存点、未知提交、来源缺失、预算和缩减。受控 PostgreSQL fixture 与旧记录重放分开，不代表任意 SQL 或完整 ORM 接入。
