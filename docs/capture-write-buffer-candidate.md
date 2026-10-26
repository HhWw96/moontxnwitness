# Opt-in bounded source write buffering

`GroupedSourceSink(path, write_buffer_bytes=65536)` adds a bounded standard-library binary write buffer to coalesce small source-record writes. `write_buffer_bytes=0` is the default and preserves the existing unbuffered path. Nonzero buffers must be integers in 128..262144 bytes; booleans are rejected. This buffer is additional to the default 4 MiB queue and its bounded in-flight record reservation. It is declared separately as `writeBufferBytes` in the sealed index and verification result only when enabled. This bound is not a whole-process RSS claim.

## Explicit source-writer example

This executable example demonstrates storage of an example record only. It supplies no SQL/model coverage. Use a new path, stop source-producing workers before close, and retain the original files and guards if synchronization or close raises.

```python
from moontxnwitness_capture.source_sink import GroupedSourceSink, SourceSinkError

sources = GroupedSourceSink("new-sources.jsonl", write_buffer_bytes=64 * 1024)
try:
    admitted = sources.append({"kind": "source-batch", "example": True})
    if not admitted.accepted:
        raise SourceSinkError("Source record was not admitted: " + str(admitted.gap))
    durable_prefix = sources.flush()
    assert durable_prefix >= admitted.source_seq
finally:
    storage = sources.close()  # synchronization/close errors propagate
assert storage["storageSealed"]
assert storage["coreProofAccepted"] is False
```

An append result acknowledges queue admission. `source_seq` identifies that admitted record; `durable_seq` reports the previously synchronized prefix observed when append returns. `stats['bytesWritten']` counts bytes accepted by the file object, which can include bytes still in the optional Python buffer. `stats['durableRecords']` advances only after source data flush/fsync and index fsync/replacement/directory synchronization. Call `flush()` to wait for its accepted target prefix; call `close()` to append the seal, drain, synchronize and close before removing the writer guard. A write/sync/index/close error rejects the source seal and keeps failure/writer guards. A failed close can have a previously synchronized open index; that does not make the source sealed.

The default 256 KiB / 100 ms synchronization scheduling and explicit flush watermark protocol are unchanged. Timer scheduling is not a hard wall-clock persistence deadline under blocked storage. The additional buffer does not change source record JSONL bytes or delete source history.

## Entry-point boundary and error handling

`write_buffer_bytes` is a `GroupedSourceSink` constructor option. `Instrumentation`, `instrument_engine` and `instrument_psycopg` do not own a source sink and reject this keyword before creating diagnostic resources. `Instrumentation.psycopg_factory` configures a local connection wrapper, not source storage. Arguments passed later to its returned `connect` callable belong to the original driver. No buffer setting is injected into a driver connection or global driver.

`install_user_profile` and `install_model_profile` accept the keyword-only `source_write_buffer_bytes=0`. They validate this setting before resolving/creating output paths, opening source files or starting database installation, then pass it only to `GroupedSourceSink(write_buffer_bytes=...)`. The shared rule is exact integer 0 or 128..262144; booleans and integer subclasses are rejected. Omitting the setting keeps the original unbuffered default. Other queue, record, total, flush and capture budgets are unchanged. This setting never reaches capture options, diagnostic engines or driver connection arguments.

The user-profile example requires an existing valid `UserScope` and a dedicated native idle/autocommit setup connection on its explicitly owned database. Installation still performs the existing controlled migration; then follow the existing engine attachment, worker-stop, finalization and export protocol.

```python
from moontxnwitness_capture.profiles.fastapi_users import install_user_profile

capture, control = install_user_profile(
    setup_connection, user_scope, "new-user-profile",
    source_write_buffer_bytes=64 * 1024,
)
```

The list/relation example requires an existing immutable `ModelScope` and the same dedicated setup-connection contract. Configure its existing local synchronous business-connection factory on the returned capture; buffer configuration belongs to installation, not `connect` arguments.

```python
from moontxnwitness_capture.profiles.model_profile import install_model_profile

capture, control = install_model_profile(
    setup_connection, model_scope, "new-model-profile",
    source_write_buffer_bytes=64 * 1024,
)
```

The two installation examples are checked with fake control/installation/capture objects and real source files in pure tests. They have not been rerun against PostgreSQL with this option. Replacing an active profile sink remains unsupported because it loses the original source window.

`GroupedSourceSink.close()` and the installed profiles' `finalize()` propagate source storage errors. The profiles' existing diagnostic cleanup `close()` is best effort: it records `profile_source_storage_failed` or `model_source_storage_failed` after a source close error and can still return a diagnostic result. That return is not a sealed-source guarantee; `export_profile()` independently verifies source guards and refuses failed storage. Missing finalization already records an unclosed-window gap. Do not infer complete coverage from cleanup alone.

The legacy `_orm_source_sink.SourceSink` retains its per-record flush/fsync and original defaults. Segmented event journal, lifecycle log and observer configuration are unchanged. Valid source storage still declares `completeCapture=false` and `coreProofAccepted=false`.

## Evidence and pending acceptance

The frozen full-capture cost experiment already used grouped sources. Its eligible results remain C/A throughput about 0.11-0.225 and the C/A P95 latency ratio about 3.7-7.3, outside the 0.90 / 1.15 targets. Passing file-I/O tests and fewer raw write calls do not establish throughput or latency improvement. CPU/lock/disk attribution and actual A/B/C improvement remain unmeasured for this buffer candidate.

A formal measurement needs a separately frozen protocol selecting this option and all existing capture boundaries. Existing qualifying/failing receipts, experiment inputs and defaults are not rewritten. Pure tests, injected failures and fake driver/profile objects are not database acceptance, physical disk-full tests, power-loss testing or default-adoption certification. Cross-platform file buffering behavior and a real installed-profile database run remain pending.

With the existing pinned Python dependencies installed, run `python -B scripts/source-buffer-unit-test.py` from the repository. This standalone pure-test entry covers source storage, flush watermarks, configuration rejection, cleanup/finalization boundaries and this example; it blocks database/network connections and saves source hashes and the original test log. It does not add the suite to existing release or CI workflows.

## 使用边界

默认缓冲仍为 0；两个安装入口可用仅关键字参数 source_write_buffer_bytes 显式启用，最多额外使用 256 KiB，且在任何安装副作用前校验。入队、文件对象接收和来源数据及索引已同步是不同状态。关闭来源写入器或正式完成 profile 时错误会向调用方传播；普通 profile 清理关闭会记录失败缺口，因此不能只凭其返回值认定来源密封。旧逐条同步入口不变，现有采集性能目标尚未达到。
