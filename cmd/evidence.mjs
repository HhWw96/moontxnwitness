import {routeLegacyV028} from './legacy-v028-dispatch.mjs';
import { createHash } from 'node:crypto';
import { capsule_content_json, replay_report_json, version, capsule_v3_content_json, analyze_v3_json, verify_v3_json } from './core.mjs';

function hash(text) { return createHash('sha256').update(text, 'utf8').digest('hex'); }

export function makeCapsule(historyText, report) {
  const schemaVersion = report.schemaVersion === 2 ? 2 : 1;
  const reportText = JSON.stringify(report);
  const text = JSON.stringify({ format: 'moontxnwitness-replay/v' + schemaVersion, schemaVersion, tool: 'MoonTxnWitness', engineVersion: version(), historyText, historySha256: hash(historyText), reportText, reportSha256: hash(reportText) }, null, 2) + '\n';
  if (Buffer.byteLength(text) > 32 * 1024 * 1024) throw new Error('复现包超过 32 MiB 限制');
  return text;
}

export function replayCapsule(text) {
  const legacy028=routeLegacyV028('replay-v1v2',[text],version());if(legacy028.matched)return legacy028.result;
  const content = JSON.parse(capsule_content_json(text));
  if (!content.valid) return content;
  if (hash(content.historyText) !== content.historySha256 || hash(content.reportText) !== content.reportSha256) return { valid: false, reason: '复现包内容的 SHA-256 不匹配' };
  return JSON.parse(replay_report_json(content.historyText, content.reportText));
}

// v3 keeps collection facts, normalization and judgment in separate bound texts.
export function makeCapsuleV3(trace, report) {
  const traceText = typeof trace === 'string' ? trace : JSON.stringify(trace);
  if (Buffer.byteLength(traceText, 'utf8') > 8 * 1024 * 1024) throw new RangeError('v3 capture exceeds 8 MiB UTF-8');
  report ??= JSON.parse(analyze_v3_json(traceText, '{}'));
  const reportText = typeof report === 'string' ? report : JSON.stringify(report);
  const checked = JSON.parse(verify_v3_json(traceText, reportText));
  if (!checked.valid) throw new Error('Cannot package a v3 report that does not reproduce');
  const parsed = JSON.parse(reportText);
  const normalizedText = JSON.stringify(parsed.normalized);
  const evidenceText = JSON.stringify(parsed.evidence);
  const content = {format:'moontxnwitness-replay/v3',schemaVersion:3,tool:'MoonTxnWitness',engineVersion:parsed.version,traceText,normalizedText,reportText,evidenceText};
  for (const key of ['trace','normalized','report','evidence']) content[key + 'Sha256'] = hash(content[key + 'Text']);
  const text = JSON.stringify(content, null, 2) + '\n';
  if (Buffer.byteLength(text) > 32 * 1024 * 1024) throw new Error('v3 capsule exceeds 32 MiB');
  return text;
}

export function replayCapsuleV3(text) {
  if (Buffer.byteLength(text, 'utf8') > 32 * 1024 * 1024) return {valid:false,reason:'v3 capsule exceeds 32 MiB UTF-8'};
  const legacy028=routeLegacyV028('replay-v3',[text],version());if(legacy028.matched)return legacy028.result;
  const parsed = JSON.parse(capsule_v3_content_json(text));
  if (!parsed.valid) return parsed;
  const content = parsed.content;
  for (const key of ['trace','normalized','report','evidence']) {
    if (hash(content[key + 'Text']) !== content[key + 'Sha256']) return {valid:false,reason:`v3 ${key} digest mismatch`};
  }
  const result = JSON.parse(verify_v3_json(content.traceText, content.reportText));
  if (!result.valid) return result;
  const report = JSON.parse(content.reportText);
  // Compare text emitted by our canonical producer after semantic verification.
  if (JSON.stringify(report.normalized) !== content.normalizedText || JSON.stringify(report.evidence) !== content.evidenceText) return {valid:false,reason:'v3 normalized facts or evidence differ from verified report'};
  return {...result,status:report.status,coverageComplete:report.coverage.complete};
}
