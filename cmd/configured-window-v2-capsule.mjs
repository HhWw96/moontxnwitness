// Offline transport only. Independent callers select the configuration and budgets.
import {createHash} from 'node:crypto';
import * as standalone from './configured-window-v2-standalone.mjs';

const MiB = 1024 * 1024;
export const CONFIGURED_WINDOW_CAPSULE_V4_LIMITS = Object.freeze({
  bundleBytes: 32 * MiB,
  analysisReportBytes: 32 * MiB,
  reductionReportBytes: 64 * MiB,
  analysisCapsuleBytes: 136 * MiB,
  reductionCapsuleBytes: 264 * MiB,
});
const specs = Object.freeze({
  analysis: Object.freeze({
    format: 'moontxnwitness-configured-source-window-capsule/v1',
    reportFormat: 'moontxnwitness-configured-window-analysis/v2',
    reportBytes: CONFIGURED_WINDOW_CAPSULE_V4_LIMITS.analysisReportBytes,
    capsuleBytes: CONFIGURED_WINDOW_CAPSULE_V4_LIMITS.analysisCapsuleBytes,
    make: 'analyzeConfiguredWindowV4', verify: 'verifyConfiguredWindowV4',
  }),
  reduction: Object.freeze({
    format: 'moontxnwitness-configured-source-window-reduction-capsule/v1',
    reportFormat: 'moontxnwitness-configured-window-reduction/v1',
    reportBytes: CONFIGURED_WINDOW_CAPSULE_V4_LIMITS.reductionReportBytes,
    capsuleBytes: CONFIGURED_WINDOW_CAPSULE_V4_LIMITS.reductionCapsuleBytes,
    make: 'reduceConfiguredWindowV4', verify: 'verifyConfiguredWindowReductionV4',
  }),
});
const fields = Object.freeze(['format', 'operation', 'bundleText', 'bundleSha256',
  'reportText', 'reportSha256', 'capsuleSha256']);
const sha256 = text => createHash('sha256').update(text, 'utf8').digest('hex');

function boundedText(value, maximum, label) {
  if (typeof value !== 'string' || !value.isWellFormed()) {
    throw new TypeError(label + ' must be original well-formed UTF-8 text');
  }
  if (Buffer.byteLength(value, 'utf8') > maximum) throw new RangeError(label + ' exceeds its UTF-8 byte limit');
  return value;
}

function object(value, label) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)
      || ![Object.prototype, null].includes(Object.getPrototypeOf(value))) {
    throw new TypeError(label + ' must be a plain object');
  }
  return value;
}

function independentOptions(value, operation) {
  object(value, 'Independent configured window options');
  for (const name of ['config', 'policy']) {
    if (!Object.hasOwn(value, name)) throw new TypeError('Independent ' + name + ' is required');
  }
  if (operation === 'reduction' && value.preserveModel !== 'serializable') {
    throw new TypeError('Independent preserveModel must be serializable');
  }
  // The existing SDK validates allowed fields, individual text limits and budgets.
  return value;
}

function reportText(value, spec) {
  object(value, 'Configured window report');
  if (value.format !== spec.reportFormat) throw new TypeError('Unexpected configured window report format');
  return boundedText(JSON.stringify(value, (_name, item) => {
    if (typeof item === 'number' && !Number.isSafeInteger(item)) {
      throw new TypeError('Configured window report contains an inexact JSON number');
    }
    if (item === undefined || typeof item === 'function' || typeof item === 'symbol') {
      throw new TypeError('Configured window report contains a non-JSON value');
    }
    return item;
  }), spec.reportBytes, 'Configured window report');
}

function envelope(operation, bundle, report) {
  const body = {
    format: specs[operation].format, operation,
    bundleText: bundle, bundleSha256: sha256(bundle),
    reportText: report, reportSha256: sha256(report),
  };
  return {...body, capsuleSha256: sha256(JSON.stringify(body))};
}

function reject(operation, reason, envelopeVerified = false) {
  return {
    format: 'moontxnwitness-configured-source-window-capsule-verification/v1',
    operation, valid: false, envelopeVerified, reportMatches: false,
    refutationVerified: false, oneMinimalVerified: false, sourceAuthenticated: false,
    reason: String(reason).slice(0, 1024),
  };
}

