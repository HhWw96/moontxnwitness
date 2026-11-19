#!/usr/bin/env node
// Recompute real configured-window observations with an independently selected core.
// Source logs remain unauthenticated; rehashing here deliberately tests semantics,
// not protection against wholesale replacement of every original observation.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { copyFile, mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const pending = process.argv.slice(2);
const args = {};
while (pending.length) {
  const arg = pending.shift(), at = arg.indexOf('=');
  assert(arg.startsWith('--'), `Expected --name=value or --name value, received ${arg}`);
  const name = arg.slice(2, at > 2 ? at : undefined);
  const value = at > 2 ? arg.slice(at + 1) : pending.shift();
  assert(typeof value === 'string' && value.length > 0 && !value.startsWith('--') && !Object.hasOwn(args, name), `Missing or duplicate --${name}`);
  args[name] = value;
}
for (const name of ['core', 'receipt', 'output']) assert(args[name], `Missing --${name}`);
for (const name of Object.keys(args)) assert(['core', 'receipt', 'output'].includes(name), `Unknown --${name}`);

const sha = (text) => createHash('sha256').update(text).digest('hex');
const clone = (value) => structuredClone(value);
const stringify = (value) => JSON.stringify(value);
const jsonl = (text) => text.trimEnd().split('\n').map((line) => JSON.parse(line));
const frame = (event) => JSON.parse(event.frameText);
const setFrame = (event, value) => { event.frameText = stringify(value); };

// Rebuild sequence references and the exact-byte seal after structural changes.
function reseal(events) {
  const body = events.filter((event) => event.kind !== 'seal');
  const seqMap = new Map(body.map((event, index) => [event.seq, index + 1]));
  for (const event of body) {
    if (event.requestSeq != null) event.requestSeq = seqMap.get(event.requestSeq) ?? event.requestSeq;
    if (event.frameText != null) {
      const value = frame(event);
      if (value.projectionNoteSeq != null) {
        value.projectionNoteSeq = seqMap.get(value.projectionNoteSeq) ?? value.projectionNoteSeq;
      }
      setFrame(event, value);
    }
    event.seq = seqMap.get(event.seq);
  }
  const prefix = body.map(stringify).join('\n') + '\n';
  return prefix + stringify({ seq: body.length + 1, kind: 'seal', records: body.length, prefixSha256: sha(prefix) }) + '\n';
}

function changeLifecycle(bundle, mutate) {
  const events = jsonl(bundle.lifecycleText);
  mutate(events);
  bundle.lifecycleText = reseal(events);
}

function deliveredResult(events) {
  const delivery = events.find((event) => event.kind === 'configured-point-delivery' && frame(event).rows.length > 0);
  assert(delivery, 'No nonempty delivery');
  const resultId = frame(delivery).resultId;
  const native = events.find((event) => event.kind === 'configured-point-native' && frame(event).resultId === resultId);
  assert(native && native.seq < delivery.seq, 'No preceding matching native result');
  const projection = events.find((event) => event.kind === 'configured-point-projection' && event.seq === frame(native).projectionNoteSeq);
  assert(projection, 'No matching projection');
  return { delivery, native, projection };
}

function changeSnapshot(bundle, side, mutate) {
  const key = `${side}InputText`;
  const envelope = JSON.parse(bundle[key]);
  const receipt = JSON.parse(envelope.receiptText);
  const events = jsonl(envelope.logText);
  mutate(events, receipt);
  envelope.logText = reseal(events);
  receipt.log.bytes = Buffer.byteLength(envelope.logText);
  receipt.log.records = jsonl(envelope.logText).length;
  receipt.log.sha256 = sha(envelope.logText);
  envelope.receiptText = stringify(receipt);
  bundle[key] = stringify(envelope);
  changeLifecycle(bundle, (lifecycle) => {
    const boundary = lifecycle.find((event) => event.kind === `configured-window-${side}`);
    assert(boundary, `No ${side} boundary`);
    const value = frame(boundary);
    value.snapshotInputSha256 = sha(bundle[key]);
    setFrame(boundary, value);
  });
}

