import * as core from './sql-projection-v2-core.mjs';

export function admitConfiguredPredicateWindowV1(bundleText, {config, policy, maxChecks = 1_000_000}) {
  if (typeof bundleText !== 'string' || config == null || policy == null) {
    throw new TypeError('Original bundle text and independent configuration and policy are required');
  }
  const text = value => typeof value === 'string' ? value : JSON.stringify(value);
  return JSON.parse(core.admit_configured_predicate_window_v1_json(text(config), text(policy),
    bundleText, JSON.stringify({maxChecks})));
}
