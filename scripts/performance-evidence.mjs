// Filesystem-only persistence for evidence. No analysis or test is retried.
import * as fs from 'node:fs';
import { createHash, randomUUID } from 'node:crypto';
import { basename, dirname, join } from 'node:path';

const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const encode = value => Buffer.from(JSON.stringify(value, null, 2) + '\n');
const retryable = new Set(['UNKNOWN', 'EACCES', 'EAGAIN', 'EBUSY', 'EINTR', 'EIO', 'EMFILE', 'ENFILE', 'EPERM']);
const pause = milliseconds => {
  if (milliseconds) Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, milliseconds);
};

export class EvidenceIoError extends Error {
  constructor(operation, attempts, cause) {
    super(`Evidence ${operation} failed after ${attempts.length} filesystem attempt(s)`, { cause });
    this.name = 'EvidenceIoError';
    this.code = cause.code || 'EVIDENCE_IO';
    this.operation = operation;
    // Paths and OS error messages are deliberately excluded from public metadata.
    this.attempts = attempts;
  }
}

function options(value = {}) {
  const maxAttempts = value.maxAttempts ?? 3;
  if (!Number.isInteger(maxAttempts) || maxAttempts < 1 || maxAttempts > 5) {
    throw new RangeError('Evidence file I/O permits between 1 and 5 attempts');
  }
  return { io: value.io || fs, maxAttempts, retryDelayMs: value.retryDelayMs ?? 20 };
}

function retry(operation, task, configuration) {
  const attempts = [];
  for (let attempt = 1; attempt <= configuration.maxAttempts; attempt++) {
    try { return task(); }
    catch (error) {
      attempts.push({ attempt, code: error.code || null, errno: error.errno ?? null,
        syscall: error.syscall || null });
      if (!retryable.has(error.code) || attempt === configuration.maxAttempts) {
        throw new EvidenceIoError(operation, attempts, error);
      }
      pause(configuration.retryDelayMs);
    }
  }
}

function verify(path, bytes, io) {
  const actual = io.readFileSync(path);
  if (actual.length !== bytes.length || digest(actual) !== digest(bytes)) {
    const error = new Error('Evidence read-back digest differs');
    error.code = 'EVIDENCE_INTEGRITY';
    throw error;
  }
}

function temporaryFile(target, bytes, io) {
  const temporary = join(dirname(target), `.${basename(target)}.${randomUUID()}.pending`);
  let fd;
  try {
    fd = io.openSync(temporary, 'wx', 0o600);
    let offset = 0;
    while (offset < bytes.length) {
      const written = io.writeSync(fd, bytes, offset, bytes.length - offset, null);
      if (!Number.isInteger(written) || written <= 0) {
        const error = new Error('Evidence file write made no progress');
        error.code = 'EIO';
        throw error;
      }
      offset += written;
    }
    io.fsyncSync(fd);
  } finally {
    if (fd !== undefined) io.closeSync(fd);
  }
  verify(temporary, bytes, io);
  return temporary;
}

function discardTemporary(path, io) {
  // Cleanup cannot invalidate an already published file. Failed/partial staging
  // files remain recoverable, and are never candidates for the latest pointer.
  try { io.unlinkSync(path); } catch { /* retained staging file */ }
}

export function writeImmutableEvidence(target, value, configuration = {}) {
  const settings = options(configuration), { io } = settings;
  const bytes = Buffer.isBuffer(value) ? value : Buffer.from(value);
  return retry('immutable-write', () => {
    const temporary = temporaryFile(target, bytes, io);
    try {
      // A hard link publishes the already complete file atomically and refuses
      // to overwrite any existing evidence. Staging is on the same filesystem.
      try { io.linkSync(temporary, target); }
      catch (error) {
        if (error.code !== 'EEXIST') throw error;
        // An ambiguous previous filesystem result may already have published
        // these exact bytes. Different existing bytes are never replaced.
        verify(target, bytes, io);
      }
      verify(target, bytes, io);
    } finally {
      discardTemporary(temporary, io);
    }
    return { path: target, bytes: bytes.length, sha256: digest(bytes) };
  }, settings);
}

