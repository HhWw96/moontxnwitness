import {createHash} from 'node:crypto';
import {
  reduce_relation_models_v4_json,
  verify_relation_model_reduction_v4_json,
  relation_model_reduction_options_v4_content_json,
  relation_model_reduction_report_v4_content_json,
  relation_model_reduction_capsule_v4_content_json,
  version,
} from './core.mjs';

const MiB = 1024 * 1024;
export const RELATION_MODEL_REDUCTION_V4_LIMITS = Object.freeze({
  sourceUtf8Bytes: 8 * MiB,
  optionsUtf8Bytes: 8192,
  reportUtf8Bytes: 32 * MiB,
  capsuleUtf8Bytes: 64 * MiB,
  maxChecks: 256,
  maxSourceChecks: 1000000,
  maxStates: 100000,
  maxEdgeChecks: 1000000,
});
const FORMAT = 'moontxnwitness-relation-model-reduction-replay/v4';
const OPERATION = 'reduce-relation-models';
const IDENTITIES = Object.freeze({
  semanticContract: 'relation-predicate-model-reduction/v1',
  classificationContract: 'relation-predicate-models/v1',
  algorithm: 'source-closed-single-delete-fixed-relation-model-1',
  counterContract: 'relation-model-single-delete-candidate-checks-1',
});
const SCOPE = 'model-preserving source-closed reduction under an independently selected model and budgets; original observations are not authenticated';
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

function prepared(options) {
  if (typeof options !== 'string' && (options === null || typeof options !== 'object' || Array.isArray(options) || ![Object.prototype, null].includes(Object.getPrototypeOf(options)))) {
    throw new TypeError('relation model reduction options must be a plain object or JSON object text');
  }
  const input = bounded(options, RELATION_MODEL_REDUCTION_V4_LIMITS.optionsUtf8Bytes, 'relation model reduction options');
  const normalized = guarded(input, relation_model_reduction_options_v4_content_json, 'relation model reduction options');
  return {normalized, text: bounded(normalized, RELATION_MODEL_REDUCTION_V4_LIMITS.optionsUtf8Bytes, 'normalized relation model reduction options')};
}

/** Validate decoded keys before returning omitted fields for command merging. */
export function parseRelationModelReductionOptionsV4(input) {
  const text = bounded(input, RELATION_MODEL_REDUCTION_V4_LIMITS.optionsUtf8Bytes, 'relation model reduction options');
  prepared(text);
  return JSON.parse(text);
}

function identity(report) {
  if (report?.format !== 'moontxnwitness-relation-model-reduction/v4' || report.schemaVersion !== 4) throw new TypeError('Unsupported relation model reduction report');
  for (const key of ['semanticContract', 'classificationContract', 'algorithm']) {
    if (report[key] !== IDENTITIES[key]) throw new TypeError('Unsupported relation model reduction ' + key);
  }
  if (report.execution?.counterContract !== IDENTITIES.counterContract) throw new TypeError('Unsupported relation model reduction counter contract');
  return IDENTITIES;
}

function run(sourceText, optionsText) {
  const reportText = bounded(reduce_relation_models_v4_json(sourceText, optionsText), RELATION_MODEL_REDUCTION_V4_LIMITS.reportUtf8Bytes, 'relation model reduction report');
  const report = guarded(reportText, relation_model_reduction_report_v4_content_json, 'relation model reduction report');
  identity(report);
  return {reportText, report};
}

export function reduceRelationModelsV4(source, options) {
  return run(bounded(source, RELATION_MODEL_REDUCTION_V4_LIMITS.sourceUtf8Bytes, 'relation model reduction source'), prepared(options).text).report;
}

export function verifyRelationModelReductionV4(source, report, expectedOptions) {
  try {
    const sourceText = bounded(source, RELATION_MODEL_REDUCTION_V4_LIMITS.sourceUtf8Bytes, 'relation model reduction source');
    const reportText = bounded(report, RELATION_MODEL_REDUCTION_V4_LIMITS.reportUtf8Bytes, 'relation model reduction report');
    identity(guarded(reportText, relation_model_reduction_report_v4_content_json, 'relation model reduction report'));
    return JSON.parse(verify_relation_model_reduction_v4_json(sourceText, reportText, prepared(expectedOptions).text));
  } catch (error) {
    return {valid: false, reason: error.message, scope: SCOPE};
  }
}

export function makeRelationModelReductionCapsuleV4(source, options) {
  const sourceText = bounded(source, RELATION_MODEL_REDUCTION_V4_LIMITS.sourceUtf8Bytes, 'relation model reduction source');
  const optionsText = prepared(options).text;
  const {reportText, report} = run(sourceText, optionsText);
  return bounded({
    format: FORMAT,
    schemaVersion: 4,
    tool: 'MoonTxnWitness',
    producer: {version: version()},
    operation: OPERATION,
    ...identity(report),
    sourceText,
    sourceSha256: hash(sourceText),
    optionsText,
    optionsSha256: hash(optionsText),
    reportText,
    reportSha256: hash(reportText),
  }, RELATION_MODEL_REDUCTION_V4_LIMITS.capsuleUtf8Bytes, 'relation model reduction capsule');
}

/** Hashes bind bytes; only caller-selected policies authorize recomputation. */
export function replayRelationModelReductionCapsuleV4(input, expectedOptions) {
  const reject = reason => ({valid: false, reason, scope: SCOPE});
  try {
    const independent = prepared(expectedOptions);
    const capsule = guarded(bounded(input, RELATION_MODEL_REDUCTION_V4_LIMITS.capsuleUtf8Bytes, 'relation model reduction capsule'), relation_model_reduction_capsule_v4_content_json, 'relation model reduction capsule');
    for (const [key, maximum] of [
      ['source', RELATION_MODEL_REDUCTION_V4_LIMITS.sourceUtf8Bytes],
      ['options', RELATION_MODEL_REDUCTION_V4_LIMITS.optionsUtf8Bytes],
      ['report', RELATION_MODEL_REDUCTION_V4_LIMITS.reportUtf8Bytes],
    ]) {
      const text = bounded(capsule[key + 'Text'], maximum, key);
      if (hash(text) !== capsule[key + 'Sha256']) return reject(key + '-sha256-mismatch');
    }
    const report = guarded(capsule.reportText, relation_model_reduction_report_v4_content_json, 'relation model reduction report');
    for (const [key, value] of Object.entries(identity(report))) {
      if (capsule[key] !== value) return reject('capsule-report-' + key + '-mismatch');
    }
    if (prepared(capsule.optionsText).text !== independent.text) return reject('caller-expected-reduction-options-mismatch');
    if (report.preserveModel !== independent.normalized.model) return reject('caller-expected-model-mismatch');
    if (verifyRelationModelReductionV4(capsule.sourceText, capsule.reportText, expectedOptions).valid !== true) return reject('recomputed-relation-model-reduction-differs');
    return {
      valid: true,
      status: 'recomputed',
      operation: OPERATION,
      reductionStatus: report.status,
      preserveModel: report.preserveModel,
      oneMinimal: report.oneMinimal,
      ...IDENTITIES,
      producer: capsule.producer,
      scope: SCOPE,
    };
  } catch (error) {
    return reject(error.message);
  }
}
