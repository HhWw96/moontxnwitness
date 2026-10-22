// Exact original2542 generator, no production imports.
import {fixtures} from './inputs/parser/benchmark-fixtures.mjs';
export function parserCases(){let seed=0xA10C5EED;const cases=[];const push=(text,requiredFast=false)=>cases.push({text,requiredFast});
const random=n=>{seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return(seed>>>0)%n;};
const corpus=fixtures().map(c=>JSON.stringify(c.history));
for(const text of corpus){push(text,true);push(JSON.stringify(JSON.parse(text),null,2),true);}
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
for(const text of edge)push(text);
for(let i=0;i<2500;i++){
  let text=corpus[random(corpus.length)];const p=random(text.length+1);
  const token=['"','\\',',',':','{','}','[',']','0','null','\n','☃'][random(12)];
  text=i%3===0?text.slice(0,p)+text.slice(p+1):i%3===1?text.slice(0,p)+token+text.slice(p):text.slice(0,p)+token+text.slice(p+1);
  push(text);
}

return cases;}
