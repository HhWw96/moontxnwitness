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

export const CONFIGURED_WINDOW_REDUCTION_V4_LIMITS = Object.freeze({
  bundleBytes: 32 * 1024 * 1024, reportBytes: 64 * 1024 * 1024,
  configBytes: 262144, policyBytes: 8192, optionsBytes: 524288,
  maxChecks: 256, maxSourceChecks: 1000000, maxStates: 100000, maxEdgeChecks: 1000000,
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

function independentReductionOptions(value) {
  object(value, 'Independent configured window reduction options');
  for (const name of ['config', 'policy', 'preserveModel']) {
    if (!Object.hasOwn(value, name)) throw new TypeError('Independent ' + name + ' is required');
  }
  if (value.preserveModel !== 'serializable') throw new TypeError('preserveModel must be serializable');
  const limits = {};
  for (const name of Object.keys(value)) {
    if (name === 'config' || name === 'policy') continue;
    if (!['preserveModel', 'windowOptions', 'reductionOptions'].includes(name)) {
      throw new TypeError('Unknown configured window reduction option: ' + name);
    }
    limits[name] = value[name];
  }
  if (Object.hasOwn(limits, 'windowOptions')) object(limits.windowOptions, 'Independent windowOptions');
  if (Object.hasOwn(limits, 'reductionOptions')) {
    const reduction = object(limits.reductionOptions, 'Independent reductionOptions');
    for (const name of Object.keys(reduction)) {
      if (!['maxChecks', 'modelOptions'].includes(name)) throw new TypeError('Unknown independent reduction option: ' + name);
    }
    if (Object.hasOwn(reduction, 'maxChecks')
        && (!Number.isSafeInteger(reduction.maxChecks) || reduction.maxChecks < 0 || reduction.maxChecks > 256)) {
      throw new RangeError('maxChecks must be an integer in 0..256');
    }
    if (Object.hasOwn(reduction, 'modelOptions')) {
      for (const [name, number] of Object.entries(object(reduction.modelOptions, 'Independent reduction model budgets'))) {
        if (!['maxSourceChecks', 'maxStates', 'maxEdgeChecks'].includes(name)) {
          throw new TypeError('Unknown independent reduction model budget: ' + name);
        }
        const maximum = CONFIGURED_WINDOW_REDUCTION_V4_LIMITS[name];
        if (!Number.isSafeInteger(number) || number < 0 || number > maximum) {
          throw new RangeError(name + ' must be an integer in 0..' + maximum);
        }
      }
    }
  }
  return [
    jsonText(value.config, CONFIGURED_WINDOW_REDUCTION_V4_LIMITS.configBytes, 'Independent SQL configuration'),
    jsonText(value.policy, CONFIGURED_WINDOW_REDUCTION_V4_LIMITS.policyBytes, 'Independent source policy'),
    jsonText(limits, CONFIGURED_WINDOW_REDUCTION_V4_LIMITS.optionsBytes, 'Independent reduction options'),
  ];
}

const htmlEscape = value => String(value).replace(/[&<>"']/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[char]));
const htmlJSON = value => htmlEscape(JSON.stringify(value));
const htmlDetails = (label, value) => `<details><summary>${htmlEscape(label)}</summary><pre>${htmlJSON(value)}</pre></details>`;
const canonicalJSON = value => JSON.stringify(value, (_name, item) =>
  item && typeof item === 'object' && !Array.isArray(item)
    ? Object.fromEntries(Object.keys(item).sort().map(name => [name, item[name]])) : item);

function renderConfiguredWindowExplanation(bundleText, data, reduction, reductionVerification) {
  if (data?.format !== 'moontxnwitness-configured-window-analysis/v2') throw new Error('Unsupported configured window report');
  const bundle = JSON.parse(bundleText);
  const lifecycle = bundle.lifecycleText.trimEnd().split('\n').map(line => JSON.parse(line));
  const lifecycleBySeq = new Map(lifecycle.map(event => [event.seq, event]));
  const trace = JSON.parse(bundle.diagnosticTraceText);
  const statements = new Map(trace.events.filter(event => event.kind === 'statement').map(event => [event.seq, event]));
  const history = data.history.events;
  const historyBySeq = new Map(history.map(event => [event.seq, event]));
  const sources = data.operationSources;
  if (!Array.isArray(sources) || new Set(sources.map(source => source.historySeq)).size !== sources.length
      || history.filter(event => ['row_read', 'row_write'].includes(event.kind)).length !== sources.length) {
    throw new Error('Missing explicit history-to-original-statement mapping');
  }
  function historyLink(originalSeq) {
    const event = historyBySeq.get(originalSeq);
    if (!event) throw new Error('Witness references an absent original history event');
    return `<a href="#history-${originalSeq}">${htmlEscape(event.kind)} ${originalSeq}</a>`;
  }
  function frame(seq, kind) {
    const event = lifecycleBySeq.get(seq);
    if (!event || event.kind !== kind || typeof event.frameText !== 'string') throw new Error('Missing original ' + kind + ' reference');
    return JSON.parse(event.frameText);
  }
  const rows = sources.map(source => {
    if (!Number.isSafeInteger(source.historySeq) || source.historySeq <= 0) throw new Error('Invalid explicit history sequence');
    const event = historyBySeq.get(source.historySeq), statement = statements.get(source.originalStatementSeq);
    if (!event || !['row_read', 'row_write'].includes(event.kind) || !statement || event.tx !== statement.tx) {
      throw new Error('History event does not bind the original business statement');
    }
    const projection = frame(source.projectionNoteSeq, 'configured-point-projection');
    const native = frame(source.nativeNoteSeq, 'configured-point-native');
    if (native.statementSeq !== statement.seq || native.tx !== statement.tx
        || native.projectionNoteSeq !== source.projectionNoteSeq
        || projection.descriptor.projectedSql !== statement.sql) throw new Error('Original SQL/native identity mismatch');
    const deliveries = lifecycle.filter(item => item.kind === 'configured-point-delivery').map(item => ({seq: item.seq, frame: JSON.parse(item.frameText)}))
      .filter(item => item.frame.resultId === native.resultId && item.frame.statementSeq === statement.seq && item.frame.tx === statement.tx);
    if (projection.descriptor.businessResult.mode === 'rows' && deliveries.length === 0) throw new Error('Missing actual business delivery');
    const versions = event.kind === 'row_read' ? event.rows.map(row => row.version) : [event.version];
    const sourceEffects = versions.map(version => {
      const id = String(version).replace(/^(?:row:|delete:)/, '');
      return {version, currentRow: data.startSnapshot.rows[id] ?? null,
        effect: data.endSnapshot.effects[id] ?? null};
    });
    return `<tr id="history-${source.historySeq}"><td>${historyLink(source.historySeq)}${htmlDetails('Original mapping', source)}</td>` +
      `<td>${htmlEscape(statement.tx)}<p>Original statement ${statement.seq}</p><pre>${htmlEscape(projection.descriptor.originalSql)}</pre>` +
      htmlDetails('Original parameters', projection.descriptor.originalParameters) + htmlDetails('Executed SQL and parameters', statement) + '</td>' +
      `<td>${htmlDetails('Native result and metadata', native)}${htmlDetails('Actual business deliveries', deliveries)}</td>` +
      `<td>${htmlDetails('Verified relation observation', event)}${htmlDetails('Verified source versions/effects', sourceEffects)}</td></tr>`;
  }).join('');
  const lifecycleRows = history.filter(event => !['row_read', 'row_write'].includes(event.kind)).map(event =>
    `<div id="history-${event.seq}">${htmlDetails('History ' + event.seq + ': ' + event.kind, event)}</div>`).join('');
  const edges = data.itemCategory?.judgment?.rules?.['G2-item']?.evidence?.edges ?? [];
  const edgeRows = edges.map(edge => {
    const references = (edge.observationLinks ?? []).flatMap(link => [link.fromObservationSeq, link.toObservationSeq]);
    return `<li>${references.map(historyLink).join(' → ')}${htmlDetails('Original dependency evidence', edge)}</li>`;
  }).join('');
  let reductionSection = '';
  if (reduction) {
    if (reduction.format !== 'moontxnwitness-configured-window-reduction/v1'
        || canonicalJSON(reduction.window?.history) !== canonicalJSON(data.history)) {
      throw new Error('Reduction does not bind the explained original window history');
    }
    const reduced = reduction.reduction;
    if (!reduced || !Array.isArray(reduced.originalEventSequence)
        || !Array.isArray(reduced.analysisView?.history?.events)) throw new Error('Missing reduced original-event mapping');
    const selected = reduced.analysisView.history.events;
    if (selected.length !== reduced.originalEventSequence.length) throw new Error('Reduced event mapping length differs');
    for (let i = 0; i < selected.length; i++) {
      if (selected[i].seq !== i + 1 || !historyBySeq.has(reduced.originalEventSequence[i])) throw new Error('Invalid reduced local/original event mapping');
    }
    const localLink = seq => {
      if (!Number.isSafeInteger(seq) || seq < 1 || seq > selected.length) throw new Error('Reduced witness local reference is invalid');
      return historyLink(reduced.originalEventSequence[seq - 1]);
    };
    function sourceReferences(value) {
      const refs = new Set(), pending = [value]; let visits = 0;
      while (pending.length) {
        if (++visits > 1000000) throw new RangeError('Explanation source traversal budget exhausted');
        const current = pending.pop();
        if (!current || typeof current !== 'object') continue;
        for (const [name, item] of Object.entries(current)) {
          if (['readSeq', 'sourceSeq', 'fromObservationSeq', 'toObservationSeq'].includes(name) && item !== null) refs.add(item);
          else if (item && typeof item === 'object') pending.push(item);
        }
      }
      return [...refs];
    }
    const witnesses = (reduced.classification?.models ?? []).flatMap(model => model.rules ?? []).flatMap(rule => {
      const witness = rule.evidence?.witness;
      return witness ? [{rule: rule.rule, witness}] : [];
    });
    const witnessRows = witnesses.map(({rule, witness}) => `<li>${htmlEscape(rule)}<ul>` +
      (witness.steps ?? []).map(step => `<li>${sourceReferences(step.sources).map(localLink).join(' → ')}${htmlDetails('Reduced witness step', step)}</li>`).join('') + '</ul></li>').join('');
    reductionSection = `<section><h2>Source-closed model reduction</h2><p>Status: ${htmlEscape(reduction.status)}. ` +
      `Report recomputed: ${htmlEscape(reductionVerification.valid)}. Refutation verified: ${htmlEscape(reductionVerification.refutationVerified)}. ` +
      `Single-minimality verified: ${htmlEscape(reductionVerification.oneMinimalVerified)}.</p>` +
      `<p>The original bundle and source records remain unchanged. Local witness references below map through the verified original-event sequence.</p><ul>${witnessRows}</ul>` +
      htmlDetails('Transaction selection and original-event sequence', {selectedTransactions: reduced.selectedTransactions,
        removedTransactions: reduced.removedTransactions, originalEventSequence: reduced.originalEventSequence,
        oneMinimal: reduction.oneMinimal, unresolvedCandidates: reduced.unresolvedCandidates}) +
      htmlDetails('Reduction counters', reduced.execution) + '</section>';
  }
  const html = `<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">` +
    `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">` +
    `<title>MoonTxnWitness · ${htmlEscape(data.status)}</title><style>body{font:16px/1.6 system-ui,sans-serif;background:#f4f6f8;color:#182432;margin:0;padding:24px}main{max-width:1400px;margin:auto}section{background:white;padding:20px;margin:18px 0;border:1px solid #dae0e6;border-radius:10px}table{border-collapse:collapse;width:100%}th,td{text-align:left;vertical-align:top;padding:10px;border-bottom:1px solid #ddd}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}summary{cursor:pointer}a{color:#155db1}.scroll{overflow-x:auto}</style></head>` +
    `<body><main><h1>PostgreSQL transaction evidence</h1><section><h2>Verified original window</h2><p>Status: ${htmlEscape(data.status)}. ` +
    `Coverage complete: ${htmlEscape(data.coverageComplete)}. Source authenticated: ${htmlEscape(data.sourceAuthenticated)}.</p>` +
    htmlDetails('Source bindings', {bundleSha256: data.bundleSha256, configSha256: data.configSha256, optionsSha256: data.optionsSha256}) +
    `<p>${htmlEscape(data.scope ?? '')}</p></section><section><h2>Original SQL → actual delivery → version → history</h2><div class="scroll">` +
    `<table><thead><tr><th>History mapping</th><th>Original and executed SQL</th><th>Native and business results</th><th>Version sources</th></tr></thead><tbody>${rows}</tbody></table></div>${lifecycleRows}</section>` +
    `<section><h2>Dependency witness and model</h2><ul>${edgeRows}</ul>` + htmlDetails('Original atomic-row model report', data.model) +
    htmlDetails('Original item-category report', data.itemCategory) + htmlDetails('Independent serial replay', data.serialReplay) + '</section>' +
    reductionSection + '</main></body></html>\n';
  if (Buffer.byteLength(html, 'utf8') > 64 * 1024 * 1024) throw new RangeError('Configured window explanation exceeds 64 MiB');
  return html;
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

  function reduceConfiguredWindowTextV4(bundleText, configText, policyText, optionsText) {
    return JSON.parse(core.reduce_configured_window_v2_json(
      originalText(configText, CONFIGURED_WINDOW_REDUCTION_V4_LIMITS.configBytes, 'Independent SQL configuration'),
      originalText(policyText, CONFIGURED_WINDOW_REDUCTION_V4_LIMITS.policyBytes, 'Independent source policy'),
      originalText(bundleText, CONFIGURED_WINDOW_REDUCTION_V4_LIMITS.bundleBytes, 'Original configured window bundle'),
      originalText(optionsText, CONFIGURED_WINDOW_REDUCTION_V4_LIMITS.optionsBytes, 'Independent reduction options')));
  }

  function verifyConfiguredWindowReductionTextV4(bundleText, report, configText, policyText, optionsText) {
    return JSON.parse(core.verify_configured_window_reduction_v2_json(
      originalText(configText, CONFIGURED_WINDOW_REDUCTION_V4_LIMITS.configBytes, 'Independent SQL configuration'),
      originalText(policyText, CONFIGURED_WINDOW_REDUCTION_V4_LIMITS.policyBytes, 'Independent source policy'),
      originalText(bundleText, CONFIGURED_WINDOW_REDUCTION_V4_LIMITS.bundleBytes, 'Original configured window bundle'),
      jsonText(report, CONFIGURED_WINDOW_REDUCTION_V4_LIMITS.reportBytes, 'Configured window reduction report'),
      originalText(optionsText, CONFIGURED_WINDOW_REDUCTION_V4_LIMITS.optionsBytes, 'Independent reduction options')));
  }

  function reduceConfiguredWindowV4(bundleText, options) {
    const [config, policy, limits] = independentReductionOptions(options);
    return reduceConfiguredWindowTextV4(bundleText, config, policy, limits);
  }

  function verifyConfiguredWindowReductionV4(bundleText, report, options) {
    const [config, policy, limits] = independentReductionOptions(options);
    return verifyConfiguredWindowReductionTextV4(bundleText, report, config, policy, limits);
  }

  function explainConfiguredWindowTextV4(bundleText, report, configText, policyText, optionsText = '{}', extra = {}) {
    object(extra, 'Optional explanation reduction');
    for (const name of Object.keys(extra)) if (!['reduction', 'reductionOptionsText'].includes(name)) throw new TypeError('Unknown explanation option: ' + name);
    const verified = verifyConfiguredWindowTextV4(bundleText, report, configText, policyText, optionsText);
    if (verified.valid !== true) throw new Error('Configured window report does not match original inputs and independent budgets');
    let reduced = null, checked = null;
    if (Object.hasOwn(extra, 'reduction') || Object.hasOwn(extra, 'reductionOptionsText')) {
      if (!Object.hasOwn(extra, 'reduction') || !Object.hasOwn(extra, 'reductionOptionsText')) throw new TypeError('Reduction and independent reduction options are both required');
      checked = verifyConfiguredWindowReductionTextV4(bundleText, extra.reduction, configText, policyText, extra.reductionOptionsText);
      if (checked.valid !== true) throw new Error('Reduction does not match original inputs and independent reduction budgets');
      reduced = JSON.parse(jsonText(extra.reduction, CONFIGURED_WINDOW_REDUCTION_V4_LIMITS.reportBytes, 'Configured window reduction report'));
    }
    return renderConfiguredWindowExplanation(bundleText, verified.recomputed, reduced, checked);
  }

  function explainConfiguredWindowV4(bundleText, report, options, extra = {}) {
    object(extra, 'Optional explanation reduction');
    for (const name of Object.keys(extra)) if (!['reduction', 'reductionOptions'].includes(name)) throw new TypeError('Unknown explanation option: ' + name);
    const verified = verifyConfiguredWindowV4(bundleText, report, options);
    if (verified.valid !== true) throw new Error('Configured window report does not match original inputs and independent budgets');
    let reduced = null, checked = null;
    if (Object.hasOwn(extra, 'reduction') || Object.hasOwn(extra, 'reductionOptions')) {
      if (!Object.hasOwn(extra, 'reduction') || !Object.hasOwn(extra, 'reductionOptions')) throw new TypeError('Reduction and independent reduction options are both required');
      checked = verifyConfiguredWindowReductionV4(bundleText, extra.reduction, extra.reductionOptions);
      if (checked.valid !== true) throw new Error('Reduction does not match original inputs and independent reduction budgets');
      reduced = JSON.parse(jsonText(extra.reduction, CONFIGURED_WINDOW_REDUCTION_V4_LIMITS.reportBytes, 'Configured window reduction report'));
    }
    return renderConfiguredWindowExplanation(bundleText, verified.recomputed, reduced, checked);
  }

  return {analyzeConfiguredWindowV4, verifyConfiguredWindowV4,
    analyzeConfiguredWindowTextV4, verifyConfiguredWindowTextV4,
    reduceConfiguredWindowV4, verifyConfiguredWindowReductionV4,
    reduceConfiguredWindowTextV4, verifyConfiguredWindowReductionTextV4,
    explainConfiguredWindowV4, explainConfiguredWindowTextV4};
}