/** SDK injection is an explicit trusted caller choice, never capsule content. */
export function createConfiguredWindowCapsulesV4(sdk) {
  object(sdk, 'Configured window SDK');
  const callbacks = {};
  for (const spec of Object.values(specs)) {
    for (const name of [spec.make, spec.verify]) {
      if (typeof sdk[name] !== 'function') throw new TypeError('Missing configured window SDK entry ' + name);
      callbacks[name] = sdk[name].bind(sdk);
    }
  }

  function make(operation, bundleText, options) {
    const spec = specs[operation];
    const bundle = boundedText(bundleText, CONFIGURED_WINDOW_CAPSULE_V4_LIMITS.bundleBytes, 'Original configured window bundle');
    const independent = independentOptions(options, operation);
    const report = reportText(callbacks[spec.make](bundle, independent), spec);
    const checked = callbacks[spec.verify](bundle, report, independent);
    if (checked?.reportMatches !== true) throw new Error('Cannot package a report that does not independently reproduce');
    // Matching unknown/invalid diagnostics can be retained, but confer no authority.
    const text = JSON.stringify(envelope(operation, bundle, report)) + '\n';
    return boundedText(text, spec.capsuleBytes, 'Configured window capsule');
  }

  function replay(operation, capsuleText, options) {
    const spec = specs[operation];
    let envelopeVerified = false;
    try {
      const text = boundedText(capsuleText, spec.capsuleBytes, 'Configured window capsule');
      const value = object(JSON.parse(text), 'Configured window capsule');
      if (JSON.stringify(Object.keys(value)) !== JSON.stringify(fields)
          || value.format !== spec.format || value.operation !== operation) {
        throw new TypeError('Unexpected configured window capsule schema or operation');
      }
      const bundle = boundedText(value.bundleText, CONFIGURED_WINDOW_CAPSULE_V4_LIMITS.bundleBytes, 'Original configured window bundle');
      const report = boundedText(value.reportText, spec.reportBytes, 'Configured window report');
      // Exact generator encoding rejects duplicate/escaped keys, extra fields,
      // alternate ordering and whitespace before any inner JSON is interpreted.
      if (text !== JSON.stringify(envelope(operation, bundle, report)) + '\n') {
        throw new TypeError('Configured window capsule encoding or digests differ');
      }
      envelopeVerified = true;
      const independent = independentOptions(options, operation);
      // Original text goes straight to MoonBit; host parsing cannot erase inner
      // duplicate keys or change original SQL, numeric tokens and source evidence.
      const checked = callbacks[spec.verify](bundle, report, independent);
      if (checked?.reportMatches !== true) return reject(operation, 'Configured window report does not reproduce under independent inputs', true);
      const parsed = object(JSON.parse(report), 'Configured window report');
      if (parsed.format !== spec.reportFormat) return reject(operation, 'Unexpected configured window report format', true);
      const valid = checked.valid === true && !['unknown', 'invalid'].includes(parsed.status);
      return {
        format: 'moontxnwitness-configured-source-window-capsule-verification/v1',
        operation, valid, envelopeVerified: true, reportMatches: true,
        status: parsed.status,
        refutationVerified: operation === 'reduction' && valid && checked.refutationVerified === true,
        oneMinimalVerified: operation === 'reduction' && valid && checked.refutationVerified === true && checked.oneMinimalVerified === true,
        sourceAuthenticated: false,
        bundleSha256: value.bundleSha256, reportSha256: value.reportSha256,
        capsuleSha256: value.capsuleSha256, report: parsed,
      };
    } catch (error) {
      return reject(operation, error.message ?? error, envelopeVerified);
    }
  }

  return Object.freeze({
    makeConfiguredWindowCapsuleV4: (bundle, options) => make('analysis', bundle, options),
    replayConfiguredWindowCapsuleV4: (capsule, independent) => replay('analysis', capsule, independent),
    makeConfiguredWindowReductionCapsuleV4: (bundle, options) => make('reduction', bundle, options),
    replayConfiguredWindowReductionCapsuleV4: (capsule, independent) => replay('reduction', capsule, independent),
  });
}

export const {makeConfiguredWindowCapsuleV4, replayConfiguredWindowCapsuleV4,
  makeConfiguredWindowReductionCapsuleV4, replayConfiguredWindowReductionCapsuleV4} = createConfiguredWindowCapsulesV4(standalone);
