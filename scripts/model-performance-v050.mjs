/**
 * Full-call model benchmark; controller and isolated worker share this file.
 *
 * node scripts/model-performance-v050.mjs --config D:\path\config.json --output D:\path\new-run
 * --smoke is deliberately nonformal: 1 warmup, 2 samples, 1 batch.
 * --describe-cases lists maintained fixture IDs without running measurements.
 *
 * Config schema:
 * {schemaVersion:1, exclusiveExecution:true, groups:[{
 *   id:'inference-v043', api:'classifyWithInferenceV4',
 *   baseline:{sdk:'D:/baseline/dist/sdk.mjs',sourceCommit:'...'},
 *   candidate:{sdk:'D:/candidate/dist/sdk.mjs',sourceCommit:'...'},
 *   cases:['register-full','list-prefix','relation-atomic','register-noise',
 *          {id:'zero-control',fixture:'register-budget',control:true}]
 * }]}
 * Each case may override options, or supply sourcePath/sourceJson instead of a
 * maintained fixture. Paths resolve relative to the config, never a runtime.
 * Reduction APIs use explicit cases/options matching both SDK versions.
 */
import {createHash} from 'node:crypto';
import {existsSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync} from 'node:fs';
import {dirname, join, relative, resolve, sep} from 'node:path';
import {arch, cpus, freemem, hostname, platform, release, totalmem, version as osVersion} from 'node:os';
import {performance} from 'node:perf_hooks';
import {spawnSync} from 'node:child_process';
import {fileURLToPath, pathToFileURL} from 'node:url';

const SELF = fileURLToPath(import.meta.url);
const ROOT = resolve(dirname(SELF), '..');
let activeOutput = null;
const APIS = new Set(['classifyModelsV4', 'classifyWithInferenceV4', 'classifyRelationModelsV4', 'reduceRelationModelsV4']);
const REPORT_FORMATS = Object.freeze({
  classifyModelsV4: 'moontxnwitness-model-composition/v4',
  classifyWithInferenceV4: 'moontxnwitness-model-inference-composition/v4',
  classifyRelationModelsV4: 'moontxnwitness-relation-model-composition/v4',
  reduceRelationModelsV4: 'moontxnwitness-relation-model-reduction/v4',
});
const FORMAL = Object.freeze({warmups: 5, samples: 30, batches: 3});
const SMOKE = Object.freeze({warmups: 1, samples: 2, batches: 1});
const hash = data => createHash('sha256').update(data).digest('hex');
const json = value => JSON.stringify(value, null, 2) + '\n';
const exclusive = (path, value) => writeFileSync(path, typeof value === 'string' ? value : json(value), {flag: 'wx'});
const idValid = value => typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/.test(value);
const assert = (condition, message) => { if (!condition) throw new Error(message); };

function stats(values) {
  assert(values.length > 0 && values.every(Number.isFinite), 'Statistics require finite samples');
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return {
    count: sorted.length,
    median: sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2,
    p95: sorted[Math.max(0, Math.ceil(sorted.length * 0.95) - 1)],
    minimum: sorted[0],
    maximum: sorted.at(-1),
  };
}

function geometricMean(values) {
  return values.length && values.every(value => Number.isFinite(value) && value > 0)
    ? Math.exp(values.reduce((sum, value) => sum + Math.log(value), 0) / values.length)
    : null;
}

function examples(name) {
  return readFileSync(resolve(ROOT, 'examples', name), 'utf8');
}

function noisyRegister() {
  const trace = JSON.parse(examples('register-cycle.json'));
  const initial = trace.events[0].initial;
  const body = trace.events.slice(1);
  for (let i = 0; i < 48; i++) {
    const key = 'noise-key-' + i, tx = 'noise-' + i;
    initial[key] = 'noise-initial-' + i;
    body.push({kind: 'begin', tx, connection: tx});
    body.push({kind: 'read', tx, key, version: initial[key]});
    body.push({kind: 'commit_request', tx});
    body.push({kind: 'commit_ok', tx});
  }
  trace.events = [trace.events[0], ...body].map((event, index) => ({...event, seq: index + 1, time: index}));
  trace.clockDomain = 'model-performance-fixed-noise/v1';
  return JSON.stringify(trace);
}

