import {createHash} from 'node:crypto';
import {
  classify_relation_models_v4_json,
  verify_relation_models_v4_json,
  relation_model_options_v4_content_json,
  relation_model_report_v4_content_json,
  relation_model_capsule_v4_content_json,
  version,
} from './core.mjs';

const MiB = 1024 * 1024;
export const RELATION_MODEL_V4_LIMITS = Object.freeze({
  sourceUtf8Bytes: 8 * MiB,
  optionsUtf8Bytes: 8192,
  reportUtf8Bytes: 32 * MiB,
  capsuleUtf8Bytes: 64 * MiB,
  maxSourceChecks: 1000000,
  maxStates: 100000,
  maxEdgeChecks: 1000000,
});
const FORMAT = 'moontxnwitness-relation-model-replay/v4';
const IDENTITIES = Object.freeze({
  semanticContract: 'relation-predicate-models/v1',
  algorithm: 'predicate-source-scoped-graph-and-original-prefix-search-1',
  counterContract: 'relation-model-independent-source-scoped-graph-and-prefix-counters-1',
});
const SCOPE = 'relation model reproduction under independently selected source facts, models and budgets; observations are not authenticated';
const hash = text => createHash('sha256').update(text, 'utf8').digest('hex');

function bounded(value, maximum, label) {
  const text = typeof value === 'string' ? value : JSON.stringify(value);
  if (typeof text !== 'string') throw new TypeError(label + ' must be JSON text or serializable data');
  if (Buffer.byteLength(text, 'utf8') > maximum) throw new RangeError(label + ' exceeds ' + maximum + ' UTF-8 bytes');
  if (Buffer.from(text, 'utf8').toString('utf8') !== text) throw new TypeError(label + ' contains malformed Unicode');
  return text;
}

function guarded(text, normalizer, label) {
  const result = JSON.parse(normalizer(text));
  if (result.valid !== true) throw new TypeError(result.error || 'Invalid ' + label);
  return result.options ?? result.value;
}

function prepared(options = {}) {
  if (typeof options !== 'string' && (options === null || typeof options !== 'object' || Array.isArray(options) || ![Object.prototype, null].includes(Object.getPrototypeOf(options)))) {
    throw new TypeError('relation model options must be a plain object or JSON object text');
  }
  const requested = bounded(options, RELATION_MODEL_V4_LIMITS.optionsUtf8Bytes, 'relation model options');
  const normalized = guarded(requested, relation_model_options_v4_content_json, 'relation model options');
  return {normalized, text: bounded(normalized, RELATION_MODEL_V4_LIMITS.optionsUtf8Bytes, 'normalized relation model options')};
}

/** Preserve omitted fields for CLI merging after strict decoded-key checks. */
export function parseRelationModelOptionsV4(input) {
  const text = bounded(input, RELATION_MODEL_V4_LIMITS.optionsUtf8Bytes, 'relation model options');
  prepared(text);
  return JSON.parse(text);
}

function identity(report) {
  if (report?.format !== 'moontxnwitness-relation-model-composition/v4' || report.schemaVersion !== 4) throw new TypeError('Unsupported relation model report');
  if (report.semanticContract !== IDENTITIES.semanticContract || report.algorithm !== IDENTITIES.algorithm || report.execution?.counterContract !== IDENTITIES.counterContract) {
    throw new TypeError('Unsupported relation model semantic/algorithm/counter identity');
  }
  return IDENTITIES;
}

function run(sourceText, optionsText) {
  const reportText = bounded(classify_relation_models_v4_json(sourceText, optionsText), RELATION_MODEL_V4_LIMITS.reportUtf8Bytes, 'relation model report');
  const report = guarded(reportText, relation_model_report_v4_content_json, 'relation model report');
  identity(report);
  return {reportText, report};
}

export function classifyRelationModelsV4(source, options = {}) {
  return run(bounded(source, RELATION_MODEL_V4_LIMITS.sourceUtf8Bytes, 'relation model source'), prepared(options).text).report;
}

export function verifyRelationModelsV4(source, report, expectedOptions = {}) {
  try {
    const sourceText = bounded(source, RELATION_MODEL_V4_LIMITS.sourceUtf8Bytes, 'relation model source');
    const reportText = bounded(report, RELATION_MODEL_V4_LIMITS.reportUtf8Bytes, 'relation model report');
    identity(guarded(reportText, relation_model_report_v4_content_json, 'relation model report'));
    return JSON.parse(verify_relation_models_v4_json(sourceText, reportText, prepared(expectedOptions).text));
  } catch (error) {
    return {valid: false, reason: error.message, scope: SCOPE};
  }
}

export function makeRelationModelsCapsuleV4(source, options = {}) {
  const sourceText = bounded(source, RELATION_MODEL_V4_LIMITS.sourceUtf8Bytes, 'relation model source');
  const optionsText = prepared(options).text;
  const {reportText, report} = run(sourceText, optionsText);
  return bounded({
    format: FORMAT,
    schemaVersion: 4,
    tool: 'MoonTxnWitness',
    producer: {version: version()},
    operation: 'classify-relation-models',
    ...identity(report),
    sourceText,
    sourceSha256: hash(sourceText),
    optionsText,
    optionsSha256: hash(optionsText),
    reportText,
    reportSha256: hash(reportText),
  }, RELATION_MODEL_V4_LIMITS.capsuleUtf8Bytes, 'relation model capsule');
}

/** Embedded policies and matching hashes cannot authorize a caller's replay. */
export function replayRelationModelsCapsuleV4(input, expectedOptions = {}) {
  const reject = reason => ({valid: false, reason, scope: SCOPE});
  try {
    const capsule = guarded(bounded(input, RELATION_MODEL_V4_LIMITS.capsuleUtf8Bytes, 'relation model capsule'), relation_model_capsule_v4_content_json, 'relation model capsule');
    for (const [key, maximum] of [
      ['source', RELATION_MODEL_V4_LIMITS.sourceUtf8Bytes],
      ['options', RELATION_MODEL_V4_LIMITS.optionsUtf8Bytes],
      ['report', RELATION_MODEL_V4_LIMITS.reportUtf8Bytes],
    ]) {
      const text = bounded(capsule[key + 'Text'], maximum, key);
      if (hash(text) !== capsule[key + 'Sha256']) return reject(key + '-sha256-mismatch');
    }
    const report = guarded(capsule.reportText, relation_model_report_v4_content_json, 'relation model report');
    for (const [key, value] of Object.entries(identity(report))) {
      if (capsule[key] !== value) return reject('capsule-report-' + key + '-mismatch');
    }
    if (prepared(capsule.optionsText).text !== prepared(expectedOptions).text) return reject('caller-expected-relation-model-options-mismatch');
    if (verifyRelationModelsV4(capsule.sourceText, capsule.reportText, expectedOptions).valid !== true) return reject('recomputed-relation-model-report-differs');
    return {
      valid: true,
      status: 'recomputed',
      operation: 'classify-relation-models',
      modelStatus: report.status,
      ...IDENTITIES,
      models: report.models.map(model => ({model: model.model, status: model.status})),
      producer: capsule.producer,
      scope: SCOPE,
    };
  } catch (error) {
    return reject(error.message);
  }
}
