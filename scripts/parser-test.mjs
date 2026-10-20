// Differentially check the typed fast path against the legacy official JSON decoder.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {fixtures} from './benchmark-fixtures.mjs';
import {benchmark_parser_agreement,version} from '../dist/core.mjs';
import {root} from './moon.mjs';
import {writeVerifiedJson} from './performance-evidence.mjs';
export function runParserTests(){
  let seed=0xA10C5EED,checked=0,fastValid=0,referenceInvalid=0;
  const random=n=>{seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return(seed>>>0)%n;};
  function check(text,requiredFast=false){const r=JSON.parse(benchmark_parser_agreement(text));assert.equal(r.agrees,true,`Parser disagreement: ${text.slice(0,300)}`);if(requiredFast)assert.equal(r.fastPath,true);checked++;if(r.fastPath&&r.referenceValid)fastValid++;if(!r.referenceValid)referenceInvalid++;}
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
  ];for(const text of edge)check(text);
  for(let i=0;i<2500;i++){
    let text=corpus[random(corpus.length)];const p=random(text.length+1);
    const token=['"','\\',',',':','{','}','[',']','0','null','\n','☃'][random(12)];
    text=i%3===0?text.slice(0,p)+text.slice(p+1):i%3===1?text.slice(0,p)+token+text.slice(p):text.slice(0,p)+token+text.slice(p+1);
    check(text);
  }
  const receipt={tool:'MoonTxnWitness',version:version(),passed:true,seed:'0xA10C5EED',checked,fastValid,referenceInvalid,method:'Schema-directed parser versus legacy duplicate/depth guard plus official JSON decoder; malformed/Unicode/duplicate/numeric mutations'};
  writeVerifiedJson(resolve(root,'verification/parser.json'),receipt);console.log(`Parser differential: ${checked} inputs agree; ${referenceInvalid} malformed inputs rejected by reference.`);return receipt;
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url))runParserTests();