// Update both PostgreSQL raw bytes and the corresponding actually delivered value.
function changeControlPayload(events, queryId, select, mutate) {
  for (const native of events.filter((event) => event.kind === 'control-native' && event.queryId === queryId)) {
    if (native.native.rows.length !== 1) continue;
    const payload = JSON.parse(Buffer.from(native.native.rows[0][0], 'base64').toString('utf8'));
    if (!select(payload)) continue;
    mutate(payload);
    const text = stringify(payload);
    native.native.rows[0][0] = Buffer.from(text).toString('base64');
    const delivery = events.find((event) => event.kind === 'control-delivery' && event.requestSeq === native.requestSeq);
    assert(delivery?.observation.rows[0]?.cells[0], 'No matching control delivery');
    delivery.observation.rows[0].cells[0].value = text;
    return payload;
  }
  throw new Error(`No matching ${queryId} payload`);
}

const output = path.resolve(args.output);
const directory = path.dirname(output);
await mkdir(directory, { recursive: true });
const receiptText = await readFile(args.receipt, 'utf8');
const campaign = JSON.parse(receiptText);
assert.equal(campaign.passed, true, 'Original database campaign did not pass');
assert.equal(campaign.actualDatabaseExecution, true, 'Need actual database observations');
assert.equal(campaign.analysisFixturesRequested, true, 'Campaign lacks analysis fixtures');
assert(Array.isArray(campaign.records) && campaign.records.length > 0, 'No campaign records');
const coreBytes = await readFile(args.core);
const corePath = path.join(directory, `configured-window-core-${sha(coreBytes).slice(0, 16)}.mjs`);
await copyFile(args.core, corePath);
const core = await import(pathToFileURL(corePath).href);
assert.equal(typeof core.analyze_configured_window_v2_json, 'function');
assert.equal(typeof core.verify_configured_window_v2_json, 'function');

const checks = [];
const fixtures = [];
const snapshotReaders = new Map();
async function check(id, run) {
  try {
    const details = await run();
    checks.push({ id, passed: true, ...details });
  } catch (error) {
    checks.push({ id, passed: false, error: error.stack ?? String(error) });
    process.stderr.write(`FAIL ${id}: ${error.message}\n`);
  }
}
function summarize(report) {
  return {
    status: report.status, coverageComplete: report.coverageComplete,
    sourceMappingVerified: report.sourceMappingVerified, writerWindowVerified: report.writerWindowVerified,
    decisionBasis: report.modelDecision?.basis, serialStatus: report.serialReplay?.judgment?.status,
    reason: report.reason ?? null,
  };
}
function incomplete(report) {
  assert(['unknown', 'invalid'].includes(report.status), `Unexpected rejection status ${report.status}`);
  assert.equal(report.coverageComplete, false);
  assert.notEqual(report.sourceMappingVerified, true);
  assert.notEqual(report.writerWindowVerified, true);
  assert.equal(report.sourceAuthenticated, false);
  assert.equal(typeof report.reason, 'string');
  assert(report.reason.length > 0, 'Rejection must provide a reason');
}

