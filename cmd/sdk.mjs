import { analyze_json, analyze_options_json, verify_certificate_json, shrink_json, shrink_options_json, replay_report_json, compare_models_json, version, analyze_v3_json, reduce_v3_json, verify_v3_json } from './core.mjs';
import { normalize_capture_json, normalize_presence_json, normalize_capture_v3_json, normalize_capture_v3_options_json, dislock_sql_v3_proof_json, inspect_execution_failures_v3_json, orm_sql_source2_v3_proof_json } from './capture-core.mjs';

export { version };
import { makeCapsuleV3, replayCapsuleV3 } from './evidence.mjs';
export { makeCapsuleV3, replayCapsuleV3 };
const inputText = value => typeof value === 'string' ? value : JSON.stringify(value);
function v3Text(value, maximum) {
  const text = inputText(value);
  if (Buffer.byteLength(text, 'utf8') > maximum) throw new RangeError(`v3 input exceeds ${maximum} UTF-8 bytes`);
  return text;
}
export function normalizeCaptureV3(trace, options = {}) {
  return JSON.parse(normalize_capture_v3_options_json(v3Text(trace, 8 * 1024 * 1024), v3Text(options, 4096)));
}
// Diagnostic only: matching fixed SQL does not enable complete analysis.
export function inspectDislockCaptureV3(trace) {
  return JSON.parse(dislock_sql_v3_proof_json(v3Text(trace, 8 * 1024 * 1024)));
}
export function inspectExecutionFailuresV3(trace) {
  return JSON.parse(inspect_execution_failures_v3_json(v3Text(trace, 8 * 1024 * 1024)));
}
// Experimental local source proofs; never grants complete capture/model coverage.
// Keep the caller's exact schema/profile and original trace/JSONL text.
export function inspectOrmSourceV3(envelope) {
  return JSON.parse(orm_sql_source2_v3_proof_json(v3Text(envelope, 64 * 1024 * 1024)));
}
export function analyzeV3(trace, options = {}) {
  return JSON.parse(analyze_v3_json(v3Text(trace, 8 * 1024 * 1024), v3Text(options, 4096)));
}
export function reduceV3(trace, options = {}) {
  return JSON.parse(reduce_v3_json(v3Text(trace, 8 * 1024 * 1024), v3Text(options, 4096)));
}
export function verifyV3(trace, report) {
  return JSON.parse(verify_v3_json(v3Text(trace, 8 * 1024 * 1024), v3Text(report, 32 * 1024 * 1024)));
}
export function normalizeCapture(trace) {
  return JSON.parse(normalize_capture_json(typeof trace === 'string' ? trace : JSON.stringify(trace)));
}
// Experimental frozen-key presence/source projection, separate from trace-v1.
export function normalizePresenceCapture(trace) {
  return JSON.parse(normalize_presence_json(typeof trace === 'string' ? trace : JSON.stringify(trace)));
}
export function analyzeWithOptions(history, options = {}) {
  return JSON.parse(analyze_options_json(typeof history === 'string' ? history : JSON.stringify(history), JSON.stringify(options)));
}
export function shrinkWithOptions(history, options = {}) {
  return JSON.parse(shrink_options_json(typeof history === 'string' ? history : JSON.stringify(history), JSON.stringify(options)));
}
export function compareModels(history) {
  return JSON.parse(compare_models_json(typeof history === 'string' ? history : JSON.stringify(history)));
}
export function replayReport(history, report) {
  return JSON.parse(replay_report_json(typeof history === 'string' ? history : JSON.stringify(history), typeof report === 'string' ? report : JSON.stringify(report)));
}
export function shrink(history) {
  return JSON.parse(shrink_json(typeof history === 'string' ? history : JSON.stringify(history)));
}
export function analyze(history) {
  return JSON.parse(analyze_json(typeof history === 'string' ? history : JSON.stringify(history)));
}
export function verify(history, certificate) {
  return JSON.parse(verify_certificate_json(
    typeof history === 'string' ? history : JSON.stringify(history),
    typeof certificate === 'string' ? certificate : JSON.stringify(certificate),
  ));
}

