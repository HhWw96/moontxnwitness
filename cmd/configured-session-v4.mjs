// Unified diagnostic facade. Model facts and writer-window claims are disabled.
import {createHash} from 'node:crypto';
const digest=value=>createHash('sha256').update(value).digest('hex');
const names=['diagnose_configured_session_v4_json','verify_configured_session_diagnostic_v4_json','configured_session_options_v4_json','configured_session_bundle_v4_json'];
export const CONFIGURED_SESSION_LIMITS=Object.freeze({configBytes:262144,lifecycleBytes:8388608,diagnosticTraceBytes:8388608,sourceInputsBytes:12582912,bundleBytes:33554432,optionsBytes:8192,reportBytes:67108864});
function text(value,limit,label){const result=typeof value==='string'?value:JSON.stringify(value,(_key,item)=>{if(typeof item==='number'&&!Number.isSafeInteger(item))throw new TypeError('Use original JSON text for exact numeric input');return item;});if(typeof result!=='string'||!result.isWellFormed()||Buffer.byteLength(result,'utf8')>limit)throw new TypeError(label+' exceeds its text contract');return result;}
const forbidden=['sourceFactsProduced','writerWindowVerified','sourceAuthenticated','serverInstanceIdentityAuthenticated','isolationModelChecked','isolationAnalysisReady'];
function report(raw){if(typeof raw!=='string'||Buffer.byteLength(raw,'utf8')>CONFIGURED_SESSION_LIMITS.reportBytes)throw new TypeError('Invalid configured session response');const value=JSON.parse(raw);if(value.format!=='moontxnwitness-configured-session-diagnostic/v4')throw new TypeError('Unsupported configured session report');for(const name of forbidden)if(value[name]!==false)throw new TypeError('Diagnostic namespace cannot authorize '+name);return value;}
export function createConfiguredSessionV4(core){
 for(const name of names)if(typeof core[name]!=='function')throw new TypeError('Missing configured session core entry '+name);
 const options=value=>{const raw=text(value??{},8192,'caller options');const checked=JSON.parse(core.configured_session_options_v4_json(raw));if(checked.valid!==true)throw new TypeError(checked.error||'Invalid configured session options');return JSON.stringify(checked.options);};
 const input=value=>{const raw=text(value,33554432,'session input');const checked=JSON.parse(core.configured_session_bundle_v4_json(raw));if(checked.valid!==true)throw new TypeError(checked.error||'Invalid session input');const v=checked.input;if(typeof v.lifecycleText!=='string'||typeof v.configText!=='string'||typeof v.diagnosticTraceText!=='string'||typeof v.sourceInputsText!=='string')throw new TypeError('Original session inputs must remain text');return [text(v.configText,262144,'configuration'),text(v.lifecycleText,8388608,'lifecycle'),text(v.diagnosticTraceText,8388608,'diagnostic trace'),text(v.sourceInputsText,12582912,'source inputs')];};
 return Object.freeze({
  diagnoseConfiguredSessionTextV4(value,callerOptions={}){const raw=core.diagnose_configured_session_v4_json(...input(value),options(callerOptions));report(raw);return raw;},
  diagnoseConfiguredSessionV4(value,callerOptions={}){return report(core.diagnose_configured_session_v4_json(...input(value),options(callerOptions)));},
  verifyConfiguredSessionV4(value,suppliedReport,expectedOptions={}){return core.verify_configured_session_diagnostic_v4_json(...input(value),text(suppliedReport,67108864,'report'),options(expectedOptions))===true;},
  normalizeConfiguredSessionOptionsV4(value={}){return JSON.parse(options(value));},
  makeConfiguredSessionCapsuleV4(value,callerOptions={}){
   const inputText=text(value,33554432,'session input'),optionsText=options(callerOptions);
   const reportText=core.diagnose_configured_session_v4_json(...input(inputText),optionsText);
   report(reportText);
   const capsule={format:'moontxnwitness-configured-session-capsule/v1',scope:'diagnostic-only',
    inputText,optionsText,reportText,inputSha256:digest(inputText),reportSha256:digest(reportText)};
   return text(capsule,134217728,'configured session capsule')+'\n';
  },
  replayConfiguredSessionCapsuleV4(capsuleText,expectedOptions={}){
   const reject=reason=>({valid:false,reason,sourceFactsProduced:false,writerWindowVerified:false,
    sourceAuthenticated:false,isolationModelChecked:false,isolationAnalysisReady:false});
   try{
    if(typeof capsuleText!=='string')return reject('original-capsule-text-required');
    text(capsuleText,134217728,'configured session capsule');
    const v=JSON.parse(capsuleText);
    if(!v||v.format!=='moontxnwitness-configured-session-capsule/v1'||v.scope!=='diagnostic-only'||
     typeof v.inputText!=='string'||typeof v.optionsText!=='string'||typeof v.reportText!=='string')return reject('unsupported-capsule');
    const expected={format:v.format,scope:v.scope,inputText:v.inputText,optionsText:v.optionsText,
     reportText:v.reportText,inputSha256:digest(v.inputText),reportSha256:digest(v.reportText)};
    if(JSON.stringify(expected)+'\n'!==capsuleText)return reject('capsule-envelope-or-digest-mismatch');
    if(options(expectedOptions)!==v.optionsText)return reject('independent-caller-options-differ');
    input(v.inputText);report(v.reportText);
    if(core.verify_configured_session_diagnostic_v4_json(...input(v.inputText),v.reportText,options(expectedOptions))!==true)return reject('diagnostic-does-not-reproduce');
    return {valid:true,status:'recomputed-diagnostic',inputSha256:expected.inputSha256,
     reportSha256:expected.reportSha256,diagnostic:report(v.reportText),sourceFactsProduced:false,
     writerWindowVerified:false,sourceAuthenticated:false,isolationModelChecked:false,isolationAnalysisReady:false};
   }catch{return reject('invalid-capsule-or-caller-options');}
  }
 });
}