for (const record of campaign.records) {
  assert(record.analysisFixtures?.length > 0, 'Record lacks fixtures');
  for (const fixture of record.analysisFixtures) {
    const id = `${record.keyType}/${fixture.name}`;
    const raw = await readFile(fixture.bundle, 'utf8');
    assert.equal(sha(raw), fixture.bundleSha256, `Changed original bundle ${id}`);
    const bundle = JSON.parse(raw);
    assert.equal(bundle.format, 'moontxnwitness-configured-window-input/v2');
    const configText = stringify(fixture.config);
    const policyText = stringify(fixture.policy);
    const snapshotComparison = ['snapshot-row-v2', 'snapshot-paged-v1'].includes(fixture.name);
    const optionsText = (options) => stringify({ ...fixture.analysisOptions, ...options });
    const analyze = (text = raw, options = {}) => JSON.parse(core.analyze_configured_window_v2_json(configText, policyText, text, optionsText(options)));
    const verify = (report, text = raw, options = {}) => JSON.parse(core.verify_configured_window_v2_json(configText, policyText, text, stringify(report), optionsText(options)));
    const report = analyze();
    const reportPath = path.join(directory, `${record.keyType}-${fixture.name}-report.json`);
    await writeFile(reportPath, JSON.stringify(report, null, 2) + '\n');
    fixtures.push({ id, expected: fixture.expected, bundle: fixture.bundle, bundleSha256: sha(raw), report: reportPath, reportSha256: sha(await readFile(reportPath)), actual: summarize(report) });

    await check(`${id}/expected-result`, () => {
      const expectedStatus = { compatible: 'checked-compatible', refuted: 'refuted', unknown: 'unknown' }[fixture.expected];
      assert(expectedStatus, `Unknown fixture expectation ${fixture.expected}`);
      assert.equal(report.status, expectedStatus);
      assert.equal(report.coverageComplete, fixture.coverageComplete ?? fixture.expected !== 'unknown');
      assert.equal(report.sourceAuthenticated, false);
      if (fixture.expectedReason) assert(report.reason?.includes(fixture.expectedReason), report.reason);
      if (fixture.expected !== 'unknown') {
        assert.equal(report.sourceMappingVerified, true);
        assert.equal(report.writerWindowVerified, true);
      }
      if (fixture.expected === 'compatible') {
        assert.equal(report.serialReplay?.judgment?.status, 'consistent');
        assert.equal(report.serialReplay?.judgment?.evidence?.kind, 'serial-relation-replay');
        assert(report.serialReplay.judgment.evidence.serialOrder.length > 0);
      }
      if (fixture.expected === 'refuted') {
        const rule = report.itemCategory?.judgment?.rules?.['G2-item'];
        assert.equal(rule?.status, 'refuted');
        assert.equal(rule.evidence?.specificCategory, 'G2-item');
        assert(rule.evidence.edges.length >= 2);
        for (const edge of rule.evidence.edges) {
          assert(edge.sources?.length > 0, 'Cycle edge lacks row-version sources');
          assert(edge.observationLinks?.length > 0, 'Cycle edge lacks observation links');
        }
      }
      return summarize(report);
    });
    await check(`${id}/exact-independent-verification`, () => {
      const result = verify(report);
      assert.equal(result.reportMatches, true);
      assert.equal(result.valid, fixture.expected !== 'unknown');
      return { valid: result.valid, reportMatches: result.reportMatches };
    });
    if (fixture.name === 'async-sqlalchemy-prefetched-unread') {
      await check(`${id}/prefetch-is-not-delivery`, () => {
        const events = jsonl(bundle.lifecycleText);
        const nonempty = events.filter((event) => event.kind === 'configured-point-native' && frame(event).native.rows.length === 1);
        const undelivered = nonempty.at(-1);
        assert(undelivered);
        const resultId = frame(undelivered).resultId;
        assert(!events.some((event) => event.kind === 'configured-point-delivery' && frame(event).resultId === resultId));
      });
    }
    if (fixture.name === 'snapshot-paged-late-commit') {
      await check(`${id}/late-lower-version-admitted`, () => {
        assert(BigInt(fixture.lateVersion) < BigInt(fixture.earlierVisibleMaximum));
        assert(!Object.hasOwn(report.startSnapshot.effects, fixture.lateVersion));
        assert(Object.hasOwn(report.endSnapshot.effects, fixture.lateVersion));
        assert.equal(report.endSnapshot.effectsObserved - report.startSnapshot.effectsObserved, 2);
      });
      continue;
    }
    if (snapshotComparison) {
      await check(`${id}/point-footprint-retains-full-snapshot`, () => {
        assert.equal(report.semanticContract, 'postgres18-source-bound-point-crud-touched-keys/v1');
        const rows = report.history.events[0].initial.configured_row;
        assert.deepEqual(rows.map(r => r.key).sort((a,b) => Number(a)-Number(b)), ['1','128','129','256','257','260']);
        assert.equal(report.startSnapshot.rowsObserved, 260);
        assert.equal(report.endSnapshot.effectsObserved, 260);
      });
      snapshotReaders.set(fixture.name, {
        decision: summarize(report),
        inventories: ['startInputText', 'endInputText'].map((key) => {
          const original = JSON.parse(JSON.parse(bundle[key]).receiptText);
          return [original.visibleRowVersions, original.effectVersions];
        }),
      });
      if (fixture.name === 'snapshot-paged-v1') {
        for (const queryId of ['visible-row-page', 'retained-effect-page']) {
          await check(`${id}/${queryId}-full-short-empty`, () => {
            for (const key of ['startInputText', 'endInputText']) {
              const rows = jsonl(JSON.parse(bundle[key]).logText);
              assert.deepEqual(rows.filter((r) => r.kind === 'control-native' && r.queryId === queryId)
                .map((r) => r.native.rowCount), [128, 128, 4, 0]);
            }
          });
          for (const index of [1, 3]) {
            await check(`${id}/${queryId}-removed-page-${index}`, () => {
              const altered = clone(bundle);
              changeSnapshot(altered, 'end', (events) => {
                const request = events.filter((r) => r.kind === 'control-request' && r.queryId === queryId)[index];
                assert(request);
                for (let i = events.length - 1; i >= 0; i--) {
                  if (events[i].seq === request.seq || events[i].requestSeq === request.seq) events.splice(i, 1);
                }
              });
              incomplete(analyze(stringify(altered)));
            });
          }
        }
        await check(`${id}/duplicate-original-row-with-valid-hashes`, () => {
          const altered = clone(bundle);
          changeSnapshot(altered, 'start', (events) => {
            const first = events.find((r) => r.kind === 'control-native' && r.queryId === 'visible-row-page');
            const delivery = events.find((r) => r.kind === 'control-delivery' && r.requestSeq === first.requestSeq);
            assert(first.native.rows.length > 1 && delivery.observation.rows.length > 1);
            first.native.rows[1] = first.native.rows[0];
            delivery.observation.rows[1] = delivery.observation.rows[0];
          });
          incomplete(analyze(stringify(altered)));
        });
        await check(`${id}/budget-across-multiple-pages`, () => {
          incomplete(analyze(raw, { maxRows: 259 }));
          incomplete(analyze(raw, { maxEffects: 259 }));
        });
        await check(`${id}/paging-requires-point-footprint`, () => {
          const refused = analyze(raw, { pointFootprintOnly: false });
          incomplete(refused);
          assert(refused.reason.includes('window-paged-requires-point-footprint'));
        });
      }
      continue;
    }
    await check(`${id}/forged-verdict-rejected`, () => {
      const forged = clone(report);
      forged.status = report.status === 'refuted' ? 'checked-compatible' : 'refuted';
      const result = verify(forged);
      assert.equal(result.valid, false); assert.notEqual(result.reportMatches, true);
      return { valid: result.valid };
    });
    await check(`${id}/forged-budget-rejected`, () => {
      const forged = clone(report);
      if (forged.execution) forged.execution.maxSourceChecks = 0;
      else forged.execution = { maxSourceChecks: 0 };
      const result = verify(forged);
      assert.equal(result.valid, false); assert.notEqual(result.reportMatches, true);
      return { valid: result.valid };
    });
    if (fixture.name === 'snapshot-paged-write-skew') {
      await check(`${id}/complete-source-and-paged-model-refutation`, () => {
        assert.equal(report.semanticContract, 'postgres18-source-bound-point-crud-touched-keys/v1');
        assert.equal(report.startSnapshot.rowsObserved, 260);
        assert.equal(report.endSnapshot.effectsObserved - report.startSnapshot.effectsObserved, 2);
        assert.equal(report.history.events.filter(event => event.kind === 'begin').length, 3);
        assert.equal(verify(report, raw, { maxPointChecks: 0 }).valid, false);
      });
      continue;
    }
    if (report.serialReplay?.judgment?.evidence?.kind === 'serial-relation-replay') {
      await check(`${id}/forged-serial-certificate-rejected`, () => {
        const forged = clone(report);
        forged.serialReplay.judgment.evidence.serialOrder[0] = 'not-an-observed-transaction';
        const result = verify(forged);
        assert.equal(result.valid, false); assert.notEqual(result.reportMatches, true);
        return { valid: result.valid };
      });
    }
    if (report.itemCategory?.judgment?.rules?.['G2-item']?.status === 'refuted') {
      await check(`${id}/forged-dependency-witness-rejected`, () => {
        const forged = clone(report);
        forged.itemCategory.judgment.rules['G2-item'].evidence.edges[0].edge.fromVersion = 'row:unobserved';
        const result = verify(forged);
        assert.equal(result.valid, false); assert.notEqual(result.reportMatches, true);
        return { valid: result.valid };
      });
    }
    for (const option of ['maxSourceChecks', 'maxPointChecks']) {
      await check(`${id}/${option}-zero`, () => {
        const limited = analyze(raw, { [option]: 0 });
        incomplete(limited);
        assert.equal(limited.status, 'unknown');
        assert.equal(verify(report, raw, { [option]: 0 }).valid, false);
        return summarize(limited);
      });
    }
    await check(`${id}/independent-serial-budget`, () => {
      const limited = analyze(raw, { maxSerialOperationChecks: 0 });
      assert.notEqual(limited.serialReplay?.judgment?.status, 'consistent');
      assert.notEqual(limited.modelDecision?.basis, 'complete-serial-relation-replay');
      if (limited.coverageComplete === true && limited.status === 'checked-compatible') {
        assert.equal(limited.modelDecision?.basis, 'relation-atomic-row-graph');
        assert.equal(limited.model?.status, 'checked-compatible');
      }
      if (fixture.expected === 'refuted') assert.equal(limited.status, 'refuted', 'Independent graph refutation must remain available');
      if (fixture.expected !== 'unknown') assert.equal(verify(report, raw, { maxSerialOperationChecks: 0 }).valid, false);
      return summarize(limited);
    });

    // Unknown fixtures already stop at an earlier unsupported condition; mutations
    // on them would not demonstrate the intended guard and are deliberately omitted.
    if (fixture.expected === 'unknown') continue;
    for (const mode of ['lifecycle', 'nested-snapshot']) {
      await check(`${id}/rehash-only-${mode}-control`, () => {
        const rebuilt = clone(bundle);
        if (mode === 'lifecycle') changeLifecycle(rebuilt, () => {});
        else changeSnapshot(rebuilt, 'end', () => {});
        const rebuiltText = stringify(rebuilt);
        const actual = analyze(rebuiltText);
        assert.equal(actual.status, report.status, actual.reason);
        assert.equal(actual.coverageComplete, true, actual.reason);
        assert.equal(verify(actual, rebuiltText).valid, true);
        return summarize(actual);
      });
    }
    async function tamper(name, mutate, reasonPart = null) {
      await check(`${id}/${name}`, () => {
        const altered = clone(bundle);
        mutate(altered);
        const alteredText = stringify(altered);
        assert.notEqual(sha(alteredText), sha(raw), 'Mutation did not change the input');
        const actual = analyze(alteredText);
        incomplete(actual);
        if (reasonPart) assert(actual.reason.includes(reasonPart), actual.reason);
        assert.equal(verify(report, alteredText).valid, false);
        return { ...summarize(actual), mutatedBundleSha256: sha(alteredText), rehashed: true };
      });
    }
    await tamper('deleted-native-observation', (altered) => changeLifecycle(altered, (events) => {
      const index = events.findIndex((event) => event.kind === 'configured-point-native');
      assert(index >= 0); events.splice(index, 1);
    }));
    await tamper('reordered-native-delivery', (altered) => changeLifecycle(altered, (events) => {
      const { native, delivery } = deliveredResult(events);
      [events[native.seq - 1], events[delivery.seq - 1]] = [delivery, native];
    }));
    await tamper('native-value-disagrees-with-delivery', (altered) => changeLifecycle(altered, (events) => {
      const { native } = deliveredResult(events);
      const value = frame(native);
      value.native.rows[0][0] = Buffer.from('changed-native-value').toString('base64');
      setFrame(native, value);
    }));
    await tamper('partial-business-delivery', (altered) => changeLifecycle(altered, (events) => {
      const event = events.find((event) => event.kind === 'configured-point-delivery' && frame(event).rows.length > 0);
      assert(event, 'No nonempty delivery');
      const value = frame(event); value.rows = []; value.exhaustedObserved = false;
      setFrame(event, value);
    }));
    await tamper('projection-native-delivery-wrong-connection', (altered) => changeLifecycle(altered, (events) => {
      const { delivery, native, projection } = deliveredResult(events);
      for (const event of [projection, native, delivery]) {
        const value = frame(event);
        value.connection = 'connection-not-opened';
        setFrame(event, value);
      }
    }));
    await tamper('removed-commit-confirmation', (altered) => changeLifecycle(altered, (events) => {
      const index = events.findIndex((event) => event.kind === 'commit-response');
      assert(index >= 0); events.splice(index, 1);
    }));
    await tamper('changed-native-command-tag', (altered) => changeLifecycle(altered, (events) => {
      const event = events.find((event) => event.kind === 'commit-response');
      assert(event); event.commandTag = 'ROLLBACK';
    }));
    if (fixture.asynchronous === true) {
      await tamper('async-connection-mode-mismatch', (altered) => changeLifecycle(altered, (events) => {
        const event = events.find((entry) => entry.kind === 'connect');
        assert.equal(event?.asynchronous, true);
        event.asynchronous = false;
      }), 'window-connection');
    }
    await tamper('diagnostic-rows-impossible-statement', (altered) => {
      const trace = JSON.parse(altered.diagnosticTraceText);
      const rows = trace.events.find((event) => event.kind === 'rows');
      assert(rows); rows.statement = 2147483647;
      altered.diagnosticTraceText = stringify(trace);
    });
    await tamper('diagnostic-rows-wrong-transaction-statement', (altered) => {
      const trace = JSON.parse(altered.diagnosticTraceText);
      const rows = trace.events.find((event) => event.kind === 'rows' && trace.events.some((candidate) => candidate.kind === 'statement' && candidate.tx !== event.tx));
      assert(rows, 'Need two captured transactions');
      rows.statement = trace.events.find((event) => event.kind === 'statement' && event.tx !== rows.tx).seq;
      altered.diagnosticTraceText = stringify(trace);
    });
    await tamper('changed-boundary-snapshot', (altered) => {
      const start = altered.startInputText; altered.startInputText = altered.endInputText; altered.endInputText = start;
      changeLifecycle(altered, (events) => {
        for (const side of ['start', 'end']) {
          const event = events.find((entry) => entry.kind === `configured-window-${side}`);
          const value = frame(event); value.snapshotInputSha256 = sha(altered[`${side}InputText`]); setFrame(event, value);
        }
      });
    });
    await tamper('effect-writer-forgery-rehashed-through-boundary', (altered) => {
      const initial = new Set(JSON.parse(JSON.parse(altered.startInputText).receiptText).effectVersions);
      changeSnapshot(altered, 'end', (events) => {
        changeControlPayload(events, 'retained-effect', (effect) => !initial.has(effect.version), (effect) => { effect.writerXid = '999999999'; });
      });
    });
    await tamper('effect-row-forgery-rehashed-through-boundary', (altered) => {
      const initial = new Set(JSON.parse(JSON.parse(altered.startInputText).receiptText).effectVersions);
      changeSnapshot(altered, 'end', (events) => {
        changeControlPayload(events, 'retained-effect', (effect) => !initial.has(effect.version) && effect.rowValues != null, (effect) => {
          const column = fixture.config.table.businessColumns[0];
          effect.rowValues[column.name] = column.type === 'bool' ? !effect.rowValues[column.name] : column.type === 'int64' ? 998877 : 'forged row value';
        });
      });
    });
    await tamper('missing-retained-effect-with-rehashed-claims', (altered) => {
      const initial = new Set(JSON.parse(JSON.parse(altered.startInputText).receiptText).effectVersions);
      changeSnapshot(altered, 'end', (events, receipt) => {
        const native = events.find((event) => event.kind === 'control-native' && event.queryId === 'retained-effect' && event.native.rows.length > 0 && !initial.has(JSON.parse(Buffer.from(event.native.rows[0][0], 'base64').toString('utf8')).version));
        assert(native, 'No added retained effect');
        const effect = JSON.parse(Buffer.from(native.native.rows[0][0], 'base64').toString('utf8'));
        const requestSeq = native.requestSeq;
        const request = events.find((event) => event.seq === requestSeq);
        const nextRequest = events.find((event) => event.kind === 'control-request' && event.queryId === 'retained-effect' && event.seq > requestSeq);
        assert(request && nextRequest);
        // Keep the enumeration cursor locally consistent after dropping the
        // observation, so rejection cannot rely only on a broken cursor chain.
        nextRequest.parameters = clone(request.parameters);
        for (let index = events.length - 1; index >= 0; index--) {
          if (events[index].seq === requestSeq || events[index].requestSeq === requestSeq) events.splice(index, 1);
        }
        receipt.effectVersions = receipt.effectVersions.filter((version) => version !== effect.version);
        receipt.effectsObserved--;
      });
    });
    await check(`${id}/original-input-unchanged`, async () => {
      assert.equal(sha(await readFile(fixture.bundle)), fixture.bundleSha256);
      return { bundleSha256: fixture.bundleSha256 };
    });
  }
}