/**
 * @typedef {Object} AppendListCaptureV3
 * @property {3} traceSchema
 * @property {'append-list-v1'} dataModel
 * @property {string} clockDomain
 * @property {{exclusiveWriters: boolean}} scope
 * @property {ReadonlyArray<Object>} events
 * @property {ReadonlyArray<Object>} gaps
 *
 * @typedef {{maxStates?: number, maxOperationChecks?: number}} ListAnalysisOptionsV3
 * @typedef {{maxChecks?: number, analysisOptions?: ListAnalysisOptionsV3}} ListReductionOptionsV3
 */

// Check the caller's model once, then pass the exact text to the bounded core.
// JSON.parse here does not replace MoonBit's duplicate-key/shape validation.
function listCaptureTextV3(trace) {
  if (typeof trace !== 'string' && (trace === null || typeof trace !== 'object')) {
    throw new TypeError('List v3 capture must be JSON text or a capture object');
  }
  const text = v3Text(trace, 8 * 1024 * 1024);
  const capture = JSON.parse(text);
  if (capture === null || Array.isArray(capture) || capture.traceSchema !== 3 || capture.dataModel !== 'append-list-v1') {
    throw new TypeError('Expected traceSchema 3 and dataModel append-list-v1');
  }
  return text;
}

/** @param {string | AppendListCaptureV3} trace */
export function normalizeListCaptureV3(trace) {
  return normalizeCaptureV3(listCaptureTextV3(trace));
}

/** @param {string | AppendListCaptureV3} trace @param {ListAnalysisOptionsV3} options */
export function analyzeListV3(trace, options = {}) {
  return analyzeV3(listCaptureTextV3(trace), options);
}

/** @param {string | AppendListCaptureV3} trace @param {ListReductionOptionsV3} options */
export function reduceListV3(trace, options = {}) {
  return reduceV3(listCaptureTextV3(trace), options);
}

/** @param {string | AppendListCaptureV3} trace */
export function verifyListV3(trace, report) {
  return verifyV3(listCaptureTextV3(trace), report);
}

/** @param {string | AppendListCaptureV3} trace */
export function makeListCapsuleV3(trace, report) {
  return makeCapsuleV3(listCaptureTextV3(trace), report);
}

/** Verify the complete generic capsule before accepting its fixed list model. */
export function replayListCapsuleV3(text) {
  if (typeof text !== 'string') throw new TypeError('List v3 capsule must be JSON text');
  const result = replayCapsuleV3(text);
  if (!result.valid) return result;
  let trace;
  try {
    trace = JSON.parse(JSON.parse(text).traceText);
  } catch {
    // A generic v3 capsule can faithfully reproduce an invalid-JSON diagnostic.
    // Such a trace cannot declare this fixed model, even when replay is valid.
    return {valid: false, reason: 'Expected traceSchema 3 and dataModel append-list-v1'};
  }
  if (trace === null || typeof trace !== 'object' || Array.isArray(trace) || trace.traceSchema !== 3 || trace.dataModel !== 'append-list-v1') {
    return {valid: false, reason: 'Expected traceSchema 3 and dataModel append-list-v1'};
  }
  return result;
}

/**
 * @typedef {Object} RelationCaptureV3
 * @property {3} traceSchema
 * @property {'relation-set-v1'} dataModel
 * @property {string} clockDomain
 * @property {{exclusiveWriters: boolean, completeSnapshotTables: ReadonlyArray<string>}} scope
 * @property {Object} relationSchema
 * @property {ReadonlyArray<Object>} events
 * @property {ReadonlyArray<Object>} gaps
 *
 * @typedef {{maxStates?: number, maxOperationChecks?: number}} RelationAnalysisOptionsV3
 * @typedef {{maxChecks?: number, analysisOptions?: RelationAnalysisOptionsV3}} RelationReductionOptionsV3
 */

