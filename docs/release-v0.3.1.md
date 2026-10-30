# v0.3.1：工具链升级与源码树整理

本版将当前源码迁移到 MoonBit `0.10.16+b1a0e846e`，构建前要求 moonc 不低于 `0.10.16`。公开 SDK、CLI 与现有分析预算保持兼容。

## 运行核心库示例

```sh
git -c core.longpaths=true clone --depth 1 https://github.com/HhWw96/moontxnwitness.git
cd moontxnwitness
moon run --target wasm-gc src/demo
```

示例直接调用 MoonBit 库，分析两事务写偏斜、核验环证据并验证缩减后的反例，不需要 Node.js、Python 或数据库。

从 Mooncakes 使用核心库：

```sh
moon add HhWw96/moontxnwitness@0.3.1
```

接口示例见 [`src/demo/main.mbt`](../src/demo/main.mbt)。

## 源码与兼容组件

历史实验输出和完整源码副本移出当前文件树，原材料仍可从旧 Git 提交和发布标签恢复。新生成的构建与实验输出默认忽略；CI 检查暂存区总量、新大文件及重复 MoonBit 源码。当前树和完整 Git 历史的大小分别记录，详见[仓库布局](repository-layout.md)。

公开 v0.3.0 兼容运行时按固定下载摘要准备到忽略的本地缓存，源码树不再为本次版本增加一套旧运行时。便携包携带相应组件；首次源码构建需要联网下载，之后可以复用已校验缓存。

旧 v3 报告中包含的诊断位置、预算和观察内容保持原样，通过固定原运行时核验。已发布引擎采用明确白名单；未知版本、内外引擎不一致或组件损坏均不能通过复核。

## 验证入口

```sh
npm test
node scripts/performance-evidence-test.mjs
python -B -m unittest discover -s scripts -p test_repository_hygiene.py -v
npm run package
```

`npm test` 需要[固定 Python 测试依赖](../examples/orm-requirements.txt)。数据库检查使用独立受控 PostgreSQL 18，相关原始 SQL、实际结果、胶囊与收据保存在 `verification/releases/0.3.1/`。完整回归、独立复核、安装测试和公开下载验证分别记录；本版不增加未测量的性能提升声明。
