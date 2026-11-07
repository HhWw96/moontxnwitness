// Default SDK shares the main MoonBit instance. Standalone entries remain separate.
import * as core from './core.mjs';
import {createHash} from 'node:crypto';
import {createPointWindowExplanationV4} from './point-window-explanation-v4.mjs';
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

export const explainConfiguredPointWindowV4 = createPointWindowExplanationV4(verifyConfiguredPointWindowV4);

const pointCapsuleFormat='moontxnwitness-configured-point-capsule/v1';
const pointHash=text=>createHash('sha256').update(text,'utf8').digest('hex');
const pointCapsuleFields=['format','beforeText','afterText','sessionText','reportText','optionsText',
 'beforeSha256','afterSha256','sessionSha256','reportSha256','optionsSha256'];

export function makeConfiguredPointWindowCapsuleV4(before,after,session,options={}) {
 const [beforeText,afterText,sessionText]=pointInputs(before,after,session);
 const optionsText=boundedText(options,8192,'Point window options');
 const reportText=core.analyze_configured_point_window_v4_json(beforeText,afterText,sessionText,optionsText);
 const capsule={format:pointCapsuleFormat,beforeText,afterText,sessionText,reportText,optionsText};
 for(const name of ['before','after','session','report','options'])capsule[name+'Sha256']=pointHash(capsule[name+'Text']);
 return boundedText(capsule,64*1024*1024,'Point window capsule');
}

export function replayConfiguredPointWindowCapsuleV4(capsule,options={}) {
 try {
  const value=JSON.parse(boundedText(capsule,64*1024*1024,'Point window capsule'));
  if(!value||value.format!==pointCapsuleFormat||Object.keys(value).length!==pointCapsuleFields.length
    ||pointCapsuleFields.some(name=>!Object.hasOwn(value,name)))throw Error('envelope');
  for(const name of ['before','after','session','report','options']) {
   if(typeof value[name+'Text']!=='string'||pointHash(value[name+'Text'])!==value[name+'Sha256'])throw Error('digest');
  }
  // Capsule options describe the original run; they cannot authorize a replay.
  const caller=boundedText(options,8192,'Point window options');
  if(value.optionsText!==caller)throw Error('caller-options');
  if(!verifyConfiguredPointWindowV4(value.beforeText,value.afterText,value.sessionText,value.reportText,caller).valid)throw Error('report');
  return {valid:true,sourceAuthenticated:false,report:JSON.parse(value.reportText)};
 } catch {
  return {valid:false,sourceAuthenticated:false,reason:'invalid-point-capsule-or-caller-options'};
 }
}
