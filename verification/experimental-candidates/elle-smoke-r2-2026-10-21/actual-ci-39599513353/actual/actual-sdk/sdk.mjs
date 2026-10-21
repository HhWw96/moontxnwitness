import { analyze_json, analyze_options_json, verify_certificate_json, shrink_json, shrink_options_json, replay_report_json, compare_models_json, version, analyze_v3_json, reduce_v3_json, verify_v3_json } from './core.mjs';
import { normalize_capture_json, normalize_presence_json, normalize_capture_v3_json, normalize_capture_v3_options_json, dislock_sql_v3_proof_json, inspect_execution_failures_v3_json } from './capture-core.mjs';

export { version };
export { makeCapsuleV3, replayCapsuleV3 } from './evidence.mjs';
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