// Check the caller's model once, then pass the exact text to the bounded core.
// JSON.parse here does not replace MoonBit's duplicate-key/shape validation.
function relationCaptureTextV3(trace) {
  if (typeof trace !== 'string' && (trace === null || typeof trace !== 'object')) {
    throw new TypeError('Relation v3 capture must be JSON text or a capture object');
  }
  const text = v3Text(trace, 8 * 1024 * 1024);
  const capture = JSON.parse(text);
  if (capture === null || Array.isArray(capture) || capture.traceSchema !== 3 || capture.dataModel !== 'relation-set-v1') {
    throw new TypeError('Expected traceSchema 3 and dataModel relation-set-v1');
  }
  return text;
}

/** @param {string | RelationCaptureV3} trace */
export function normalizeRelationCaptureV3(trace) {
  return normalizeCaptureV3(relationCaptureTextV3(trace));
}

/** @param {string | RelationCaptureV3} trace @param {RelationAnalysisOptionsV3} options */
export function analyzeRelationV3(trace, options = {}) {
  return analyzeV3(relationCaptureTextV3(trace), options);
}

/** @param {string | RelationCaptureV3} trace @param {RelationReductionOptionsV3} options */
export function reduceRelationV3(trace, options = {}) {
  return reduceV3(relationCaptureTextV3(trace), options);
}

/** @param {string | RelationCaptureV3} trace */
export function verifyRelationV3(trace, report) {
  return verifyV3(relationCaptureTextV3(trace), report);
}

/** @param {string | RelationCaptureV3} trace */
export function makeRelationCapsuleV3(trace, report) {
  return makeCapsuleV3(relationCaptureTextV3(trace), report);
}

/** Verify the complete generic capsule before accepting its fixed relation model. */
export function replayRelationCapsuleV3(text) {
  if (typeof text !== 'string') throw new TypeError('Relation v3 capsule must be JSON text');
  const result = replayCapsuleV3(text);
  if (!result.valid) return result;
  let trace;
  try {
    trace = JSON.parse(JSON.parse(text).traceText);
  } catch {
    // A generic v3 capsule can faithfully reproduce an invalid-JSON diagnostic.
    // Such a trace cannot declare this fixed model, even when replay is valid.
    return {valid: false, reason: 'Expected traceSchema 3 and dataModel relation-set-v1'};
  }
  if (trace === null || typeof trace !== 'object' || Array.isArray(trace) || trace.traceSchema !== 3 || trace.dataModel !== 'relation-set-v1') {
    return {valid: false, reason: 'Expected traceSchema 3 and dataModel relation-set-v1'};
  }
  return result;
}

import {createHash as cycleHashV3} from 'node:crypto';
import {isDeepStrictEqual as cycleEqualV3} from 'node:util';

const cycleDigestV3 = text => cycleHashV3('sha256').update(text, 'utf8').digest('hex');
const cycleScopeV3 = () => ({
  witnessOnly: true,
  searchesOtherCategoryCycles: false,
  acceptsIsolationModels: false,
  completeIsolationClassification: false,
  classifiesExecutionFailures: false,
  authenticatesCaptureSources: false,
});

