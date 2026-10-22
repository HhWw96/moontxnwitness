// Project exactly the root /version JSON string span after strict metadata checks.
// Every other character, including all business values named version, is retained.
import assert from 'node:assert/strict';
export function projectEngineHeader(text,expectedVersion){
  assert.ok(expectedVersion==='0.1.7'||expectedVersion==='0.1.8');
  assert.equal(typeof text,'string');const parsed=JSON.parse(text);
  assert.ok(parsed&&typeof parsed==='object'&&!Array.isArray(parsed));
  assert.equal(parsed.tool,'MoonTxnWitness');assert.equal(parsed.schemaVersion,2);
  assert.equal(parsed.algorithm,'bounded-register-v2.1');assert.equal(parsed.version,expectedVersion);
  let i=0,span=null,depth=0;const white=()=>{while(/[\x20\t\r\n]/.test(text[i]??'!'))i++;};
  function stringToken(){const start=i;assert.equal(text[i++],'"');while(i<text.length){const c=text[i++];if(c==='"')return{start,end:i,raw:text.slice(start,i),decoded:JSON.parse(text.slice(start,i))};if(c==='\\'){assert.ok(i<text.length);i++;}}throw Error('Unterminated JSON string');}
  function value(path){white();const start=i,c=text[i];if(c==='{'){
    assert.ok(++depth<=128);i++;white();const keys=new Set();if(text[i]==='}'){i++;depth--;return;}
    for(;;){white();const key=stringToken();assert.equal(keys.has(key.decoded),false,'Duplicate JSON key');keys.add(key.decoded);white();assert.equal(text[i++],':');white();const childStart=i;value([...path,key.decoded]);if(path.length===0&&key.decoded==='version'){assert.equal(key.raw,'"version"');assert.equal(span,null);span={start:childStart,end:i};}white();if(text[i]==='}'){i++;depth--;return;}assert.equal(text[i++],',');}
  }else if(c==='['){assert.ok(++depth<=128);i++;white();if(text[i]===']'){i++;depth--;return;}let n=0;for(;;){value([...path,n++]);white();if(text[i]===']'){i++;depth--;return;}assert.equal(text[i++],',');}}
  else if(c==='"')stringToken();else{while(i<text.length&&!/[\x20\t\r\n,}\]]/.test(text[i]))i++;assert.ok(i>start);}}
  value([]);white();assert.equal(i,text.length);assert.ok(span);assert.equal(text.slice(span.start,span.end),JSON.stringify(expectedVersion));
  const projectedText=text.slice(0,span.start)+'"__ENGINE_METADATA_VERSION__"'+text.slice(span.end);
  return{projectedText,engineVersion:expectedVersion,projectedPath:'/version',rawValueStart:span.start,rawValueEnd:span.end,otherCharactersPreserved:true};
}
