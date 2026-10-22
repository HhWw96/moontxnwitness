# perf-v3 最终静态封存入口

使用 `run-protocol-v3-final.py`，授权中的preparationManifestSha256绑定 `preparation-manifest.v3-final.json`。其余参数和17/18绑定格式、固定7输入、协议和严格根引擎头原文本投影完全见README-v3。

原v2的22文件与初版v3的33文件全部原字节保留。最终仅把无外部依赖的core检测限制在真正import/export-from声明或动态import语法；JSON字符串字段 `"from"` 不是模块依赖，不能被误判。首版静态准备快照仍保留，没有执行过SDK或测量，没有改变任何输入/输出/预算/版本语义期待。

```text
python -B artifacts/v018-performance-preparation/run-protocol-v3-final.py --binding RUNTIME_SOURCE_BINDING.json --binding-sha256 ROOT_BINDING_SHA --authorization AUTH.json --authorization-sha256 ROOT_AUTH_SHA
```

缺少外给实际17/18源与core的SHA、正式构建/已发布17绑定、exclusive=true及所有其他agent已停止的授权时不能执行。当前只有静态准备，没有core import、计时、RSS/冷启动测量、编译、数据库、网络或提速结论。
