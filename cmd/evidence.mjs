import { createHash } from 'node:crypto';
import { capsule_content_json, replay_report_json, version } from './core.mjs';

function hash(text) { return createHash('sha256').update(text, 'utf8').digest('hex'); }

export function makeCapsule(historyText, report) {
  const schemaVersion = report.schemaVersion === 2 ? 2 : 1;
  const reportText = JSON.stringify(report);
  const text = JSON.stringify({ format: 'moontxnwitness-replay/v' + schemaVersion, schemaVersion, tool: 'MoonTxnWitness', engineVersion: version(), historyText, historySha256: hash(historyText), reportText, reportSha256: hash(reportText) }, null, 2) + '\n';
  if (Buffer.byteLength(text) > 32 * 1024 * 1024) throw new Error('复现包超过 32 MiB 限制');
  return text;
}

export function replayCapsule(text) {
  const content = JSON.parse(capsule_content_json(text));
  if (!content.valid) return content;
  if (hash(content.historyText) !== content.historySha256 || hash(content.reportText) !== content.reportSha256) return { valid: false, reason: '复现包内容的 SHA-256 不匹配' };
  return JSON.parse(replay_report_json(content.historyText, content.reportText));
}
