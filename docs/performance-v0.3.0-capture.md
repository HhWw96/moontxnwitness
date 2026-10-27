# v0.3.0 来源日志缓冲与采集成本

配置化来源入口接受 `source_write_buffer_bytes`：默认 0 保留已有来源同步行为；非零需为 128–262144 的整数。缓冲属于有界来源写入的一部分，不能替代封存、尾部同步或完整来源验证。队列背压、写入/同步失败及不完整索引仍然可见；封存必须等所有尾部记录同步并校验完成。

```python
profile = install_model_profile(..., source_write_buffer_bytes=65536)
# install_user_profile() 使用相同的显式选项。
```

## 正式 A/B/C 结果

固定源提交 `329df5cf1a2c58f03dd9e913e0621a822c6411ef`，两个独立 Linux 工作流各执行 36 单元。A 为原业务，B 仅来源，C 完整来源、诊断采集与持久化；只有 C 启用 65536 来源缓冲。四负载、15 秒预热、60 秒发起、30 秒排空与三批 ABC/BCA/CAB 不变，吞吐分母含持久化尾部。

以下为三批配对几何比，目标保持 C/A 吞吐 ≥0.90、P95 ≤1.15。**所有负载均未达到性能目标。**

| 来源 | 负载 | C/A 吞吐 | C/A P95 | 资格 |
| --- | --- | ---: | ---: | --- |
| column | serial | 0.2318 | 3.5541 | 合格，目标未达 |
| column | parallel | 0.1397 | 6.7869 | 合格，目标未达 |
| column | hot | 0.1721 | 4.3035 | 合格，目标未达 |
| column | crud | 0.1268 | 6.1506 | 不合格 |
| sidecar | serial | 0.2520 | 3.7766 | 合格，目标未达 |
| sidecar | parallel | 0.1433 | 6.8677 | 合格，目标未达 |
| sidecar | hot | 0.1899 | 5.1716 | 合格，目标未达 |
| sidecar | crud | 0.1446 | 5.6379 | 不合格 |

全部 72 单元执行完成，预算耗尽为 0、attempt 日志缺失为 0。两组 CRUD 均遇到原始 `23505` 重复插入失败，分别有 135075／70286 次测量失败和 43234／24221 次预热失败；各 9 个 CRUD 单元不具资格。其余三类负载 SQL 失败为 0，但采集成本仍明显超出目标。C 的持久化尾为 7.20–9.53 秒，事务内 P95 也明显偏高；不能只用结束 flush 解释差距。

完整原件见 [column 工作流](https://github.com/HhWw96/moontxnwitness/actions/runs/40383472300)和 [sidecar 工作流](https://github.com/HhWw96/moontxnwitness/actions/runs/40383476670)。[汇总与原件 SHA](../verification/releases/0.3.0/development/capture-cost-buffer-summary.json)保留实际源提交、artifact 身份、资格和失败计数。独立 AI 技术审查逐条重算原 attempt、P50/P95、吞吐分母及三批几何比，校验 72 个内层 ZIP、685 个原始文件和全部 C 单元的持久水位与封存；不等同于真人、生产或赛事审核。

该实验只测上述来源缓冲候选，不把旧机器的数据换算为本次提速，不代表完整 v0.3.0 的正式性能数字。关系缩减的 1.124× 仍仅属于[既有固定负载](performance-v0.2.8-relation.md)。后续 CPU 热点优化与此处原件分别记录，不能改写本轮失败结果。
