// Default SDK shares the main MoonBit instance. Standalone entries remain separate.
import * as core from './core.mjs';
import {createConfiguredSessionV4} from './configured-session-v4.mjs';
import {createSourceComponentsV4} from './source-components-v4.mjs';
import {createSQLCandidateV1} from './sql-candidate-host-v1.mjs';
import {createSQLFetchV1} from './sql-fetch-host-v1.mjs';
export const {diagnoseConfiguredSessionTextV4,diagnoseConfiguredSessionV4,verifyConfiguredSessionV4,
 normalizeConfiguredSessionOptionsV4,makeConfiguredSessionCapsuleV4,replayConfiguredSessionCapsuleV4}=createConfiguredSessionV4(core);
export const {verifySourceInstallationV4,verifySourceInstallationReportV4,mapInitialSourceFetchV4,
 verifyInitialSourceFetchReportV4}=createSourceComponentsV4(core);
export const {normalizeSQLConfigV1,normalizeSQLCandidateV1,verifySQLCandidateV1,compareConfiguredCTextV1}=createSQLCandidateV1(core);
export const {verifyConfiguredFetchV1}=createSQLFetchV1(core);
export {CONFIGURED_SESSION_LIMITS} from './configured-session-v4.mjs';

function boundedText(value, maximum, label) {
  const text = typeof value === 'string' ? value : JSON.stringify(value);
  if (typeof text !== 'string' || !text.isWellFormed() || Buffer.byteLength(text) > maximum) {
    throw new TypeError(label + ' exceeds its text contract');
  }
  return text;
}

export function verifyConfiguredEffectsSnapshotV4(input, options = {}) {
  const source = boundedText(input, 24 * 1024 * 1024, 'Original effects snapshot');
  const limits = boundedText(options, 8192, 'Effects snapshot options');
  return JSON.parse(core.verify_configured_effects_snapshot_v4_json(source, limits));
}

export function verifyConfiguredWriterBindingsV4(effects, session, options = {}) {
  const source = boundedText(effects, 24 * 1024 * 1024, 'Original effects snapshot');
  const trace = boundedText(session, 32 * 1024 * 1024, 'Original configured session');
  const limits = boundedText(options, 8192, 'Writer binding options');
  return JSON.parse(core.verify_configured_writer_bindings_v4_json(source, trace, limits));
}

export function verifyConfiguredWriterWindowV4(before, after, session, options = {}) {
  const start = boundedText(before, 24 * 1024 * 1024, 'Original start snapshot');
  const end = boundedText(after, 24 * 1024 * 1024, 'Original end snapshot');
  const trace = boundedText(session, 32 * 1024 * 1024, 'Original configured session');
  const limits = boundedText(options, 8192, 'Writer window options');
  return JSON.parse(core.verify_configured_writer_window_v4_json(start, end, trace, limits));
}

function pointInputs(before, after, session) {
  return [
    boundedText(before, 24 * 1024 * 1024, 'Original start snapshot'),
    boundedText(after, 24 * 1024 * 1024, 'Original end snapshot'),
    boundedText(session, 32 * 1024 * 1024, 'Original configured session'),
  ];
}

export function analyzeConfiguredPointWindowV4(before, after, session, options = {}) {
  return JSON.parse(core.analyze_configured_point_window_v4_json(
    ...pointInputs(before, after, session), boundedText(options, 8192, 'Point window options')));
}

export function verifyConfiguredPointWindowV4(before, after, session, report, options = {}) {
  return {valid: core.verify_configured_point_window_v4_json(
    ...pointInputs(before, after, session), boundedText(report, 32 * 1024 * 1024, 'Point window report'),
    boundedText(options, 8192, 'Point window options'))};
}