// Derived explanations of an existing MoonBit witness. No new graph or model
// search is performed here; the original core must reproduce the whole report.
export function explainRegisterCycleV3(trace, report) {
  const traceText = v3Text(trace, 8 * 1024 * 1024);
  const reportText = v3Text(report, 32 * 1024 * 1024);
  const checked = verifyV3(traceText, reportText);
  const base = {
    schemaVersion: 1,
    kind: 'moontxnwitness-register-cycle-explanation/v1',
    algorithm: 'verified-register-cycle-v1',
    traceTextSha256: cycleDigestV3(traceText),
    reportTextSha256: cycleDigestV3(reportText),
    verifiedReport: checked.valid === true,
    sourceReportVersion: null,
    sourceStatus: null,
    sourceCoverageComplete: false,
    status: 'invalid',
    reason: 'report-does-not-reproduce',
    subtype: null,
    categoriesSearched: false,
    scope: cycleScopeV3(),
    witness: null,
    steps: [],
    rules: {repository: 'jepsen-io/elle', commit: '4e359e597c52938b0afebb8bc42273914d68a424',
      file: 'src/elle/txn.clj', definition: 'cycle-explainer; ww/wr/item-rw subset only'},
  };
  if (!checked.valid) return base;
  const supplied = JSON.parse(reportText);
  base.sourceReportVersion = supplied.version;
  base.sourceStatus = supplied.status;
  base.sourceCoverageComplete = supplied.coverage?.complete === true;
  if (supplied.status === 'invalid') return {...base, reason: 'invalid-source-analysis'};
  if (!base.sourceCoverageComplete || supplied.status === 'inconclusive') {
    return {...base, status: 'inconclusive', reason: 'source-analysis-incomplete'};
  }
  if (supplied.modelDefinition?.id !== 'register-serializable-v1' || supplied.algorithm !== 'v3-register-1') {
    return {...base, status: 'not-applicable', reason: 'explicit-register-observations-required'};
  }
  const evidence = supplied.evidence, witness = evidence?.witness;
  if (supplied.status !== 'violation' || witness?.kind !== 'dependency_cycle' || !Array.isArray(witness.edges) || !witness.edges.length) {
    return {...base, status: 'not-applicable', reason: 'no-cycle-witness'};
  }
  if (evidence.complete !== true || evidence.graph?.analyzed !== true || evidence.graph.edgeBudgetExceeded !== false) {
    return {...base, status: 'inconclusive', reason: 'dependency-graph-incomplete'};
  }
  const history = supplied.normalized?.history, observations = supplied.normalized?.observations;
  if (!Array.isArray(history?.transactions) || !Array.isArray(observations) || witness.edges.length > 512) {
    return {...base, status: 'not-applicable', reason: 'unsupported-projected-witness'};
  }
  const transactions = new Map(history.transactions.map(transaction => [transaction.id, transaction]));
  const original = new Map();
  // Structured maps preserve identifiers containing separators and controls.
  for (const event of observations) {
    if (event.kind !== 'read' && event.kind !== 'write') continue;
    if (!original.has(event.tx)) original.set(event.tx, new Map());
    const tx = original.get(event.tx);
    if (!tx.has(event.key)) tx.set(event.key, new Map());
    const key = tx.get(event.key);
    if (!key.has(event.kind)) key.set(event.kind, new Map());
    const kind = key.get(event.kind);
    if (!kind.has(event.version)) kind.set(event.version, []);
    kind.get(event.version).push(event.seq);
  }
  const matching = (tx, operation) => original.get(tx)?.get(operation.key)?.get(operation.type)?.get(operation.version) || [];
  const steps = [];
  for (let index = 0; index < witness.edges.length; index++) {
    const edge = witness.edges[index], next = witness.edges[(index + 1) % witness.edges.length];
    const from = transactions.get(edge.from), to = transactions.get(edge.to);
    if (!['ww', 'wr', 'rw'].includes(edge.kind) || edge.from === edge.to || edge.to !== next.from ||
        from?.status !== 'committed' || to?.status !== 'committed' ||
        !Number.isInteger(edge.fromOp) || !Number.isInteger(edge.toOp) ||
        !evidence.edges.some(candidate => cycleEqualV3(candidate, edge))) {
      return {...base, status: 'not-applicable', reason: 'unsupported-typed-cycle'};
    }
    const fromOp = from.ops[edge.fromOp], toOp = to.ops[edge.toOp];
    const expectedKinds = {ww: ['write', 'write'], wr: ['write', 'read'], rw: ['read', 'write']}[edge.kind];
    if (!fromOp || !toOp || fromOp.type !== expectedKinds[0] || toOp.type !== expectedKinds[1] ||
        fromOp.key !== edge.key || toOp.key !== edge.key || fromOp.version !== edge.fromVersion || toOp.version !== edge.toVersion) {
      return {...base, status: 'not-applicable', reason: 'projected-operation-source-mismatch'};
    }
    const fromSeqs = matching(edge.from, fromOp), toSeqs = matching(edge.to, toOp);
    if (!fromSeqs.length || !toSeqs.length) return {...base, status: 'not-applicable', reason: 'original-point-source-unavailable'};
    const chain = evidence.versionOrders?.[edge.key], orderSource = evidence.versionOrderSources?.[edge.key];
    if (edge.kind !== 'wr' && (!['asserted', 'single-writer'].includes(orderSource) || !Array.isArray(chain) ||
        chain.indexOf(edge.fromVersion) < 0 || chain.indexOf(edge.fromVersion) >= chain.indexOf(edge.toVersion))) {
      return {...base, status: 'inconclusive', reason: 'nonfactual-version-order'};
    }
    steps.push({edgeIndex: index, dependency: edge,
      from: {transaction: edge.from, projectedOperation: edge.fromOp, operation: fromOp, matchingOriginalSeqs: fromSeqs},
      to: {transaction: edge.to, projectedOperation: edge.toOp, operation: toOp, matchingOriginalSeqs: toSeqs},
      sourceReferenceKind: 'all matching original point observations; no unique occurrence inferred',
      versionOrderSource: orderSource ?? null, versionOrder: chain ?? null});
  }
  // Rules independently implemented from the fixed upstream mathematical
  // definition. The last and first edge are adjacent as well.
  const rw = witness.edges.filter(edge => edge.kind === 'rw').length;
  const adjacent = witness.edges.some((edge, index) => edge.kind === 'rw' && witness.edges[(index + 1) % witness.edges.length].kind === 'rw');
  const subtype = rw === 1 ? 'G-single-item' : rw > 1 ? (adjacent ? 'G2-item' : 'G-nonadjacent-item') :
    witness.edges.some(edge => edge.kind === 'wr') ? 'G1c' : 'G0';
  const result = {...base, status: 'explained', reason: 'verified-point-cycle', subtype,
    witness, steps, pattern: {itemAntiDependencies: rw, adjacentAntiDependenciesIncludingWraparound: adjacent},
    categoryCoverage: 'Only this existing witness; another anomaly may exist elsewhere in the history.'};
  if (Buffer.byteLength(JSON.stringify(result), 'utf8') > 8 * 1024 * 1024) {
    return {...base, status: 'inconclusive', reason: 'explanation-output-byte-budget'};
  }
  return result;
}

