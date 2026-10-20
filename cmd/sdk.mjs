import { analyze_json, analyze_options_json, verify_certificate_json, shrink_json, shrink_options_json, replay_report_json, compare_models_json, version } from './core.mjs';
import { normalize_capture_json, normalize_presence_json } from './capture-core.mjs';

export { version };
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