assert.equal(sha(await readFile(args.receipt)), sha(receiptText), 'Original campaign receipt changed');
if (snapshotReaders.size !== 0) {
  await check('snapshot-reader-equivalence', () => {
    assert.equal(snapshotReaders.size, 2);
    assert.deepEqual(snapshotReaders.get('snapshot-row-v2'), snapshotReaders.get('snapshot-paged-v1'));
  });
}
const failed = checks.filter((entry) => !entry.passed);
const result = {
  format: 'moontxnwitness-configured-window-adversarial-check/v2',
  passed: failed.length === 0, actualDatabaseExecution: false,
  originalReceiptActualDatabaseExecution: campaign.actualDatabaseExecution,
  originalReceipt: path.resolve(args.receipt), originalReceiptSha256: sha(receiptText),
  core: path.resolve(args.core), coreSha256: sha(coreBytes),
  fixtureCount: fixtures.length, checkCount: checks.length, passedChecks: checks.length - failed.length,
  failedChecks: failed.length, fixtures, checks,
};
await writeFile(output, JSON.stringify(result, null, 2) + '\n');
process.stdout.write(`${result.passed ? 'PASS' : 'FAIL'} ${result.passedChecks}/${result.checkCount} checks, ${fixtures.length} fixtures; ${output}\n`);
if (!result.passed) process.exitCode = 1;
