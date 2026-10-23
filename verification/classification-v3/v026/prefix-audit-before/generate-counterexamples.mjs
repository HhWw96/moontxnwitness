import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import * as core from './core.mjs';
const hash=x=>createHash('sha256').update(x).digest('hex');
const cases=[];
const options=JSON.stringify({models:['adya-pl-1-v1','adya-pl-2-v1','adya-pl-2.99-v1','elle-generalized-si-v1','adya-pl-3-v1','strict-pl-ss-v1']});
for(const [name,reordered,valid] of [['omitted-initial-prefix',false,false],['reordered-initial-prefix',true,false],['valid-initial-prefix-control',false,true]]){
 const ix={id:'ix',value:'initial-x'},ix2={id:'ix2',value:'initial-x2'},iy={id:'iy',value:'initial-y'},iy2={id:'iy2',value:'initial-y2'};
 const events=[{kind:'snapshot',initial:{x:reordered?[ix,ix2]:[ix],y:reordered?[iy,iy2]:[iy]},consistent:true},{kind:'begin',tx:'A',connection:'a'},{kind:'begin',tx:'B',connection:'b'},{kind:'list_read',tx:'A',key:'y',items:reordered?[iy2,iy]:valid?[iy]:[]},{kind:'list_read',tx:'B',key:'x',items:reordered?[ix2,ix]:valid?[ix]:[]},{kind:'append',tx:'A',key:'x',id:'a',value:'same'},{kind:'append',tx:'B',key:'y',id:'b',value:'same'},{kind:'commit_request',tx:'A'},{kind:'commit_ok',tx:'A'},{kind:'commit_request',tx:'B'},{kind:'commit_ok',tx:'B'}];
 events.forEach((e,i)=>{e.seq=i+1;e.time=i});
 const trace={traceSchema:3,dataModel:'append-list-v1',clockDomain:'v3-test',scope:{exclusiveWriters:true},events,gaps:[]};
 const text=JSON.stringify(trace)+'\n',result=JSON.parse(core.classify_v3_json(text,options)),output=JSON.stringify(result,null,2)+'\n';
 writeFileSync(name+'.source.json',text,{flag:'wx'});writeFileSync(name+'.before.json',output,{flag:'wx'});
 cases.push({name,sourceSha256:hash(text),beforeSha256:hash(output),beforeStatus:result.status,models:Object.fromEntries(Object.entries(result.models??{}).map(([k,v])=>[k,v.status])),dependencies:result.dependencies?.length,expectedAfter:valid?{si:'checked-compatible',pl3:'refuted'}:{status:'inconclusive',dependencies:0,validityGap:true}});
}
const receipt={kind:'v026-list-prefix-semantic-counterexamples-before',sourceBuild:JSON.parse(readFileSync('build-manifest.json')),actualDatabaseExecution:false,formalPerformance:false,options,cases};writeFileSync('raw-before-receipt.json',JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});console.log(JSON.stringify(receipt,null,2));