// Equality control only. Never used inside measured calls.
import assert from 'node:assert/strict';
const marker='<product-version-only>';
function header(schema,version){assert(Number.isInteger(schema));return '{"schemaVersion":'+schema+',"tool":"MoonTxnWitness","version":'+JSON.stringify(version);}
function reportEnd(text,start){let depth=0,inString=false,escape=false;assert.equal(text[start],'{');for(let i=start;i<text.length;i++){const c=text[i];if(inString){if(escape)escape=false;else if(c==='\\')escape=true;else if(c==='"')inString=false;continue;}if(c==='"')inString=true;else if(c==='{'||c==='[')depth++;else if(c==='}'||c===']'){depth--;if(depth===0)return i+1;}}throw new Error('Missing report boundary');}
function rootReport(text,schema,version){const original=header(schema,version);assert(text.startsWith(original),'Unexpected report metadata location or bytes');assert(',}'.includes(text[original.length]));return header(schema,marker)+text.slice(original.length);}
export function normalizeProductMetadataOnly(raw,{entry,format,version}){
 const decoded=JSON.parse(raw),report=entry.startsWith('run_')?decoded.report:decoded;assert.equal(report.version,version);
 if(!entry.startsWith('run_'))return rootReport(raw,report.schemaVersion,version);
 assert.deepEqual(Object.keys(decoded),['report','output','exitCode']);assert.equal(typeof decoded.output,'string');
 const outer='{"report":';assert(raw.startsWith(outer));const end=reportEnd(raw,outer.length),body=raw.slice(outer.length,end);assert.deepEqual(JSON.parse(body),report);
 let suffix=raw.slice(end);
 if(format==='json'){assert(decoded.output.endsWith('\n'));assert.deepEqual(JSON.parse(decoded.output),report);}
 if(format!=='dot'){
  const oldPrefix=format==='json'?header(report.schemaVersion,version):(format==='markdown'?'# ':'')+'MoonTxnWitness v'+version+'\n';
  const newPrefix=format==='json'?header(report.schemaVersion,marker):(format==='markdown'?'# ':'')+'MoonTxnWitness v'+marker+'\n';
  assert(decoded.output.startsWith(oldPrefix),'Unexpected presentation metadata location');
  const oldEncoded=',"output":"'+JSON.stringify(oldPrefix).slice(1,-1),newEncoded=',"output":"'+JSON.stringify(newPrefix).slice(1,-1);
  assert(suffix.startsWith(oldEncoded),'Unexpected encoded presentation metadata location or bytes');suffix=newEncoded+suffix.slice(oldEncoded.length);
 }
 return outer+rootReport(body,report.schemaVersion,version)+suffix;
}
