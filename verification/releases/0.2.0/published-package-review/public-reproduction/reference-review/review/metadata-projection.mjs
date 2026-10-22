// Fixed engine-header spans only. No parsed object is reserialized for comparison.
import assert from 'node:assert/strict';
export function projectMetadata(text,version,profile){
 assert.ok(['0.1.5','0.1.7','0.1.8','0.2.0'].includes(version));assert.equal(typeof text,'string');
 const r=JSON.parse(text),paths=[];
 const common=(x,schema)=>{assert.ok(x&&typeof x==='object'&&!Array.isArray(x));assert.equal(x.tool,'MoonTxnWitness');assert.equal(x.schemaVersion,schema);assert.equal(x.version,version);};
 const analysis=x=>{common(x,2);assert.equal(x.algorithm,'bounded-register-v2.1');};
 if(profile==='analyze-options'){analysis(r);paths.push('/version');}
 else if(profile==='shrink-options'){common(r,2);assert.equal(Object.hasOwn(r,'algorithm'),false);analysis(r.report);paths.push('/version','/report/version');}
 else if(profile==='legacy-parser-invalid'){common(r,1);assert.equal(r.status,'invalid');assert.equal(Object.hasOwn(r,'algorithm'),false);paths.push('/version');}
 else if(profile==='v3-register'){common(r,3);assert.equal(r.algorithm,'v3-register-1');paths.push('/version');if(r.evidence!==null){analysis(r.evidence);paths.push('/evidence/version');}}
 else throw Error('Unknown metadata projection profile');
 let i=0,depth=0;const spans=new Map(),white=()=>{while(/[\x20\t\r\n]/.test(text[i]??'!'))i++;};
 function token(){const start=i;assert.equal(text[i++],'"');while(i<text.length){const c=text[i++];if(c==='"')return{raw:text.slice(start,i),decoded:JSON.parse(text.slice(start,i))};if(c==='\\'){assert.ok(i<text.length);i++;}}throw Error('Unterminated JSON string');}
 function value(path){white();const start=i,c=text[i];if(c==='{'){assert.ok(++depth<=128);i++;white();const keys=new Set();if(text[i]==='}'){i++;depth--;return;}for(;;){white();const key=token();assert.equal(keys.has(key.decoded),false,'Duplicate JSON key');keys.add(key.decoded);white();assert.equal(text[i++],':');white();const begin=i,child=path+'/'+key.decoded.replaceAll('~','~0').replaceAll('/','~1');value(child);if(paths.includes(child)){assert.equal(key.raw,'"version"');assert.equal(spans.has(child),false);spans.set(child,{start:begin,end:i});}white();if(text[i]==='}'){i++;depth--;return;}assert.equal(text[i++],',');}}
 else if(c==='['){assert.ok(++depth<=128);i++;white();if(text[i]===']'){i++;depth--;return;}let n=0;for(;;){value(path+'/'+n++);white();if(text[i]===']'){i++;depth--;return;}assert.equal(text[i++],',');}}
 else if(c==='"')token();else{while(i<text.length&&!/[\x20\t\r\n,}\]]/.test(text[i]))i++;assert.ok(i>start);}}
 value('');white();assert.equal(i,text.length);assert.equal(spans.size,paths.length);
 let projected=text;for(const span of [...spans.values()].sort((a,b)=>b.start-a.start)){assert.equal(text.slice(span.start,span.end),JSON.stringify(version));projected=projected.slice(0,span.start)+'"__ENGINE_METADATA_VERSION__"'+projected.slice(span.end);}
 return{projectedText:projected,profile,paths,spans:Object.fromEntries(spans),otherCharactersPreserved:true};
}
export function projectionGuards(){
 const mk=v=>JSON.stringify({tool:'MoonTxnWitness',schemaVersion:2,algorithm:'bounded-register-v2.1',version:v,business:{version:'0.1.7',name:'0.1.8'},metrics:{attempts:17}});
 assert.equal(projectMetadata(mk('0.1.7'),'0.1.7','analyze-options').projectedText,projectMetadata(mk('0.1.8'),'0.1.8','analyze-options').projectedText);
 assert.notEqual(projectMetadata(mk('0.1.8').replace('"attempts":17','"attempts":18'),'0.1.8','analyze-options').projectedText,projectMetadata(mk('0.1.7'),'0.1.7','analyze-options').projectedText);
 assert.notEqual(projectMetadata(mk('0.1.8').replace('"name":"0.1.8"','"name":"0.1.7"'),'0.1.8','analyze-options').projectedText,projectMetadata(mk('0.1.7'),'0.1.7','analyze-options').projectedText);
 for(const bad of [mk('0.1.8').replace('{','{"version":"0.1.8",'),mk('0.1.8').replace('"name":','"version":"0.1.7","name":'),mk('0.1.8').replace('"version":"0.1.8"','"ver\\u0073ion":"0.1.8"'),mk('0.1.8').replace('bounded-register-v2.1','bounded-register-v999')])assert.throws(()=>projectMetadata(bad,'0.1.8','analyze-options'));
 assert.throws(()=>projectMetadata(mk('0.1.7'),'0.1.8','analyze-options'));
}
