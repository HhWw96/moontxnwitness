// Text boundaries only. SQL, provenance and model decisions belong to MoonBit.
export const CONFIGURED_WINDOW_V4_LIMITS = Object.freeze({
  bundleBytes: 32 * 1024 * 1024,
  reportBytes: 32 * 1024 * 1024,
  configBytes: 262144,
  policyBytes: 8192,
  optionsBytes: 262144,
  maxSourceChecks: 1000000,
  maxPointChecks: 1000000,
  maxRows: 16384,
  maxEffects: 16384,
  maxStates: 100000,
  maxEdgeChecks: 1000000,
  maxModelSourceChecks: 1000000,
  maxSerialOperationChecks: 1000000,
});

const budgetNames = Object.freeze([
  'maxSourceChecks', 'maxPointChecks', 'maxRows', 'maxEffects', 'maxStates',
  'maxEdgeChecks', 'maxModelSourceChecks', 'maxSerialOperationChecks',
]);

function originalText(value, maximum, label) {
  if (typeof value !== 'string' || !value.isWellFormed()
      || Buffer.byteLength(value, 'utf8') > maximum) {
    throw new TypeError(label + ' must be original well-formed UTF-8 text within ' + maximum + ' bytes');
  }
  return value;
}

function object(value, label) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)
      || ![Object.prototype, null].includes(Object.getPrototypeOf(value))) {
    throw new TypeError(label + ' must be a plain object');
  }
  return value;
}

function jsonText(value, maximum, label) {
  if (typeof value === 'string') return originalText(value, maximum, label);
  object(value, label);
  const text = JSON.stringify(value, (_key, item) => {
    if (typeof item === 'number' && !Number.isSafeInteger(item)) {
      throw new TypeError(label + ' contains an inexact JSON number; supply original JSON text');
    }
    if (item === undefined || typeof item === 'function' || typeof item === 'symbol') {
      throw new TypeError(label + ' contains a non-JSON value');
    }
    return item;
  });
  return originalText(text, maximum, label);
}

function independentOptions(options) {
  object(options, 'Independent configured window options');
  for (const name of ['config', 'policy']) {
    if (!Object.hasOwn(options, name)) throw new TypeError('Independent ' + name + ' is required');
  }
  const limits = {};
  for (const name of Object.keys(options)) {
    if (name === 'config' || name === 'policy') continue;
    if (name === 'projectionOptions') {
      object(options[name], 'Independent projectionOptions');
      limits[name] = options[name];
    } else if (budgetNames.includes(name)) {
      const value = options[name];
      if (!Number.isSafeInteger(value) || value < 0 || value > CONFIGURED_WINDOW_V4_LIMITS[name]) {
        throw new RangeError(name + ' must be an integer in 0..' + CONFIGURED_WINDOW_V4_LIMITS[name]);
      }
      limits[name] = value;
    } else {
      throw new TypeError('Unknown independent configured window option: ' + name);
    }
  }
  return [
    jsonText(options.config, CONFIGURED_WINDOW_V4_LIMITS.configBytes, 'Independent SQL configuration'),
    jsonText(options.policy, CONFIGURED_WINDOW_V4_LIMITS.policyBytes, 'Independent source policy'),
    jsonText(limits, CONFIGURED_WINDOW_V4_LIMITS.optionsBytes, 'Independent configured window limits'),
  ];
}

export function createConfiguredWindowV4(core) {
  // CLI text entries retain duplicate keys, whitespace and exact numeric tokens
  // for the strict MoonBit parser. The bundle is never parsed in this host.
  function analyzeConfiguredWindowTextV4(bundleText, configText, policyText, optionsText = '{}') {
    return JSON.parse(core.analyze_configured_window_v2_json(
      originalText(configText, CONFIGURED_WINDOW_V4_LIMITS.configBytes, 'Independent SQL configuration'),
      originalText(policyText, CONFIGURED_WINDOW_V4_LIMITS.policyBytes, 'Independent source policy'),
      originalText(bundleText, CONFIGURED_WINDOW_V4_LIMITS.bundleBytes, 'Original configured window bundle'),
      originalText(optionsText, CONFIGURED_WINDOW_V4_LIMITS.optionsBytes, 'Independent configured window limits')));
  }

  function verifyConfiguredWindowTextV4(bundleText, report, configText, policyText, optionsText = '{}') {
    return JSON.parse(core.verify_configured_window_v2_json(
      originalText(configText, CONFIGURED_WINDOW_V4_LIMITS.configBytes, 'Independent SQL configuration'),
      originalText(policyText, CONFIGURED_WINDOW_V4_LIMITS.policyBytes, 'Independent source policy'),
      originalText(bundleText, CONFIGURED_WINDOW_V4_LIMITS.bundleBytes, 'Original configured window bundle'),
      jsonText(report, CONFIGURED_WINDOW_V4_LIMITS.reportBytes, 'Configured window report'),
      originalText(optionsText, CONFIGURED_WINDOW_V4_LIMITS.optionsBytes, 'Independent configured window limits')));
  }

  function analyzeConfiguredWindowV4(bundleText, options) {
    const [config, policy, limits] = independentOptions(options);
    return analyzeConfiguredWindowTextV4(bundleText, config, policy, limits);
  }

  function verifyConfiguredWindowV4(bundleText, report, options) {
    const [config, policy, limits] = independentOptions(options);
    return verifyConfiguredWindowTextV4(bundleText, report, config, policy, limits);
  }

  return {analyzeConfiguredWindowV4, verifyConfiguredWindowV4,
    analyzeConfiguredWindowTextV4, verifyConfiguredWindowTextV4};
}
