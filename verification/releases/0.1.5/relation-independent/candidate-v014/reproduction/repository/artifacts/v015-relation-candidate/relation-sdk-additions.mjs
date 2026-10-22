
/**
 * @typedef {Object} RelationCaptureV3
 * @property {3} traceSchema
 * @property {'relation-set-v1'} dataModel
 * @property {string} clockDomain
 * @property {{exclusiveWriters: boolean, completeSnapshotTables: ReadonlyArray<string>}} scope
 * @property {Object} relationSchema
 * @property {ReadonlyArray<Object>} events
 * @property {ReadonlyArray<Object>} gaps
 *
 * @typedef {{maxStates?: number, maxOperationChecks?: number}} RelationAnalysisOptionsV3
 * @typedef {{maxChecks?: number, analysisOptions?: RelationAnalysisOptionsV3}} RelationReductionOptionsV3
 */

// Check the caller's model once, then pass the exact text to the bounded core.
// JSON.parse here does not replace MoonBit's duplicate-key/shape validation.
function relationCaptureTextV3(trace) {
  if (typeof trace !== 'string' && (trace === null || typeof trace !== 'object')) {
    throw new TypeError('Relation v3 capture must be JSON text or a capture object');
  }
  const text = v3Text(trace, 8 * 1024 * 1024);
  const capture = JSON.parse(text);
  if (capture === null || Array.isArray(capture) || capture.traceSchema !== 3 || capture.dataModel !== 'relation-set-v1') {
    throw new TypeError('Expected traceSchema 3 and dataModel relation-set-v1');
  }
  return text;
}

/** @param {string | RelationCaptureV3} trace */
export function normalizeRelationCaptureV3(trace) {
  return normalizeCaptureV3(relationCaptureTextV3(trace));
}

/** @param {string | RelationCaptureV3} trace @param {RelationAnalysisOptionsV3} options */
export function analyzeRelationV3(trace, options = {}) {
  return analyzeV3(relationCaptureTextV3(trace), options);
}

/** @param {string | RelationCaptureV3} trace @param {RelationReductionOptionsV3} options */
export function reduceRelationV3(trace, options = {}) {
  return reduceV3(relationCaptureTextV3(trace), options);
}

/** @param {string | RelationCaptureV3} trace */
export function verifyRelationV3(trace, report) {
  return verifyV3(relationCaptureTextV3(trace), report);
}

/** @param {string | RelationCaptureV3} trace */
export function makeRelationCapsuleV3(trace, report) {
  return makeCapsuleV3(relationCaptureTextV3(trace), report);
}

/** Verify the complete generic capsule before accepting its fixed relation model. */
export function replayRelationCapsuleV3(text) {
  if (typeof text !== 'string') throw new TypeError('Relation v3 capsule must be JSON text');
  const result = replayCapsuleV3(text);
  if (!result.valid) return result;
  let trace;
  try {
    trace = JSON.parse(JSON.parse(text).traceText);
  } catch {
    // A generic v3 capsule can faithfully reproduce an invalid-JSON diagnostic.
    // Such a trace cannot declare this fixed model, even when replay is valid.
    return {valid: false, reason: 'Expected traceSchema 3 and dataModel relation-set-v1'};
  }
  if (trace === null || typeof trace !== 'object' || Array.isArray(trace) || trace.traceSchema !== 3 || trace.dataModel !== 'relation-set-v1') {
    return {valid: false, reason: 'Expected traceSchema 3 and dataModel relation-set-v1'};
  }
  return result;
}
