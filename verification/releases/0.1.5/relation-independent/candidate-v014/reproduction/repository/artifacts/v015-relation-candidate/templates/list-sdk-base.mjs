
/**
 * @typedef {Object} AppendListCaptureV3
 * @property {3} traceSchema
 * @property {'append-list-v1'} dataModel
 * @property {string} clockDomain
 * @property {{exclusiveWriters: boolean}} scope
 * @property {ReadonlyArray<Object>} events
 * @property {ReadonlyArray<Object>} gaps
 *
 * @typedef {{maxStates?: number, maxOperationChecks?: number}} ListAnalysisOptionsV3
 * @typedef {{maxChecks?: number, analysisOptions?: ListAnalysisOptionsV3}} ListReductionOptionsV3
 */

// Check the caller's model once, then pass the exact text to the bounded core.
// JSON.parse here does not replace MoonBit's duplicate-key/shape validation.
function listCaptureTextV3(trace) {
  if (typeof trace !== 'string' && (trace === null || typeof trace !== 'object')) {
    throw new TypeError('List v3 capture must be JSON text or a capture object');
  }
  const text = v3Text(trace, 8 * 1024 * 1024);
  const capture = JSON.parse(text);
  if (capture === null || Array.isArray(capture) || capture.traceSchema !== 3 || capture.dataModel !== 'append-list-v1') {
    throw new TypeError('Expected traceSchema 3 and dataModel append-list-v1');
  }
  return text;
}

/** @param {string | AppendListCaptureV3} trace */
export function normalizeListCaptureV3(trace) {
  return normalizeCaptureV3(listCaptureTextV3(trace));
}

/** @param {string | AppendListCaptureV3} trace @param {ListAnalysisOptionsV3} options */
export function analyzeListV3(trace, options = {}) {
  return analyzeV3(listCaptureTextV3(trace), options);
}

/** @param {string | AppendListCaptureV3} trace @param {ListReductionOptionsV3} options */
export function reduceListV3(trace, options = {}) {
  return reduceV3(listCaptureTextV3(trace), options);
}

/** @param {string | AppendListCaptureV3} trace */
export function verifyListV3(trace, report) {
  return verifyV3(listCaptureTextV3(trace), report);
}

/** @param {string | AppendListCaptureV3} trace */
export function makeListCapsuleV3(trace, report) {
  return makeCapsuleV3(listCaptureTextV3(trace), report);
}

/** Verify the complete generic capsule before accepting its fixed list model. */
export function replayListCapsuleV3(text) {
  if (typeof text !== 'string') throw new TypeError('List v3 capsule must be JSON text');
  const result = replayCapsuleV3(text);
  if (!result.valid) return result;
  let trace;
  try {
    trace = JSON.parse(JSON.parse(text).traceText);
  } catch {
    // A generic v3 capsule can faithfully reproduce an invalid-JSON diagnostic.
    // Such a trace cannot declare this fixed model, even when replay is valid.
    return {valid: false, reason: 'Expected traceSchema 3 and dataModel append-list-v1'};
  }
  if (trace === null || typeof trace !== 'object' || Array.isArray(trace) || trace.traceSchema !== 3 || trace.dataModel !== 'append-list-v1') {
    return {valid: false, reason: 'Expected traceSchema 3 and dataModel append-list-v1'};
  }
  return result;
}
