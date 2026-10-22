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
  const trace = JSON.parse(JSON.parse(text).traceText);
  if (trace === null || typeof trace !== 'object' || Array.isArray(trace) || trace.traceSchema !== 3 || trace.dataModel !== 'append-list-v1') {
    return {valid: false, reason: 'Expected traceSchema 3 and dataModel append-list-v1'};
  }
  return result;
}
