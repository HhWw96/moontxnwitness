// Replay actual projected buffers/deliveries with independently selected config.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {parseArgs} from 'node:util';
const {values}=parseArgs({options:{core:{type:'string'},capture:{type:'string'},config:{type:'string'},output:{type:'string'},'projection-options':{type:'string'}}});
for(const name of ['core','capture','config','output'])assert(values[name],`--${name} required`);
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const core=resolve(values.core),capture=resolve(values.capture),output=resolve(values.output),configPath=resolve(values.config);
mkdirSync(dirname(output),{recursive:true});
const snapshot=resolve(dirname(output),'projected-result-core.mjs');writeFileSync(snapshot,readFileSync(core));
const api=await import(pathToFileURL(snapshot).href),config=JSON.parse(readFileSync(configPath,'utf8'));
const independentOptions=values['projection-options']?JSON.parse(readFileSync(resolve(values['projection-options']),'utf8')):{};
const raw=readFileSync(resolve(capture,'lifecycle.jsonl')),metadata=JSON.parse(readFileSync(resolve(capture,'instrumentation.json'),'utf8'));
assert(raw.length<=8*1024*1024,'bounded original lifecycle required');
assert.equal(sha(raw),metadata.lifecycle.sha256);assert.equal(metadata.lifecycle.sealed,true);
const lines=raw.toString('utf8').split(/(?<=\n)/u).filter(Boolean),records=lines.map(line=>JSON.parse(line));
records.forEach((record,index)=>assert.equal(record.seq,index+1));
const seal=records.at(-1);assert.equal(seal.kind,'seal');assert.equal(seal.records,records.length-1);
assert.equal(seal.prefixSha256,sha(Buffer.from(lines.slice(0,-1).join(''),'utf8')));
const projections=new Map(),natives=[],deliveries=new Map();
for(const record of records){
 if(!Object.hasOwn(record,'frameText'))continue;
 const value=JSON.parse(record.frameText);
 if(record.kind==='configured-point-projection')projections.set(record.seq,value);
 if(record.kind==='configured-point-native')natives.push(value);
 if(record.kind==='configured-point-delivery'){
  const rows=deliveries.get(value.resultId)||[];rows.push(value);deliveries.set(value.resultId,rows);
 }
}
assert(natives.length>0,'actual captured projected buffers required');
const results=[],noFacts=report=>{for(const name of ['sourceFactsProduced','captureFactsProduced','sourceAuthenticated','catalogVerified','completeWindow','sourceWindowVerified','modelCoverageAccepted','commitVerified','committedWriteEffectVerified','moonbitProjectionVerified','absenceSourceVerified'])assert.equal(report[name],false,name);};
for(const native of natives){
 const execution=projections.get(native.projectionNoteSeq);assert(execution,'original projection reference missing');
 assert.equal(execution.connection,native.connection);assert.equal(execution.cursor,native.cursor);
 const d=execution.descriptor,batches=deliveries.get(native.resultId)||[];
 const report=JSON.parse(api.verify_projected_result_v2_json(JSON.stringify(config),d.originalSql,JSON.stringify(d.originalParameters),JSON.stringify(independentOptions),JSON.stringify(d),JSON.stringify(native),JSON.stringify(batches),'{}'));
 try{assert.equal(report.status,'matched',JSON.stringify(report.gaps));assert.equal(report.valid,true);noFacts(report);
  results.push({resultId:native.resultId,operation:d.candidate.operation,passed:true,checks:report.execution?.checks});
 }catch(error){results.push({resultId:native.resultId,operation:d.candidate.operation,passed:false,error:String(error)});}
}
const result={format:'moontxnwitness-projected-result-actual-replay/v1',passed:results.every(x=>x.passed),tests:results.length,
 coreSha256:sha(readFileSync(core)),configSha256:sha(readFileSync(configPath)),captureLogSha256:sha(raw),
 actualDatabaseExecutedByReplay:false,originalObservedFrames:true,sourceFactsProduced:false,completeWindow:false,modelCoverageAccepted:false,results};
writeFileSync(output,JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify({passed:result.passed,tests:result.tests,output}));
if(!result.passed){console.error(JSON.stringify(results.filter(x=>!x.passed),null,2));process.exitCode=1;}
