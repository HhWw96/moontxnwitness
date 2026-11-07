// Offline presentation only. The SDK supplies the independent MoonBit verifier.
const escape = value => String(value).replace(/[&<>"']/g, c => ({
  '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;',
}[c]));
const json = value => escape(JSON.stringify(value, null, 2));
const details = (title, value) => `<details><summary>${escape(title)}</summary><pre>${json(value)}</pre></details>`;

export function createPointWindowExplanationV4(verify) {
  return function explain(before, after, session, report, options = {}) {
    // Verify before reading any presentation field. Caller limits are not taken
    // from the report. A valid unknown report remains unknown in the view.
    if (verify(before, after, session, report, options)?.valid !== true) {
      throw new Error('Point-window report does not match the original inputs and caller budgets');
    }
    const parse = value => typeof value === 'string' ? JSON.parse(value) : value;
    const data = parse(report), envelope = parse(session);
    if (data.format !== 'moontxnwitness-configured-point-window/v4') {
      throw new Error('Unsupported point-window report');
    }
    const trace = JSON.parse(envelope.diagnosticTraceText);
    const events = trace.events;
    const statements = new Map(events.filter(e => e.kind === 'statement').map(e => [e.seq, e]));
    const rows = (data.operationSources ?? []).map(source => {
      const statement = statements.get(source.originalStatementSeq);
      if (!statement) throw new Error('Original statement reference is missing');
      const delivered = events.filter(e => e.kind === 'rows' && e.statement === statement.seq);
      return `<tr><td>${escape(source.historySeq)}</td><td>${escape(statement.seq)}</td>` +
        `<td>${escape(statement.tx)}</td><td><pre>${escape(statement.sql)}</pre>` +
        details('Parameters', statement.parameters) + details('Actual delivery', delivered) + '</td>' +
        `<td>${escape(source.sourceVersion)}${details('Original source references', source)}</td></tr>`;
    }).join('');
    return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>MoonTxnWitness · ${escape(data.status)}</title>
<style>body{font:16px/1.6 system-ui,sans-serif;color:#182432;background:#f4f6f8;margin:0;padding:28px}main{max-width:1200px;margin:auto}section{background:white;border:1px solid #dae0e6;border-radius:12px;padding:22px;margin:18px 0}h1,h2{line-height:1.3}h2{font-size:21px}pre,code{font:13px/1.5 ui-monospace,monospace;white-space:pre-wrap;overflow-wrap:anywhere}table{border-collapse:collapse;width:100%}th,td{text-align:left;vertical-align:top;border-bottom:1px solid #dae0e6;padding:10px;overflow-wrap:anywhere}summary{cursor:pointer;font-weight:600;margin:8px 0}.scroll{overflow-x:auto}.status{display:inline-block;border-radius:6px;background:#e7eef6;padding:4px 12px}dt{font-weight:600}dd{margin:0 0 8px;overflow-wrap:anywhere}</style></head>
<body><main><h1>PostgreSQL transaction evidence</h1>
<p class="status">${escape(data.status)}</p><p>${escape(data.scope ?? data.reason ?? '')}</p>
<section><h2>Recomputed report</h2><p>Coverage complete: ${escape(data.coverageComplete)}. Source authenticated: ${escape(data.sourceAuthenticated)}.</p>
<dl><dt>Start SHA-256</dt><dd>${escape(data.startSha256)}</dd><dt>End SHA-256</dt><dd>${escape(data.endSha256)}</dd><dt>Session SHA-256</dt><dd>${escape(data.sessionSha256)}</dd><dt>Options SHA-256</dt><dd>${escape(data.optionsSha256)}</dd></dl>
${details('Caller budgets', parse(options))}${data.reason ? details('Coverage reason', data.reason) : ''}</section>
<section><h2>SQL → delivery → version → history</h2><div class="scroll"><table><thead><tr><th>History event</th><th>Original statement</th><th>Transaction</th><th>SQL and actual delivery</th><th>Version and source</th></tr></thead><tbody>${rows}</tbody></table></div></section>
<section><h2>Model and anomaly evidence</h2>${details('Serializable model', data.model ?? null)}${details('G2-item', data.itemCategory ?? null)}${details('Verified relation history', data.history ?? null)}</section>
</main></body></html>\n`;
  };
}