export function verifyRegisterCycleExplanationV3(trace, report, explanation) {
  if (explanation === null || typeof explanation !== 'object' || Array.isArray(explanation)) {
    throw new TypeError('Cycle explanation must be an object; parse saved JSON explicitly');
  }
  const encoded = v3Text(explanation, 8 * 1024 * 1024);
  const expected = explainRegisterCycleV3(trace, report);
  return {valid: expected.verifiedReport && cycleEqualV3(JSON.parse(encoded), expected),
    status: expected.status, subtype: expected.subtype,
    scope: 'Recomputed derived explanation and verified source report; no source authentication or complete model classification.'};
}

import {createHash as executionHashV3} from 'node:crypto';

const executionDigestV3 = text => executionHashV3('sha256').update(text, 'utf8').digest('hex');
const executionCanonicalV3 = value => JSON.stringify(value, null, 2) + '\n';
const executionBudgetsV3 = () => ({
  traceUtf8Bytes: 8 * 1024 * 1024,
  diagnosticUtf8Bytes: 32 * 1024 * 1024,
  capsuleUtf8Bytes: 32 * 1024 * 1024,
  normalizedJsonCodeUnits: 32 * 1024 * 1024,
  normalizationPolicy: 'normalize_capture_v3_json/defaults',
  modelSearch: false,
});
// A future release may add only individually reviewed released engine/algorithm
// pairs here. No wildcard version migration or rewriting of diagnostic fields.
const executionEngineSupportedV3 = recorded => recorded === version() ||
  ['0.1.7', '0.1.8', '0.2.0'].includes(recorded);
const executionScopeV3 = () => ({
  diagnosticRecomputationOnly: true,
  actualDatabaseExecution: false,
  databaseAuthenticityVerified: false,
  certifiesFailureAbsence: false,
  modelViolationClaim: false,
  completeApplicationIntegration: false,
});
function executionFieldsV3(engineVersion, traceText, diagnosticText) {
  return {
    format: 'moontxnwitness-execution/v1', schemaVersion: 1, tool: 'MoonTxnWitness',
    engineVersion, diagnosticAlgorithm: 'v3-observed-failures-1',
    budgets: executionBudgetsV3(),
    traceText, traceSha256: executionDigestV3(traceText),
    diagnosticText, diagnosticSha256: executionDigestV3(diagnosticText),
  };
}

