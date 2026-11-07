import strictAssert from 'node:assert/strict';
import {createPointWindowExplanationV4} from '../cmd/point-window-explanation-v4.mjs';

let checks=0;
const assert=new Proxy(strictAssert,{get(target,name){
 const method=target[name];
 return typeof method==='function'?(...args)=>{const result=Reflect.apply(method,target,args);checks++;return result;}:method;
}});

const report={format:'moontxnwitness-configured-point-window/v4',status:'refuted',
 coverageComplete:true,sourceAuthenticated:false,scope:'owned window',
 operationSources:[{historySeq:7,originalStatementSeq:3,sourceVersion:'v1',nativeResultSeq:12}],
 model:{status:'refuted'},itemCategory:{judgment:{status:'refuted'}}};
const session={diagnosticTraceText:JSON.stringify({events:[
 {kind:'statement',seq:3,tx:'t1',sql:'SELECT "<script>" WHERE id=%s',parameters:['</pre><img src=x onerror=alert(1)>']},
 {kind:'rows',statement:3,rows:[['<svg/onload=alert(1)>']],complete:true},
]})};
const originals=['start','end',session,report,{maxPointChecks:123}];
let calls=0;
const explain=createPointWindowExplanationV4((...args)=>{
 calls++;assert.deepEqual(args,originals);return {valid:true};
});
const html=explain(...originals);
assert.equal(calls,1);
assert.ok(html.startsWith('<!doctype html>'));
assert.ok(html.includes('Content-Security-Policy'));
assert.ok(html.includes('SQL → delivery → version → history'));
assert.ok(html.includes('Source authenticated: false'));
assert.ok(html.includes('&lt;script&gt;'));
assert.ok(html.includes('&lt;img src=x onerror=alert(1)&gt;'));
assert.ok(!html.includes('<script>'));
assert.ok(!html.includes('<img'));
assert.ok(!html.includes('<svg'));
assert.ok(!/https?:\/\//.test(html));
assert.ok(html.includes('Actual delivery'));
assert.ok(html.includes('nativeResultSeq'));
assert.deepEqual(originals[3],report);

const reject=createPointWindowExplanationV4(()=>({valid:false}));
assert.throws(()=>reject('','','',Object.defineProperty({},'format',{get(){throw Error('read before verify');}})),
 /does not match the original inputs/);
assert.throws(()=>createPointWindowExplanationV4(()=>({valid:1}))(...originals),/does not match/);
const verified=createPointWindowExplanationV4(()=>({valid:true}));
assert.throws(()=>verified('','',session,{...report,operationSources:[{originalStatementSeq:999}]}),/reference is missing/);
assert.throws(()=>verified('','',session,{...report,format:'other'}),/Unsupported/);
const unknown=verified('','',JSON.stringify(session),JSON.stringify({...report,status:'unknown',
 coverageComplete:false,operationSources:[],reason:'budget exhausted',model:null}), '{}');
assert.ok(unknown.includes('>unknown</p>'));
assert.ok(unknown.includes('Coverage complete: false'));
assert.ok(unknown.includes('budget exhausted'));
console.log(JSON.stringify({passed:true,checks,actualDatabaseExecution:false}));