function replacePointer(target, value, configuration) {
  const { io } = configuration, bytes = encode(value);
  retry('pointer-replace', () => {
    const temporary = temporaryFile(target, bytes, io);
    try {
      // Rename stays in one directory. Readers see the previous complete JSON
      // or the new complete JSON; no in-place truncation is used.
      try { io.renameSync(temporary, target); }
      catch (error) {
        // A reported failure after a completed rename is safe only if the exact
        // intended bytes can be read back. Otherwise retain the old pointer.
        try { verify(target, bytes, io); }
        catch { throw error; }
      }
      verify(target, bytes, io);
    } finally {
      discardTemporary(temporary, io);
    }
  }, configuration);
}

// Test receipts are complete JSON documents too. Reuse the same verified atomic
// publication path; a temporary file failure must not truncate the prior result.
export function writeVerifiedJson(target, value, configuration = {}) {
  replacePointer(target, value, options(configuration));
}

function checkedSnapshot(bytes) {
  const decoded = JSON.parse(bytes);
  const { evidenceCheckpoint, ...receipt } = decoded;
  if (evidenceCheckpoint?.format !== 'moontxnwitness-performance-checkpoint-v1' ||
      !Number.isSafeInteger(evidenceCheckpoint.sequence) || evidenceCheckpoint.sequence < 1) {
    throw new Error('Unsupported evidence checkpoint');
  }
  const payload = encode(receipt);
  if (payload.length !== evidenceCheckpoint.payloadBytes || digest(payload) !== evidenceCheckpoint.payloadSha256) {
    throw new Error('Evidence checkpoint payload digest differs');
  }
  return decoded;
}

export class PerformanceEvidenceJournal {
  constructor({ directory, latestPath, reference = path => path, runId, ...configuration }) {
    this.settings = options(configuration);
    this.directory = directory;
    this.latestPath = latestPath;
    this.reference = reference;
    this.runId = runId || randomUUID();
    this.sequence = 0;
    this.lastPublished = null;
    this.settings.io.mkdirSync(directory, { recursive: true });
  }

  checkpoint(receipt) {
    const sequence = ++this.sequence;
    const { evidenceCheckpoint: priorMetadata, ...payloadReceipt } = receipt;
    const payload = encode(payloadReceipt);
    const checkpoint = { ...payloadReceipt, evidenceCheckpoint: {
      format: 'moontxnwitness-performance-checkpoint-v1', runId: this.runId, sequence,
      previous: this.lastPublished ? { receipt: this.reference(this.lastPublished.path),
        sha256: this.lastPublished.sha256 } : null,
      payloadBytes: payload.length, payloadSha256: digest(payload),
    } };
    const path = join(this.directory, `${String(sequence).padStart(6, '0')}-${randomUUID()}.json`);
    const bytes = encode(checkpoint);
    const stored = writeImmutableEvidence(path, bytes, this.settings);
    checkedSnapshot(this.settings.io.readFileSync(path));
    const pointer = { receipt: this.reference(path), sha256: stored.sha256, bytes: stored.bytes,
      runId: this.runId, checkpointSequence: sequence,
      startedAt: receipt.startedAt || null,
      complete: receipt.complete === true, passed: receipt.passed === true,
      smokeOnly: receipt.smokeOnly === true,
      correctnessPassed: receipt.complete === true && receipt.correctnessPassed === true,
      formalReleaseGatePassed: receipt.complete === true && receipt.formalReleaseGatePassed === true,
      fullScenarios: receipt.results?.length ?? 0, expectedFullScenarios: 20,
      phaseScenarios: receipt.phases?.length ?? 0, expectedPhaseScenarios: 15 };
    try { replacePointer(this.latestPath, pointer, this.settings); }
    catch (error) {
      error.recoverableSnapshot = stored;
      throw error;
    }
    this.lastPublished = stored;
    return stored;
  }

