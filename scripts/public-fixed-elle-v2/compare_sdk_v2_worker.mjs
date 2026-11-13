// Only this isolated worker imports the caller-bound SDK, after reference sealing.
import assert from 'node:assert/strict';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parentPort, workerData } from 'node:worker_threads';
import { evaluateSdkCase, runtimeSnapshot } from './compare_sdk_v2.mjs';

try {
  const snapshot = runtimeSnapshot(workerData.dist, workerData.expectedVersion, workerData.expectedCoreSha);
  assert.deepEqual(snapshot, workerData.snapshot);
  const api = await import(pathToFileURL(resolve(workerData.dist, 'models-v4.mjs')));
  const core = await import(pathToFileURL(resolve(workerData.dist, 'core.mjs')));
  assert.equal(typeof api.classifyModelsV4, 'function');
  assert.equal(typeof api.verifyModelsV4, 'function');
  assert.equal(core.version(), workerData.expectedVersion);
  parentPort.on('message', ({ id, row, reference }) => {
    const result = evaluateSdkCase(api, row, reference,
      (phase, payload) => parentPort.postMessage({ id, kind: 'phase', phase, payload }));
    parentPort.postMessage({ id, kind: 'result', result });
  });
  parentPort.postMessage({ kind: 'ready', snapshot });
} catch (error) {
  parentPort.postMessage({ kind: 'initialization-failed', error: String(error.stack || error) });
  process.exitCode = 1;
}
