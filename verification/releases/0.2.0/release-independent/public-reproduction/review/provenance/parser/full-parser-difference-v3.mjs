import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
const [work,out]=process.argv.slice(2);
assert.ok(work&&out);
const sha=x=>createHash('sha256').update(x).digest('hex');
const before=await import(pathToFileURL(resolve(out,'baseline-runtime/core.mjs')));
const after=await import(pathToFileURL(resolve(out,'actual-isolated-runtime/core.mjs')));
const {fixtures}=await import(pathToFileURL(resolve(work,'scripts/benchmark-fixtures.mjs')));
const baseline=JSON.parse(readFileSync(resolve(out,'baseline-runtime/build-manifest.json'),'utf8'));
const candidate=JSON.parse(readFileSync(resolve(out,'actual-isolated-runtime/build-manifest.json'),'utf8'));
assert.equal(baseline.coreSha256,sha(readFileSync(resolve(out,'baseline-runtime/core.mjs'))));
assert.equal(candidate.coreSha256,sha(readFileSync(resolve(out,'actual-isolated-runtime/core.mjs'))));
let seed=0xA10C5EED,checked=0,valid=0,invalid=0;
const cases=[];
const typedJson=value=>JSON.stringify(logicalHistory(value),(_key,item)=>typeof item==='bigint'?{'$moonbitInt64':item.toString()}:item);
function fields(value,names){assert.deepEqual(Object.keys(value).sort(),names.slice().sort());}
function mapContents(map,valueCheck){
  const entries=map.entries.filter(item=>item!==undefined);
  assert.equal(entries.length,map.size,'Every occupied map entry is represented');
  const seen=new Set();
  const logical=entries.map(item=>{assert.equal(typeof item.key,'string');assert.equal(seen.has(item.key),false);seen.add(item.key);valueCheck(item.value);return[item.key,item.value];});
  return logical.sort((a,b)=>a[0]<b[0]?-1:a[0]>b[0]?1:0);
}
function logicalHistory(h){
  fields(h,['model','initial','version_orders','transactions']);
  const string=value=>assert.equal(typeof value,'string');
  const option=value=>{if(value===undefined)return {'$optionNone':true};assert.equal(typeof value,'bigint');return value;};
  return {model:h.model,initial:mapContents(h.initial,string),
    version_orders:mapContents(h.version_orders,values=>{assert.ok(Array.isArray(values));values.forEach(string);}),
    transactions:h.transactions.map(t=>{
      fields(t,['id','status','ops','start','end']);string(t.id);
      return {id:t.id,status:t.status,ops:t.ops.map(op=>{fields(op,['kind','key','version']);string(op.key);string(op.version);return {kind:op.kind,key:op.key,version:op.version};}),start:option(t.start),end:option(t.end)};
    })};
}
const random=n=>{seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return(seed>>>0)%n;};
function check(text,requiredFast=false){
  const beforeFlags=before.benchmark_parser_agreement(text);
  const afterFlags=after.benchmark_parser_agreement(text);
  try{
    assert.equal(afterFlags,beforeFlags,'Full parser agreement flags differ');
    const flags=JSON.parse(afterFlags);
    assert.equal(flags.agrees,true);
    if(requiredFast)assert.equal(flags.fastPath,true);
    let original,candidateOutput,kind;
    if(flags.referenceValid){
      original=typedJson(before.benchmark_parse(text));
      candidateOutput=typedJson(after.benchmark_parse_balanced(text));
      const baselineFast=typedJson(before.benchmark_parse_balanced(text));
      assert.equal(baselineFast,original,'Existing baseline fast parser differs from legacy typed payload');
      assert.equal(candidateOutput,original,'Complete typed History payload differs');
      valid++;kind='complete-typed-history';
    }else{
      original=before.analyze_json(text);
      candidateOutput=after.analyze_json(text);
      assert.equal(candidateOutput,original,'Complete invalid-input public error output differs');
      invalid++;kind='complete-public-error';
    }
    cases.push({index:checked,inputSha256:sha(text),inputCodeUnits:text.length,kind,
      flagsSha256:sha(afterFlags),outputSha256:sha(candidateOutput),outputBytes:Buffer.byteLength(candidateOutput)});
    checked++;
  }catch(error){
    writeFileSync(resolve(out,'receipts/full-parser-v3-first-failure.json'),JSON.stringify({index:checked,text,beforeFlags,afterFlags,error:String(error),stack:error.stack},null,2)+'\n',{flag:'wx'});
    throw error;
  }
}
// Exact original fixed corpus, edge cases and 2,500 seeded mutations. No original assertion is weakened.
const corpus=fixtures().map(c=>JSON.stringify(c.history));
for(const text of corpus){check(text,true);check(JSON.stringify(JSON.parse(text),null,2),true);}
const edge=[
  '{"transactions":[],"initial":{},"schemaVersion":1e0,"name":"a\\n\\u0000☃"}',
  '{"initial":{"\\u0078":"v0"},"transactions":[{"ops":[],"status":"unknown","id":"\\ud83d\\ude00","end":null,"start":null}]}',
  '{"initial":{},"transactions":[],"initial":{}}',
  '{"initial":{"x":"v0","\\u0078":"v1"},"transactions":[]}',
  '{"initial":{},"transactions":[{"id":"a","status":"committed","ops":[],"\\u0069d":"b"}]}',
  '{"initial":{},"transactions":[],}', '{"initial":{},"transactions":[,]}',
  '{"initial":{},"transactions":[],"schemaVersion":01}',
  '{"initial":{},"transactions":[{"id":"a","status":"committed","ops":[],"start":null0}]}',
  '{"initial":{},"transactions":[{"id":"a","status":"committed","ops":[],"start":9007199254740992}]}',
  '{"initial":{},"transactions":[],"name":"raw\nnewline"}',
  '['.repeat(70)+'0'+']'.repeat(70),
];
for(const text of edge)check(text);
for(let i=0;i<2500;i++){
  let text=corpus[random(corpus.length)];const p=random(text.length+1);
  const token=['"','\\',',',':','{','}','[',']','0','null','\n','☃'][random(12)];
  text=i%3===0?text.slice(0,p)+text.slice(p+1):i%3===1?text.slice(0,p)+token+text.slice(p):text.slice(0,p)+token+text.slice(p+1);
  check(text);
}
assert.equal(checked,2542);
const receipt={schema:1,passed:true,baseline,candidate,checked,valid,invalid,
  seed:'0xA10C5EED',formalPerformanceMeasured:false,originalAssertionsPreserved:true,
  validationHarnessRevision:3,priorFailuresPreserved:['05-complete-parser-difference.json','06-complete-parser-difference-v2.json'],
  correction:'Serialize every public History/Transaction/Operation field; preserve exact Int64 and option types, array order, and all Map key/value data with size/unique-key checks. Exclude per-module randomized private Map bucket/hash layout. Candidate source, original tests, inputs and original assertions unchanged.',
  method:'Original 2542 inputs; exact serialization of every public typed History field, Map logical contents and tagged Int64 decimal strings for reference-valid input; exact public analysis error bytes for reference-invalid input; exact agreement flags throughout.',
  caveat:'Map bucket/hash metadata is private runtime layout and is not included; every logical map key/value is included. No timing or allocation conclusion is derived from this correctness run.',cases};
writeFileSync(resolve(out,'receipts/full-parser-difference-v3.json'),JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({passed:true,checked,valid,invalid,exactCompleteParserPayload:true,exactCompleteInvalidError:true}));