function noisyRelation() {
  const trace = JSON.parse(examples('relation-predicate-categories.json'));
  for (let i = 0; i < 24; i++) {
    const tx = 'noise-' + i;
    trace.events.push({kind: 'begin', tx, connection: tx});
    trace.events.push({kind: 'row_read', tx, relation: 'items', predicate: [{column: 'id', op: 'eq', value: String(1000 + i)}], rows: [], complete: true});
    trace.events.push({kind: 'commit_request', tx});
    trace.events.push({kind: 'commit_ok', tx});
  }
  trace.events = trace.events.map((event, index) => ({...event, seq: index + 1, time: index}));
  trace.clockDomain = 'relation-performance-fixed-noise/v1';
  return JSON.stringify(trace);
}

const CASES = Object.freeze({
  'register-full': {source: () => examples('models-v4-register.json'), options: {}},
  'list-prefix': {source: () => examples('models-v4-list.json'), options: {listProfile: 'captured-list-prefix-state/v2'}},
  'relation-atomic': {source: () => examples('relation-atomic-point.json'), options: {relationProfile: 'captured-relation-row-slots/v1'}},
  'register-cycle': {source: () => examples('register-cycle.json'), options: {}},
  'register-noise': {source: noisyRegister, options: {}},
  'register-budget': {source: () => examples('register-cycle.json'), options: {maxStates: 1}},
  'predicate-point': {source: () => examples('relation-atomic-point.json'), options: {}},
  'predicate-cycle': {source: () => examples('relation-predicate-categories.json'), options: {}},
  'predicate-noise': {source: noisyRelation, options: {}},
  'predicate-budget': {source: () => examples('relation-predicate-categories.json'), options: {maxStates: 1}},
});

function caseInput(raw, api, configRoot) {
  const spec = typeof raw === 'string' ? {id: raw, fixture: raw} : raw;
  assert(spec && idValid(spec.id), 'Every case needs a safe unique id');
  const fixture = spec.fixture === undefined && CASES[spec.id] ? spec.id : spec.fixture;
  assert([fixture !== undefined, spec.sourcePath !== undefined, spec.sourceJson !== undefined].filter(Boolean).length === 1, 'Case ' + spec.id + ' must select exactly one fixture, sourcePath or sourceJson');
  let sourceText, defaults = {}, origin;
  if (fixture !== undefined) {
    assert(CASES[fixture], 'Unknown fixture ' + fixture);
    sourceText = CASES[fixture].source();
    defaults = CASES[fixture].options;
    origin = {fixture};
  } else if (spec.sourcePath !== undefined) {
    assert(typeof spec.sourcePath === 'string', 'sourcePath must be text');
    const path = resolve(configRoot, spec.sourcePath);
    sourceText = readFileSync(path, 'utf8');
    origin = {path};
  } else {
    sourceText = JSON.stringify(spec.sourceJson);
    origin = {inline: true};
  }
  const document = JSON.parse(sourceText);
  const events = Array.isArray(document.events) ? document.events : [];
  const declared = Array.isArray(document.transactions) ? document.transactions : [];
  const reads = events.filter(event => ['read', 'list_read', 'row_read'].includes(event.kind)).length
    + declared.reduce((total, tx) => total + (tx.ops || []).filter(op => op.type === 'read').length, 0);
  const writes = events.filter(event => ['write', 'append', 'row_write'].includes(event.kind)).length
    + declared.reduce((total, tx) => total + (tx.ops || []).filter(op => op.type === 'write').length, 0);
  const workload = {
    dataModel: document.dataModel || 'point-register-v1',
    transactions: events.filter(event => event.kind === 'begin').length + declared.length,
    readOperations: reads,
    writeOperations: writes,
    originalEvents: events.length,
    declaredOperations: declared.reduce((total, tx) => total + (tx.ops || []).length, 0),
  };
  assert(workload.transactions > 0 && reads + writes > 0, 'Empty benchmark histories are not accepted');
  let options;
  if (spec.options !== undefined) {
    options = spec.options;
  } else {
    assert(api !== 'reduceRelationModelsV4', 'Reduction case ' + spec.id + ' requires explicit matching options');
    const modelOptions = {models: 'elle-core', ...defaults};
    options = api === 'classifyWithInferenceV4'
      ? {modules: ['original-read-sources/v1', 'original-version-constraints/v1', 'declared-transaction-orders/v1'], modelOptions}
      : modelOptions;
  }
  assert(options && typeof options === 'object' && !Array.isArray(options), 'Case options must be an explicit JSON object');
  return {id: spec.id, sourceText, options, control: spec.control === true, origin, workload};
}

