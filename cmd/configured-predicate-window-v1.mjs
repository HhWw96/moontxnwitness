// PostgreSQL observation admission and relation analysis independently execute in MoonBit.
import {createHash} from 'node:crypto';
import {admitConfiguredPredicateWindowV1} from './configured-predicate-admission-v1.mjs';
import {classifyRelationPredicateV4} from './relation-v4.mjs';
import {classifyRelationModelsV4} from './relation-models-v4.mjs';
import {reduceRelationCategoryV4} from './relation-reduction-v4.mjs';

const RULES = 'adya-2000-scoped-categories-v1';
const CAPSULE = 'moontxnwitness-configured-predicate-capsule/v1';
const MAX_CAPSULE_BYTES = 64 * 1024 * 1024;
const digest = text => createHash('sha256').update(text).digest('hex');

function normalize(admission) {
  const events = [{kind: 'snapshot', consistent: true, initial: {configured: admission.startingRows}}];
  const provenance = [];
  for (const {originalSnapshot, originalRequestSeq, ...source} of admission.events) {
    if (source.kind === 'begin') {
      events.push({...source, connection: source.tx});
    } else if (source.kind === 'commit') {
      events.push({kind: 'commit_request', tx: source.tx}, {kind: 'commit_ok', tx: source.tx});
    } else {
      events.push(source);
      provenance.push({sequence: events.length, tx: source.tx, requestSeq: originalRequestSeq,
        ...(originalSnapshot === undefined ? {} : {snapshot: originalSnapshot})});
    }
  }
  const history = {
    traceSchema: 3, dataModel: 'relation-set-v1', clockDomain: 'configured-predicate-log-order/v1',
    relationSchema: {configured: {primaryKey: 'pk', columns: {pk: 'int64', body: 'text'}}},
    scope: {exclusiveWriters: true, completeSnapshotTables: ['configured']}, gaps: [],
    events: events.map((event, time) => ({...event, seq: time + 1, time})),
  };
  return [JSON.stringify(history), provenance];
}

export function analyzeConfiguredPredicateWindowV1(bundleText, options) {
  const {maxStates = 100_000, maxChecks = 1_000_000} = options;
  if (!Number.isSafeInteger(maxStates) || maxStates < 0 || maxStates > 100_000) {
    throw new RangeError('maxStates must be an integer from 0 to 100000');
  }
  const admission = admitConfiguredPredicateWindowV1(bundleText, options);
  const header = {format: 'moontxnwitness-configured-predicate-analysis/v1',
    bundleSha256: digest(bundleText), budgets: {maxChecks, maxStates},
    coverageComplete: admission.coverageComplete, admission};
  if (!admission.coverageComplete) return {...header, status: 'unknown'};
  const [historyText, provenance] = normalize(admission);
  const g2 = classifyRelationPredicateV4(historyText, {category: 'G2', ruleSet: RULES, maxStates});
  const g2Item = classifyRelationPredicateV4(historyText, {category: 'G2-item', ruleSet: RULES, maxStates});
  const model = classifyRelationModelsV4(historyText, {models: ['serializable'], realtimeKnown: false, maxStates});
  if (g2.status === 'refuted' && model.status === 'checked-compatible') {
    throw new Error('A compatible serial certificate contradicts the verified predicate witness');
  }
  const status = g2.status === 'refuted' ? 'refuted' : model.status;
  return {...header, status, historyText, provenance, g2, g2Item, model};
}

export function reduceConfiguredPredicateWindowV1(bundleText, options) {
  const {category = 'G2', maxReductionChecks = 256, maxStates = 100_000} = options;
  if (category !== 'G2' && category !== 'G2-item') throw new TypeError('Select G2 or G2-item');
  const analysis = analyzeConfiguredPredicateWindowV1(bundleText, options);
  const header = {format: 'moontxnwitness-configured-predicate-reduction/v1',
    category, maxReductionChecks, analysis, coverageComplete: analysis.coverageComplete};
  if (!analysis.coverageComplete) return {...header, status: 'unknown'};
  const reduction = reduceRelationCategoryV4(analysis.historyText,
    {category, ruleSet: RULES, maxChecks: maxReductionChecks, maxStates});
  return {...header, status: reduction.status, reduction};
}

function recompute(kind, bundleText, options) {
  if (kind === 'analysis') return analyzeConfiguredPredicateWindowV1(bundleText, options);
  if (kind === 'reduction') return reduceConfiguredPredicateWindowV1(bundleText, options);
  throw new TypeError('Expected an analysis or reduction capsule');
}

export function makeConfiguredPredicateCapsuleV1(bundleText, options, kind = 'analysis') {
  const reportText = JSON.stringify(recompute(kind, bundleText, options));
  const bound = {format: CAPSULE, kind, bundleText, bundleSha256: digest(bundleText),
    reportText, reportSha256: digest(reportText)};
  const encoded = JSON.stringify({...bound, capsuleSha256: digest(JSON.stringify(bound))}) + '\n';
  if (Buffer.byteLength(encoded) > MAX_CAPSULE_BYTES) throw new RangeError('Predicate capsule byte limit exceeded');
  return encoded;
}

export function replayConfiguredPredicateCapsuleV1(capsuleText, options) {
  try {
    if (typeof capsuleText !== 'string' || Buffer.byteLength(capsuleText) > MAX_CAPSULE_BYTES) {
      throw new TypeError('Bounded original capsule text required');
    }
    const {format, kind, bundleText, bundleSha256, reportText, reportSha256, capsuleSha256} = JSON.parse(capsuleText);
    const bound = {format, kind, bundleText, bundleSha256, reportText, reportSha256};
    if (format !== CAPSULE || typeof bundleText !== 'string' || typeof reportText !== 'string' ||
        digest(bundleText) !== bundleSha256 || digest(reportText) !== reportSha256 ||
        digest(JSON.stringify(bound)) !== capsuleSha256 ||
        JSON.stringify({...bound, capsuleSha256}) + '\n' !== capsuleText) {
      throw new TypeError('Predicate capsule content or binding differs');
    }
    const report = recompute(kind, bundleText, options);
    const reportMatches = JSON.stringify(report) === reportText;
    const resolved = kind === 'analysis' ? ['checked-compatible', 'refuted'] : ['reduced', 'unchanged'];
    return {valid: reportMatches && report.coverageComplete && resolved.includes(report.status),
      reportMatches, kind, status: report.status, report};
  } catch (error) {
    return {valid: false, reportMatches: false, status: 'unknown', reason: error.message};
  }
}
