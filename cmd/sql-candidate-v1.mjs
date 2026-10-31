// Independent MoonBit grammar/binding checks. This module starts no driver or worker.
import {normalize_configured_sql_v1_json,verify_configured_sql_v1_json,normalize_sql_config_v1_json,compare_c_text_v1} from './sql-projection-core.mjs';
const MiB=1024*1024;
export const SQL_CANDIDATE_V1_LIMITS=Object.freeze({configBytes:262144,sqlBytes:1048576,parameterBytes:MiB,candidateBytes:8*MiB,optionsBytes:8192,reportBytes:32*MiB});
function text(value,maximum,label){
 const raw=typeof value==='string'?value:JSON.stringify(value);
 if(typeof raw!=='string'||Buffer.byteLength(raw,'utf8')>maximum)throw new TypeError(label+' is missing or oversized');
 if(Buffer.from(raw,'utf8').toString('utf8')!==raw)throw new TypeError(label+' contains malformed Unicode');
 return raw;
}
function parameterText(parameters){
 if(typeof parameters!=='string'&&parameters!==null){
  if(!Array.isArray(parameters)&&(!parameters||typeof parameters!=='object'||![Object.prototype,null].includes(Object.getPrototypeOf(parameters))))throw new TypeError('Materialized parameter array/plain object or raw JSON required');
  for(const value of Object.values(parameters))if(!['string','boolean'].includes(typeof value)&&!(typeof value==='number'&&Number.isSafeInteger(value)))throw new TypeError('Exact scalar parameters required; use raw JSON text for int64 outside the JavaScript safe range');
 }
 return text(parameters,SQL_CANDIDATE_V1_LIMITS.parameterBytes,'parameters');
}
function optionText(options){
 if(typeof options!=='string'){
  if(options===null||typeof options!=='object'||Array.isArray(options)||![Object.prototype,null].includes(Object.getPrototypeOf(options)))throw new TypeError('Plain options object or raw JSON required');
  const caps={maxChecks:1000000,maxTokens:32768,maxSqlBytes:1048576};
  for(const [name,value]of Object.entries(options))if(!Object.hasOwn(caps,name)||!Number.isSafeInteger(value)||value<0||value>caps[name])throw new TypeError('Unknown or invalid independent option: '+name);
 }
 return text(options,8192,'options');
}
function inputs(config,sql,parameters,options){
 if(typeof sql!=='string')throw new TypeError('Original SQL text required');
 return [text(config,SQL_CANDIDATE_V1_LIMITS.configBytes,'config'),text(sql,SQL_CANDIDATE_V1_LIMITS.sqlBytes,'SQL'),parameterText(parameters),optionText(options)];
}
function result(raw){return JSON.parse(text(raw,SQL_CANDIDATE_V1_LIMITS.reportBytes,'report'));}
export function normalizeSQLConfigV1(config){return result(normalize_sql_config_v1_json(text(config,262144,'config')));}
/** Exact int64 parameters must be supplied as raw JSON text from the observer. */
export function normalizeSQLCandidateV1(config,sql,parameters='null',options={}){return result(normalize_configured_sql_v1_json(...inputs(config,sql,parameters,options)));}
export function verifySQLCandidateV1(config,sql,parameters,candidate,options={}){
 try{const [c,s,p,o]=inputs(config,sql,parameters,options);return result(verify_configured_sql_v1_json(c,s,p,text(candidate,8*MiB,'candidate'),o));}
 catch(error){return {valid:false,status:'invalid',captureFactsProduced:false,sourceAuthenticated:false,gaps:[error.message]};}
}
/** Mathematical UTF-8-C candidate comparator; catalog/encoding/database proof is separate. */
export function compareConfiguredCTextV1(a,b){return compare_c_text_v1(text(a,MiB,'text'),text(b,MiB,'text'));}
