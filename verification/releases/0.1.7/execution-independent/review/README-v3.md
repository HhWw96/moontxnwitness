# 实际17独立审查 v3（仅准备，尚未执行）

原32文件v2及其准备清单完整保留，SHA仍为 `a464db0a028761408caa17c2b5af94bcda6c3447c858c0912be1b0910ca698e5`。v3只拆开阶段，避免“独立审查→acceptance→正式打包”依赖环；没有减少任何执行诊断语义断言、source fingerprint或runtime/import闭包守卫。

根外给实际17冻结信号、源码/runtime逐文件SHA和冻结JSON的SHA后，才启动：

```text
python -B artifacts/v017-actual-independent/run-review-v3.py --freeze ROOT_FREEZE.json --freeze-sha256 ROOT_SUPPLIED_SHA256
```

第一阶段可使用 `root-freeze-v3.template.json` 的 `packages:[]`。此时结果必须记录 `packagesExecuted:false`、`packageReviewPending:true`、`downloadAcceptance:false`、`formalPackageAcceptance:false`，只审查实际17源码/runtime语义，不把它当包或下载验收。

第二阶段由正式打包/消费者流程独立外给source与portable包SHA并完整核验。v3若提供两个包，仍要求各自SHA、CRC及全部绑定成员原字节；只有实际执行这些检查才记packagesExecuted。正式包可以包含第一阶段的最终acceptance，不再形成循环。

实际17尚未执行；没有导入SDK、构建、联网、数据库或测量。根的正式冻结信号仍是必要前提。完整诊断期待、旧模型胶囊兼容、业务版本字符串保留及旧MLflow边界见原README；v3没有改写原输入或预期，也没有覆盖任何旧失败。