function runtimeManifest(sdk) {
  const directory = dirname(sdk), files = [];
  function visit(path) {
    for (const entry of readdirSync(path, {withFileTypes: true})) {
      const item = join(path, entry.name);
      assert(!entry.isSymbolicLink(), 'Freeze runtime links before benchmarking: ' + item);
      if (entry.isDirectory()) visit(item);
      else if (/\.(mjs|js|json|wasm)$/.test(entry.name)) {
        const bytes = readFileSync(item);
        files.push({path: relative(directory, item).replaceAll('\\', '/'), bytes: bytes.length, sha256: hash(bytes)});
      }
    }
  }
  visit(directory);
  files.sort((a, b) => a.path.localeCompare(b.path));
  return {sdk, directory, sdkSha256: hash(readFileSync(sdk)), files, manifestSha256: hash(JSON.stringify(files))};
}

async function worker(jobFile) {
  const job = JSON.parse(readFileSync(jobFile, 'utf8'));
  const source = readFileSync(job.sourceFile, 'utf8');
  const optionsText = readFileSync(job.optionsFile, 'utf8');
  const options = JSON.parse(optionsText);
  assert(hash(source) === job.sourceSha256 && hash(optionsText) === job.optionsSha256, 'Frozen worker inputs changed');
  assert(APIS.has(job.api), 'Unsupported benchmark API');
  const optionsBefore = JSON.stringify(options);
  const workerStart = performance.now();
  const moduleStart = performance.now();
  const sdk = await import(pathToFileURL(job.sdk));
  const importMs = performance.now() - moduleStart;
  const api = sdk[job.api];
  assert(typeof api === 'function', 'SDK has no ' + job.api);
  function call() {
    const report = api(source, options);
    assert(!(report && typeof report.then === 'function'), 'This protocol measures synchronous SDK calls');
    const text = typeof report === 'string' ? report : JSON.stringify(report);
    assert(typeof text === 'string', 'SDK did not return a complete serializable report');
    const value = typeof report === 'string' ? JSON.parse(report) : report;
    assert(value?.format === REPORT_FORMATS[job.api] && value.schemaVersion === 4, 'SDK returned the wrong complete report kind');
    assert(!['invalid', 'unsupported'].includes(value.status), 'SDK rejected the benchmark input');
    if (job.api === 'reduceRelationModelsV4') {
      assert(value.originalFacts && value.analysisView && value.initialClassification && value.classification && value.execution && Array.isArray(value.selectedOriginalEvents), 'Incomplete model reduction output');
    } else {
      const modelOptions = job.api === 'classifyWithInferenceV4' ? options.modelOptions || {} : options;
      const expectedModels = modelOptions.models === 'elle-core' ? 14 : Array.isArray(modelOptions.models) ? modelOptions.models.length : 6;
      assert(Array.isArray(value.models) && value.models.length === expectedModels && value.models.length > 0, 'Incomplete model-result matrix');
      if (job.api === 'classifyWithInferenceV4') {
        assert(value.inference?.observations && value.baseClassification && value.inference.execution && Object.hasOwn(value.inference, 'graph'), 'Incomplete inference output');
      } else {
        assert(value.observations && value.execution && value.options, 'Incomplete model output');
      }
    }
    return text;
  }
  const samples = [];
  let finalText, coldCallMs = null;
  if (job.mode === 'timing') {
    for (let i = 0; i < job.warmups; i++) {
      assert(hash(call()) === job.expectedSha256, 'Warmup report changed');
    }
    for (let i = 0; i < job.samples; i++) {
      const start = performance.now();
      finalText = call();
      const elapsedMs = performance.now() - start;
      assert(hash(finalText) === job.expectedSha256, 'Timed full report changed');
      samples.push(elapsedMs);
    }
  } else {
    const start = performance.now();
    finalText = call();
    coldCallMs = performance.now() - start;
    if (job.expectedSha256) assert(hash(finalText) === job.expectedSha256, 'Cold or memory report changed');
  }
  const completedMs = performance.now() - workerStart;
  assert(JSON.stringify(options) === optionsBefore, 'SDK changed caller options');
  if (job.outputFile) exclusive(job.outputFile, finalText);
  const usage = process.resourceUsage();
  // maxRSS is the process peak in KiB, including import and full serialization.
  // Memory workers are separate from warmup/timing workers and retain finalText.
  const result = {
    mode: job.mode,
    sdk: job.sdk,
    api: job.api,
    pid: process.pid,
    importMs,
    workerToFullOutputMs: completedMs,
    coldCallMs,
    samples,
    fullOutputBytes: Buffer.byteLength(finalText),
    fullOutputSha256: hash(finalText),
    resourceUsage: usage,
    currentMemory: process.memoryUsage(),
    optionsUnchanged: true,
  };
  process.stdout.write(JSON.stringify(result));
}

