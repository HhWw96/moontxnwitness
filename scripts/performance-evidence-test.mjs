// Small real-filesystem failure tests; no engine or benchmark is executed.
import assert from 'node:assert/strict';
import * as fs from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { EvidenceIoError, PerformanceEvidenceJournal, recoverPerformanceEvidence,
  writeImmutableEvidence } from './performance-evidence.mjs';

const fixtures = [];
const passed = [];
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const helperPath = fileURLToPath(new URL('./performance-evidence.mjs', import.meta.url));

function setup(io = fs) {
  const root = fs.mkdtempSync(join(tmpdir(), 'moontxnwitness-evidence-'));
  fixtures.push(root);
  const directory = join(root, 'checkpoints'), latestPath = join(root, 'latest.json');
  const journal = new PerformanceEvidenceJournal({ directory, latestPath, runId: 'fault-test',
    io, maxAttempts: 3, retryDelayMs: 0 });
  return { root, directory, latestPath, journal,
    recover: () => recoverPerformanceEvidence({ directory, latestPath }) };
}

const row = index => ({ scenario: `case-${index}`, semanticAgreement: true,
  observations: { baseline: [{ timesMs: [1, 3, 2], p95Ms: 3 }],
    current: [{ timesMs: [2, 4, 3], p95Ms: 4 }] } });
const receipt = (count, complete = false) => ({ complete, passed: complete,
  smokeOnly: false, correctnessPassed: complete, formalReleaseGatePassed: complete,
  results: Array.from({ length: count }, (_, index) => row(index)), phases: [] });
const ioError = (code, syscall) => Object.assign(new Error('injected actual filesystem failure'),
  { code, errno: code === 'UNKNOWN' ? -4094 : -16, syscall });

function test(name, run) {
  run();
  passed.push(name);
  console.log(`PASS ${name}`);
}