  // Independent fallback location is normally ignored artifacts/. It stores
  // the exact in-memory receipt, including the most recent worker samples.
  // It never changes the public latest pointer if the public store is failing.
  preserveInterrupted(receipt, fallbackDirectory) {
    const interrupted = { ...receipt, complete: false, passed: false,
      correctnessPassed: false, formalReleaseGatePassed: false };
    delete interrupted.completedAt;
    try { return { ...this.checkpoint(interrupted), location: 'journal', latestUpdated: true }; }
    catch (error) {
      try {
        this.settings.io.mkdirSync(fallbackDirectory, { recursive: true });
        const path = join(fallbackDirectory, `interrupted-${this.runId}-${randomUUID()}.json`);
        return { ...writeImmutableEvidence(path, encode(interrupted), this.settings),
          location: 'fallback', latestUpdated: false,
          previousPublished: this.lastPublished ? this.reference(this.lastPublished.path) : null };
      } catch (fallbackError) {
        return { location: 'memory-only', latestUpdated: false,
          previousPublished: this.lastPublished ? this.reference(this.lastPublished.path) : null,
          error, fallbackError, receipt: interrupted };
      }
    }
  }
}

export function recoverPerformanceEvidence({ directory, latestPath, resolveReference = path => path, io = fs }) {
  // Publication authority is the atomic pointer plus its exact digest. Orphans
  // can aid manual recovery, but cannot claim a completed release acceptance.
  let pointerError;
  try {
    const pointer = JSON.parse(io.readFileSync(latestPath, 'utf8'));
    const path = resolveReference(pointer.receipt), bytes = io.readFileSync(path);
    if (bytes.length !== pointer.bytes || digest(bytes) !== pointer.sha256) throw new Error('Latest pointer digest differs');
    const receipt = checkedSnapshot(bytes);
    if (receipt.evidenceCheckpoint.runId !== pointer.runId ||
        receipt.evidenceCheckpoint.sequence !== pointer.checkpointSequence ||
        (receipt.complete === true) !== pointer.complete ||
        (receipt.passed === true) !== pointer.passed ||
        (receipt.smokeOnly === true) !== pointer.smokeOnly ||
        (receipt.complete === true && receipt.correctnessPassed === true) !== pointer.correctnessPassed ||
        (receipt.complete === true && receipt.formalReleaseGatePassed === true) !== pointer.formalReleaseGatePassed ||
        (receipt.results?.length ?? 0) !== pointer.fullScenarios ||
        (receipt.phases?.length ?? 0) !== pointer.phaseScenarios) throw new Error('Latest pointer metadata differs');
    return { source: 'published-pointer', path, receipt, pointer };
  } catch (error) { pointerError = error; }
  const candidates = [];
  for (const name of io.readdirSync(directory)) {
    if (!/^\d{6}-[a-f0-9-]+\.json$/.test(name)) continue;
    try {
      const path = join(directory, name), receipt = checkedSnapshot(io.readFileSync(path));
      candidates.push({ path, receipt });
    } catch { /* Partial, malformed, and integrity-failing files are not recovery candidates. */ }
  }
  candidates.sort((a, b) => b.receipt.evidenceCheckpoint.sequence - a.receipt.evidenceCheckpoint.sequence);
  if (!candidates.length) throw new Error('No valid performance evidence checkpoint is recoverable', { cause: pointerError });
  const recovered = candidates[0];
  return { source: 'unpublished-recovery', path: recovered.path, receipt: {
    ...recovered.receipt, complete: false, passed: false, correctnessPassed: false,
    formalReleaseGatePassed: false, recovery: { publicationConfirmed: false,
      explanation: 'Recovered immutable snapshot; terminal acceptance is not confirmed by a valid latest pointer' },
  } };
}