function argumentsOf(args) {
  const parsed = {};
  for (let i = 0; i < args.length; i++) {
    const token = args[i];
    if (['--smoke', '--describe-cases', '--help'].includes(token)) parsed[token.slice(2)] = true;
    else if (['--config', '--output'].includes(token)) {
      assert(args[i + 1] && !args[i + 1].startsWith('--'), token + ' needs a value');
      parsed[token.slice(2)] = args[++i];
    } else throw new Error('Unknown argument ' + token);
  }
  return parsed;
}

async function controller(args) {
  const flags = argumentsOf(args);
  if (flags.help) {
    console.log('Usage: node scripts/model-performance-v050.mjs --config <config.json> --output <new D-drive directory> [--smoke]\nFormal: 5 warmups, 30 samples, 3 independent batches. --describe-cases lists fixture IDs.');
    return;
  }
  if (flags['describe-cases']) {
    console.log(json({format: 'moontxnwitness-model-performance-fixtures/v1', cases: Object.keys(CASES), apis: [...APIS], protocol: FORMAL}));
    return;
  }
  assert(flags.config && flags.output, '--config and --output are required');
  const configFile = resolve(flags.config), configRoot = dirname(configFile);
  const configText = readFileSync(configFile, 'utf8'), config = JSON.parse(configText);
  assert(config.schemaVersion === 1 && Array.isArray(config.groups) && config.groups.length > 0, 'Config must contain schemaVersion:1 and explicit groups');
  assert(flags.smoke || config.exclusiveExecution === true, 'Formal runs require exclusiveExecution:true after other local work stops');
  const output = resolve(flags.output);
  if (process.platform === 'win32') assert(output.toUpperCase().startsWith('D:' + sep), 'Use a new D-drive evidence directory');
  assert(!existsSync(output), 'Evidence directory already exists; preserve previous runs');
  mkdirSync(output);
  activeOutput = output;
  mkdirSync(join(output, 'inputs'));
  mkdirSync(join(output, 'workers'));
  mkdirSync(join(output, 'reports'));
  exclusive(join(output, 'config.original.json'), configText);
  const frozenHarness = join(output, 'harness.mjs');
  exclusive(frozenHarness, readFileSync(SELF, 'utf8'));
  const protocol = flags.smoke ? SMOKE : FORMAL;
  const environment = {
    startedAt: new Date().toISOString(),
    formal: !flags.smoke,
    protocol,
    exclusiveExecutionDeclared: config.exclusiveExecution === true,
    harnessPath: SELF,
    harnessSha256: hash(readFileSync(SELF)),
    nodeExecutable: process.execPath,
    nodeExecutableSha256: hash(readFileSync(process.execPath)),
    nodeVersions: process.versions,
    system: {platform: platform(), architecture: arch(), release: release(), version: osVersion(), hostname: hostname(), logicalCpus: cpus().length, cpuModels: [...new Set(cpus().map(cpu => cpu.model))], totalMemoryBytes: totalmem(), freeMemoryBytesBefore: freemem()},
    measurementScope: 'complete synchronous SDK call plus full JSON output serialization; fresh-process startup, not a claim of cold disk caches',
    peakMemoryScope: 'independent fresh process resourceUsage.maxRSS in KiB; includes SDK import, full call and complete serialized output',
  };
  exclusive(join(output, 'environment.json'), environment);
  const groups = [], seen = new Set();
  for (const group of config.groups) {
    assert(idValid(group.id) && !seen.has(group.id), 'Group IDs must be safe and distinct');
    seen.add(group.id);
    assert(APIS.has(group.api), 'Unknown group API');
    assert(Array.isArray(group.cases) && group.cases.length > 0, 'Every group needs explicit case IDs');
    const paths = {};
    for (const side of ['baseline', 'candidate']) {
      assert(group[side] && typeof group[side].sdk === 'string', 'Both baseline and candidate SDK paths are required');
      paths[side] = {...group[side], sdk: resolve(configRoot, group[side].sdk)};
      assert(statSync(paths[side].sdk).isFile(), 'SDK path must be a file');
      paths[side].manifest = runtimeManifest(paths[side].sdk);
    }
    const cases = group.cases.map(raw => caseInput(raw, group.api, configRoot));
    assert(new Set(cases.map(item => item.id)).size === cases.length, 'Case IDs must be distinct within each group');
    assert(cases.some(item => item.control), 'Group ' + group.id + ' must include an explicitly selected common control');
    assert(cases.some(item => !item.control), 'Group ' + group.id + ' must include a target workload');
    for (const item of cases) {
      const stem = group.id + '--' + item.id;
      item.sourceFile = join(output, 'inputs', stem + '.source.json');
      item.optionsFile = join(output, 'inputs', stem + '.options.json');
      exclusive(item.sourceFile, item.sourceText);
      exclusive(item.optionsFile, JSON.stringify(item.options));
      item.sourceSha256 = hash(item.sourceText);
      item.optionsSha256 = hash(JSON.stringify(item.options));
      delete item.sourceText;
      delete item.options;
    }
    groups.push({id: group.id, api: group.api, paths, cases});
  }
  exclusive(join(output, 'frozen-inputs-and-runtimes.json'), groups);
  const timeout = config.workerTimeoutMs ?? 300000;
  assert(Number.isInteger(timeout) && timeout >= 10000 && timeout <= 3600000, 'workerTimeoutMs must be 10000..3600000');
  let jobNumber = 0;
  function run(group, item, side, mode, suffix, expectedSha256) {
    const key = String(jobNumber++).padStart(5, '0') + '--' + group.id + '--' + item.id + '--' + side + '--' + suffix;
    const jobFile = join(output, 'workers', key + '.job.json');
    const job = {mode, sdk: group.paths[side].sdk, api: group.api, sourceFile: item.sourceFile, optionsFile: item.optionsFile, sourceSha256: item.sourceSha256, optionsSha256: item.optionsSha256, expectedSha256, ...protocol};
    if (mode === 'preflight') job.outputFile = join(output, 'reports', group.id + '--' + item.id + '--' + side + '.json');
    exclusive(jobFile, job);
    const start = performance.now();
    const child = spawnSync(process.execPath, [frozenHarness, '--worker', jobFile], {encoding: 'utf8', windowsHide: true, timeout, maxBuffer: 4 * 1024 * 1024});
    const processWallMs = performance.now() - start;
    exclusive(join(output, 'workers', key + '.stderr.txt'), child.stderr || '');
    if (child.error || child.status !== 0) {
      const failure = {key, status: child.status, signal: child.signal, error: child.error?.message, stdout: child.stdout, stderr: child.stderr};
      exclusive(join(output, 'workers', key + '.failure.json'), failure);
      throw new Error('Worker failed: ' + key + ' ' + (child.error?.message || child.stderr));
    }
    const result = {...JSON.parse(child.stdout), processWallMs, batch: suffix};
    exclusive(join(output, 'workers', key + '.result.json'), result);
    return result;
  }
  // Complete byte equality is established for every workload before any timing.
  for (const group of groups) {
    for (const item of group.cases) {
      const baseline = run(group, item, 'baseline', 'preflight', 'preflight');
      const candidate = run(group, item, 'candidate', 'preflight', 'preflight');
      const left = readFileSync(join(output, 'reports', group.id + '--' + item.id + '--baseline.json'));
      const right = readFileSync(join(output, 'reports', group.id + '--' + item.id + '--candidate.json'));
      assert(left.equals(right), 'Full report bytes differ for ' + group.id + '/' + item.id + '; no timing accepted');
      item.expectedSha256 = baseline.fullOutputSha256;
      item.fullOutputBytes = baseline.fullOutputBytes;
      item.preflight = {baseline, candidate, equalBytes: true};
      item.runs = {baseline: [], candidate: []};
    }
  }
  exclusive(join(output, 'preflight.json'), {passed: true, groups});
  for (let batch = 0; batch < protocol.batches; batch++) {
    // Alternate before/after order across independent batches; both sides use
    // identical sources/options and one process per workload/mode/batch.
    const order = batch % 2 ? ['candidate', 'baseline'] : ['baseline', 'candidate'];
    for (const group of groups) {
      for (const item of group.cases) {
        for (const side of order) {
          const cold = run(group, item, side, 'cold', 'batch-' + batch + '-cold', item.expectedSha256);
          const memory = run(group, item, side, 'memory', 'batch-' + batch + '-memory', item.expectedSha256);
          const timing = run(group, item, side, 'timing', 'batch-' + batch + '-timing', item.expectedSha256);
          item.runs[side].push({batch, cold, memory, timing});
        }
      }
    }
    console.log(JSON.stringify({progress: 'batch-complete', batch: batch + 1, batches: protocol.batches, formal: !flags.smoke}));
  }
  for (const group of groups) {
    for (const side of ['baseline', 'candidate']) {
      assert(runtimeManifest(group.paths[side].sdk).manifestSha256 === group.paths[side].manifest.manifestSha256, 'Frozen runtime changed during measurement: ' + group.id + '/' + side);
    }
  }
  const outputGroups = groups.map(group => {
    const cases = group.cases.map(item => {
      const sides = {};
      for (const side of ['baseline', 'candidate']) {
        const runs = item.runs[side];
        const rss = runs.map(run => run.memory.resourceUsage.maxRSS);
        assert(rss.every(value => Number.isFinite(value) && value > 0), 'Peak RSS is unavailable; cannot claim a memory comparison');
        sides[side] = {
          fullCallMs: stats(runs.flatMap(run => run.timing.samples)),
          coldProcessWallMs: stats(runs.map(run => run.cold.processWallMs)),
          coldImportMs: stats(runs.map(run => run.cold.importMs)),
          coldFullCallMs: stats(runs.map(run => run.cold.coldCallMs)),
          peakRssKiB: stats(rss),
          fullOutputBytes: item.fullOutputBytes,
        };
      }
      const allowedRegressionMs = Math.max(sides.baseline.fullCallMs.p95 * 0.10, 2);
      return {
        id: item.id,
        control: item.control,
        workload: item.workload,
        sourceSha256: item.sourceSha256,
        optionsSha256: item.optionsSha256,
        fullOutputSha256: item.expectedSha256,
        sides,
        medianSpeedup: sides.baseline.fullCallMs.median / sides.candidate.fullCallMs.median,
        peakRssRatio: sides.candidate.peakRssKiB.median / sides.baseline.peakRssKiB.median,
        p95RegressionMs: sides.candidate.fullCallMs.p95 - sides.baseline.fullCallMs.p95,
        allowedRegressionMs,
        controlGatePassed: !item.control || sides.candidate.fullCallMs.p95 <= sides.baseline.fullCallMs.p95 + allowedRegressionMs,
      };
    });
    const targetCases = cases.filter(item => !item.control);
    const medianSpeedupGeomean = geometricMean(targetCases.map(item => item.medianSpeedup));
    const peakRssRatioGeomean = geometricMean(targetCases.map(item => item.peakRssRatio));
    const speedupTarget = group.api === 'reduceRelationModelsV4' ? 1.25 : 1.3;
    return {
      id: group.id,
      api: group.api,
      targetCaseIds: targetCases.map(item => item.id),
      controlCaseIds: cases.filter(item => item.control).map(item => item.id),
      medianSpeedupGeomean,
      peakRssRatioGeomean,
      speedupTarget,
      peakRssRatioTarget: 0.8,
      speedupGoalMet: medianSpeedupGeomean >= speedupTarget,
      memoryGoalMet: peakRssRatioGeomean <= 0.8,
      controlGatePassed: cases.every(item => item.controlGatePassed),
      cases,
    };
  });
  const summary = {
    format: 'moontxnwitness-full-model-performance/v1',
    status: 'completed',
    formal: !flags.smoke,
    protocol,
    completedAt: new Date().toISOString(),
    byteCorrectnessPassed: true,
    runtimeFilesUnchanged: true,
    controlGatePassed: outputGroups.every(group => group.controlGatePassed),
    speedupGoalsMet: outputGroups.every(group => group.speedupGoalMet),
    memoryGoalsMet: outputGroups.every(group => group.memoryGoalMet),
    aggregateTargetMedianSpeedup: geometricMean(outputGroups.flatMap(group => group.cases.filter(item => !item.control).map(item => item.medianSpeedup))),
    aggregateTargetPeakRssRatio: geometricMean(outputGroups.flatMap(group => group.cases.filter(item => !item.control).map(item => item.peakRssRatio))),
    fullOutputScope: 'all report fields, edges, sources, proofs and counters retained; summaries and capsules are not timed',
    rawSamplesDirectory: 'workers',
    statisticDefinitions: {median: 'middle value or mean of middle pair', p95: 'nearest-rank ceiling(0.95*n)', groupAggregation: 'geometric mean of target case ratios; control workloads reported separately', peakRssRatio: 'ratio of medians of independent-process peakRSS values'},
    groups: outputGroups,
  };
  exclusive(join(output, 'summary.json'), summary);
  const receipts = [];
  function archiveManifest(path) {
    for (const entry of readdirSync(path, {withFileTypes: true})) {
      const file = join(path, entry.name);
      if (entry.isDirectory()) archiveManifest(file);
      else receipts.push({path: relative(output, file).replaceAll('\\', '/'), bytes: statSync(file).size, sha256: hash(readFileSync(file))});
    }
  }
  archiveManifest(output);
  exclusive(join(output, 'manifest.sha256.json'), receipts.sort((a, b) => a.path.localeCompare(b.path)));
  console.log(JSON.stringify({formal: summary.formal, byteCorrectnessPassed: summary.byteCorrectnessPassed, controlGatePassed: summary.controlGatePassed, speedupGoalsMet: summary.speedupGoalsMet, memoryGoalsMet: summary.memoryGoalsMet, summary: join(output, 'summary.json')}));
  if (!summary.controlGatePassed) process.exitCode = 1;
}

try {
  if (process.argv[2] === '--worker') await worker(process.argv[3]);
  else await controller(process.argv.slice(2));
} catch (error) {
  if (activeOutput && !existsSync(join(activeOutput, 'failure.json'))) {
    exclusive(join(activeOutput, 'failure.json'), {status: 'failed', failedAt: new Date().toISOString(), error: error.stack || error.message});
  }
  console.error(error.stack || error.message);
  process.exitCode = 1;
}