try {
  test('partial physical writes leave the previous checkpoint and atomic pointer intact; failure snapshot preserves raw samples', () => {
    let failingDirectory = null, physicalPartialWrites = 0;
    const fdPaths = new Map();
    const io = { ...fs,
      openSync(path, ...args) {
        const fd = fs.openSync(path, ...args);
        fdPaths.set(fd, String(path));
        return fd;
      },
      writeSync(fd, buffer, offset, length, position) {
        if (failingDirectory && fdPaths.get(fd)?.startsWith(failingDirectory)) {
          fs.writeSync(fd, buffer, offset, Math.min(17, length), position);
          physicalPartialWrites++;
          throw ioError('UNKNOWN', 'write');
        }
        return fs.writeSync(fd, buffer, offset, length, position);
      },
      closeSync(fd) { fdPaths.delete(fd); return fs.closeSync(fd); },
    };
    const fixture = setup(io);
    const previous = fixture.journal.checkpoint(receipt(1));
    const beforeSnapshot = fs.readFileSync(previous.path), beforePointer = fs.readFileSync(fixture.latestPath);
    failingDirectory = fixture.directory;
    assert.throws(() => fixture.journal.checkpoint(receipt(2)), error =>
      error instanceof EvidenceIoError && error.attempts.length === 3 && error.code === 'UNKNOWN');
    assert.equal(physicalPartialWrites, 3, 'Only file writes, never benchmark operations, are retried');
    assert.deepEqual(fs.readFileSync(previous.path), beforeSnapshot);
    assert.deepEqual(fs.readFileSync(fixture.latestPath), beforePointer);
    const restored = fixture.recover();
    assert.equal(restored.source, 'published-pointer');
    assert.equal(restored.receipt.results.length, 1);
    assert.equal(restored.receipt.complete, false);
    const failed = receipt(2, true);
    failed.failedAt = 'fault-injection';
    const retained = fixture.journal.preserveInterrupted(failed, join(fixture.root, 'ignored-recovery'));
    assert.equal(retained.location, 'fallback');
    assert.equal(retained.latestUpdated, false);
    const interrupted = JSON.parse(fs.readFileSync(retained.path));
    assert.equal(interrupted.complete, false);
    assert.equal(interrupted.passed, false);
    assert.equal(interrupted.correctnessPassed, false);
    assert.equal(interrupted.formalReleaseGatePassed, false);
    assert.equal(interrupted.completedAt, undefined);
    assert.deepEqual(interrupted.results, failed.results, 'The final original raw timings survive failed public writes');
    assert.deepEqual(fs.readFileSync(fixture.latestPath), beforePointer);
    const partials = fs.readdirSync(fixture.directory).filter(name => name.endsWith('.pending'));
    assert.equal(partials.length, 6);
    for (const name of partials) assert.throws(() => JSON.parse(fs.readFileSync(join(fixture.directory, name))));
  });

  test('failed pointer replacement cannot expose a new terminal result; an interruption replaces it only after complete persistence', () => {
    let denyRename = false, attemptedRenames = 0;
    const io = { ...fs, renameSync(from, to) {
      if (denyRename) { attemptedRenames++; throw ioError('EBUSY', 'rename'); }
      return fs.renameSync(from, to);
    } };
    const fixture = setup(io);
    const previous = fixture.journal.checkpoint(receipt(1));
    const beforePointer = fs.readFileSync(fixture.latestPath), beforeSnapshot = fs.readFileSync(previous.path);
    denyRename = true;
    assert.throws(() => fixture.journal.checkpoint(receipt(2, true)), error =>
      error instanceof EvidenceIoError && error.operation === 'pointer-replace' && error.attempts.length === 3);
    assert.equal(attemptedRenames, 3);
    assert.deepEqual(fs.readFileSync(fixture.latestPath), beforePointer);
    assert.deepEqual(fs.readFileSync(previous.path), beforeSnapshot);
    assert.equal(fixture.recover().receipt.complete, false);
    assert.equal(fs.readdirSync(fixture.directory).filter(name => name.endsWith('.json')).length, 2,
      'The valid but unpublished snapshot remains recoverable');
    denyRename = false;
    const retained = fixture.journal.preserveInterrupted({ ...receipt(2, true), failedAt: 'pointer-write-failure' },
      join(fixture.root, 'ignored-recovery'));
    assert.equal(retained.location, 'journal');
    assert.equal(retained.latestUpdated, true);
    const restored = fixture.recover();
    assert.equal(restored.receipt.failedAt, 'pointer-write-failure');
    assert.equal(restored.receipt.results.length, 2);
    assert.equal(restored.pointer.complete, false);
    assert.equal(restored.pointer.formalReleaseGatePassed, false);
    assert.equal(restored.pointer.correctnessPassed, false);
  });

  test('physical partial writes to the next pointer staging file never truncate the current latest JSON', () => {
    let denyPointerWrites = false, partialPointerWrites = 0;
    const fdPaths = new Map();
    const io = { ...fs,
      openSync(path, ...args) {
        const fd = fs.openSync(path, ...args);
        fdPaths.set(fd, String(path));
        return fd;
      },
      writeSync(fd, buffer, offset, length, position) {
        if (denyPointerWrites && /[\\/]\.latest\.json\./.test(fdPaths.get(fd) || '')) {
          fs.writeSync(fd, buffer, offset, Math.min(13, length), position);
          partialPointerWrites++;
          throw ioError('UNKNOWN', 'write');
        }
        return fs.writeSync(fd, buffer, offset, length, position);
      },
      closeSync(fd) { fdPaths.delete(fd); return fs.closeSync(fd); },
    };
    const fixture = setup(io);
    fixture.journal.checkpoint(receipt(1));
    const beforePointer = fs.readFileSync(fixture.latestPath);
    denyPointerWrites = true;
    assert.throws(() => fixture.journal.checkpoint(receipt(2, true)), error =>
      error instanceof EvidenceIoError && error.operation === 'pointer-replace' && error.attempts.length === 3);
    assert.equal(partialPointerWrites, 3);
    assert.deepEqual(fs.readFileSync(fixture.latestPath), beforePointer);
    assert.doesNotThrow(() => JSON.parse(fs.readFileSync(fixture.latestPath)));
    assert.equal(fixture.recover().receipt.results.length, 1);
    assert.equal(fixture.recover().receipt.complete, false);
  });

  test('real child-process exit during a physical partial write preserves the last durable checkpoint', () => {
    const fixture = setup();
    const previous = fixture.journal.checkpoint(receipt(1));
    const beforeSnapshot = fs.readFileSync(previous.path), beforePointer = fs.readFileSync(fixture.latestPath);
    const childSource = `
      import * as fs from 'node:fs';
      const { PerformanceEvidenceJournal } = await import(process.argv[1]);
      const [directory, latestPath] = process.argv.slice(2);
      const io = { ...fs, writeSync(fd, buffer, offset, length, position) {
        fs.writeSync(fd, buffer, offset, Math.min(11, length), position);
        process.exit(73);
      } };
      const journal = new PerformanceEvidenceJournal({directory, latestPath, runId:'crashed-child',io});
      journal.checkpoint({complete:true,passed:true,correctnessPassed:true,formalReleaseGatePassed:true,results:[],phases:[]});
    `;
    const child = spawnSync(process.execPath, ['--input-type=module', '-e', childSource,
      new URL('./performance-evidence.mjs', import.meta.url).href, fixture.directory, fixture.latestPath],
    { encoding: 'utf8', windowsHide: true, timeout: 10000 });
    assert.ifError(child.error);
    assert.equal(child.status, 73, child.stderr);
    assert.deepEqual(fs.readFileSync(fixture.latestPath), beforePointer);
    assert.deepEqual(fs.readFileSync(previous.path), beforeSnapshot);
    const restored = fixture.recover();
    assert.equal(restored.receipt.results.length, 1);
    assert.equal(restored.receipt.complete, false);
    assert.ok(fs.readdirSync(fixture.directory).some(name => name.endsWith('.pending')));
  });

  test('transient file-open failures retry at most three times and commit exactly one unchanged receipt', () => {
    let denied = 2, fileOpenAttempts = 0;
    const io = { ...fs, openSync(path, ...args) {
      if (String(path).includes('.json.') && !String(path).includes('.latest.json.')) {
        fileOpenAttempts++;
        if (denied-- > 0) throw ioError('UNKNOWN', 'open');
      }
      return fs.openSync(path, ...args);
    } };
    const fixture = setup(io), expected = receipt(1);
    fixture.journal.checkpoint(expected);
    assert.equal(fileOpenAttempts, 3);
    const restored = fixture.recover();
    assert.deepEqual(restored.receipt.results, expected.results);
    assert.equal(restored.receipt.evidenceCheckpoint.sequence, 1);
    assert.equal(fs.readdirSync(fixture.directory).filter(name => name.endsWith('.json')).length, 1);
  });

  test('missing/corrupt pointer recovery ignores malformed or tampered snapshots and never infers terminal acceptance', () => {
    const fixture = setup();
    fixture.journal.checkpoint(receipt(1));
    const final = fixture.journal.checkpoint(receipt(2, true));
    fs.writeFileSync(join(fixture.directory, '999999-abcdef.json'), '{"complete":true');
    const tampered = JSON.parse(fs.readFileSync(final.path));
    tampered.results[0].observations.current[0].timesMs[0] = 99999;
    fs.writeFileSync(join(fixture.directory, '999998-abcdef.json'), JSON.stringify(tampered));
    fs.writeFileSync(fixture.latestPath, '{"receipt":');
    const restored = fixture.recover();
    assert.equal(restored.source, 'unpublished-recovery');
    assert.equal(restored.path, final.path);
    assert.equal(restored.receipt.results[0].observations.current[0].timesMs[0], 2);
    assert.equal(restored.receipt.complete, false);
    assert.equal(restored.receipt.correctnessPassed, false);
    assert.equal(restored.receipt.formalReleaseGatePassed, false);
    assert.equal(restored.receipt.recovery.publicationConfirmed, false);
  });

  test('immutable publication refuses existing different bytes and reports failure without overwriting either raw artifact', () => {
    const fixture = setup(), path = join(fixture.root, 'raw.json');
    writeImmutableEvidence(path, 'original');
    const before = hash(fs.readFileSync(path));
    assert.throws(() => writeImmutableEvidence(path, 'replacement'), error => error instanceof EvidenceIoError);
    assert.equal(hash(fs.readFileSync(path)), before);
    assert.equal(fs.readFileSync(path, 'utf8'), 'original');
  });

  test('pointer acceptance flags must agree with the hashed snapshot; external edits cannot promote an incomplete checkpoint', () => {
    const fixture = setup();
    fixture.journal.checkpoint(receipt(1));
    const pointer = JSON.parse(fs.readFileSync(fixture.latestPath));
    pointer.formalReleaseGatePassed = true;
    pointer.correctnessPassed = true;
    fs.writeFileSync(fixture.latestPath, JSON.stringify(pointer));
    const restored = fixture.recover();
    assert.equal(restored.source, 'unpublished-recovery');
    assert.equal(restored.receipt.complete, false);
    assert.equal(restored.receipt.formalReleaseGatePassed, false);
    assert.equal(restored.receipt.correctnessPassed, false);
  });

  console.log(JSON.stringify({ passed: true, tests: passed.length, cases: passed,
    benchmarkOperationsExecuted: 0, helperSha256: hash(fs.readFileSync(helperPath)) }));
} finally {
  for (const fixture of fixtures) {
    // Paths are resolved and checked before recursive deletion on Windows.
    const target = resolve(fixture), temporaryRoot = resolve(tmpdir());
    assert.ok(target.startsWith(temporaryRoot + '\\') || target.startsWith(temporaryRoot + '/'));
    assert.ok(target.split(/[\\/]/).at(-1).startsWith('moontxnwitness-evidence-'));
    fs.rmSync(target, { recursive: true, force: true });
  }
}
