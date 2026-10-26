# Combined observation diagnosis

`diagnoseV3(rawTrace, {analysisOptions: {}, modelOptions: {}})` combines the unchanged serial analysis with explicit formal-model checks. `verifyDiagnosisV3(rawTrace, report, optionalOriginalOptions)` recomputes both reports and the entire aggregate. The SDK and `diagnose-v3` / `verify-diagnosis-v3` CLI accept only raw traceSchema 3 captures up to 8 MiB; source envelopes need their existing dedicated entry points.

The distinct format is `moontxnwitness-diagnosis-report/v1`, algorithm `diagnosis-host-1`. It retains complete child reports, original serialized options, exact source/core/host SHA256 identities, budgets, verification results and evidence-backed rule findings. It grants no new capture coverage or database-wide certification. The first release has no diagnostic capsule or source-preserving reducer.

INT can prove that a committed transaction did not read its current own write. It remains INT; PL3/strict applicability, graph anomalies, serial-analysis status and coverage gaps stay separate. Missing sources, unconfirmed outcomes, unsupported models and exhausted budgets remain visible. A finding does not complete the other checks.

CLI exit codes: 1 for a verified rule finding or serial violation; 0 for no findings after the requested checks complete; 3 for incomplete checks; 2 for invalid input/report. Verification exit 0 means exact reproduction, including incomplete results. Output files must be new and cannot overwrite inputs. New diagnostics do not revise prior comparison statistics.

## 统一观察诊断

新入口把原串行分析与显式模型检查并列输出，保留完整证据和缺口。自身写错读显示为 INT，不替换成 G2，也不把仍无法判定的 PL3 或严格串行模型改成反证。报告验证会重新执行两类检查；摘要或哈希相同不能代替验证。

A reliable refutation can coexist with incomplete required checks. Determinate model verdicts and completed checks are reported separately.
