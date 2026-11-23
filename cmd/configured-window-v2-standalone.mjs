// Optional standalone entry: import it instead of the complete SDK.
import * as core from './sql-projection-v2-core.mjs';
import {createConfiguredWindowV4} from './configured-window-v2-host.mjs';
export const {analyzeConfiguredWindowV4, verifyConfiguredWindowV4,
  analyzeConfiguredWindowTextV4, verifyConfiguredWindowTextV4,
  reduceConfiguredWindowV4, verifyConfiguredWindowReductionV4,
  reduceConfiguredWindowTextV4, verifyConfiguredWindowReductionTextV4,
  explainConfiguredWindowV4, explainConfiguredWindowTextV4} = createConfiguredWindowV4(core);
export {CONFIGURED_WINDOW_V4_LIMITS, CONFIGURED_WINDOW_REDUCTION_V4_LIMITS} from './configured-window-v2-host.mjs';

export function admitConfiguredPredicateWindowV1(bundleText, {config, policy, maxChecks = 1_000_000}) {
  if (typeof bundleText !== 'string' || config == null || policy == null) {
    throw new TypeError('Original bundle text and independent configuration and policy are required');
  }
  const text = value => typeof value === 'string' ? value : JSON.stringify(value);
  return JSON.parse(core.admit_configured_predicate_window_v1_json(text(config), text(policy),
    bundleText, JSON.stringify({maxChecks})));
}