/**
 * Seal exact trace text and its independently recorded execution diagnostic.
 * Incomplete coverage and unknown COMMIT are retained, never promoted to proof.
 * This does not connect to a database or change the original v3 model capsule.
 */
export function makeExecutionCapsuleV3(trace) {
  const traceText = v3Text(trace, 8 * 1024 * 1024);
  if (Buffer.from(traceText, 'utf8').toString('utf8') !== traceText) {
    throw new TypeError('Execution capture must be well-formed Unicode UTF-8 text');
  }
  const diagnostic = inspectExecutionFailuresV3(traceText);
  if (diagnostic.valid !== true || diagnostic.algorithm !== 'v3-observed-failures-1') {
    throw new Error('Cannot package an invalid or unsupported execution diagnostic');
  }
  const diagnosticText = JSON.stringify(diagnostic);
  if (Buffer.byteLength(diagnosticText, 'utf8') > 32 * 1024 * 1024) {
    throw new RangeError('Execution diagnostic exceeds 32 MiB UTF-8');
  }
  const capsuleText = executionCanonicalV3(executionFieldsV3(version(), traceText, diagnosticText));
  if (Buffer.byteLength(capsuleText, 'utf8') > 32 * 1024 * 1024) {
    throw new RangeError('Execution capsule exceeds 32 MiB UTF-8');
  }
  return capsuleText;
}

/**
 * Recompute the diagnostic, preserving every original outcome and coverage gap.
 * v1 accepts the exact canonical envelope emitted above, including its newline;
 * duplicate keys, extra fields and alternative envelope encodings are rejected.
 * The contained trace is kept verbatim, including valid original whitespace.
 */
export function replayExecutionCapsuleV3(text) {
  if (typeof text !== 'string') throw new TypeError('Execution capsule must be JSON text');
  const reject = reason => ({valid: false, reason, scope: executionScopeV3()});
  if (Buffer.byteLength(text, 'utf8') > 32 * 1024 * 1024) return reject('execution-capsule-byte-budget');
  let capsule;
  try {capsule = JSON.parse(text);} catch {return reject('invalid-execution-capsule-json');}
  if (capsule === null || typeof capsule !== 'object' || Array.isArray(capsule) ||
      capsule.format !== 'moontxnwitness-execution/v1' || capsule.schemaVersion !== 1 ||
      capsule.tool !== 'MoonTxnWitness' || !executionEngineSupportedV3(capsule.engineVersion) ||
      capsule.diagnosticAlgorithm !== 'v3-observed-failures-1' ||
      typeof capsule.traceText !== 'string' || typeof capsule.diagnosticText !== 'string') {
    return reject('unsupported-execution-capsule-header');
  }
  if (Buffer.byteLength(capsule.traceText, 'utf8') > 8 * 1024 * 1024 ||
      Buffer.byteLength(capsule.diagnosticText, 'utf8') > 32 * 1024 * 1024) {
    return reject('execution-content-byte-budget');
  }
  if (Buffer.from(capsule.traceText, 'utf8').toString('utf8') !== capsule.traceText) {
    return reject('execution-trace-not-well-formed-unicode');
  }
  const expected = executionFieldsV3(capsule.engineVersion, capsule.traceText, capsule.diagnosticText);
  if (text !== executionCanonicalV3(expected)) return reject('execution-envelope-or-digest-mismatch');
  const recomputed = inspectExecutionFailuresV3(capsule.traceText);
  if (recomputed.valid !== true || recomputed.algorithm !== capsule.diagnosticAlgorithm ||
      JSON.stringify(recomputed) !== capsule.diagnosticText) {
    return reject('execution-diagnostic-does-not-reproduce');
  }
  return {valid: true, status: 'recomputed-observations', engineVersion: capsule.engineVersion,
    traceSha256: expected.traceSha256, diagnosticSha256: expected.diagnosticSha256,
    diagnostic: recomputed, scope: executionScopeV3()};
}
