import { analyze_json, analyze_options_json, verify_certificate_json, shrink_json, replay_report_json, compare_models_json, version } from './core.mjs';

export { version };
export function analyzeWithOptions(history, options = {}) {
  return JSON.parse(analyze_options_json(typeof history === 'string' ? history : JSON.stringify(history), JSON.stringify(options)));
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
