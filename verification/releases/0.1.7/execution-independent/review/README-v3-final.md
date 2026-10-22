# 实际17 v3最终准备（仍未执行）

入口 `run-review-v3-final.py` 与清单 `preparation-manifest.v3-final.json`。原v2的32文件、初v3的39文件均逐字节保留；原11输入、完整诊断期待、两案MLflow事实与旧模型胶囊没有改变。

最终只将依赖扫描识别限制在真正行首import和export-from声明；JSON字段字符串 `"from"` 是数据，不是模块声明。仍然拒绝动态import、未知/多行未审查声明、不在冻结runtime清单中的依赖、外部或逃逸路径，所有source/runtime SHA守卫与语义检查保持。没有通过放松业务预期修正这种准备器假阳性，也未执行任何SDK来得到新期待。

```text
python -B artifacts/v017-actual-independent/run-review-v3-final.py --freeze ROOT_FREEZE.json --freeze-sha256 ROOT_SUPPLIED_SHA256
```

source.root='.'与runtime.root='dist'可从repo cwd使用。packages=[]仍明确留下package/download接受未完成；正式包消费者流程另验。私有原启动/预flight保留原件并记录SHA，公开闭包后续只选择相对路径可复制代码、运行文件、输入和收据，不复制整个私有目录或全源镜像。

仍等根实际17冻结与外给SHA；没有SDK/core import、构建、数据库、网络或性能测量。
