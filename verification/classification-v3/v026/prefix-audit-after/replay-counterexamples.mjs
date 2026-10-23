import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import * as core from '../../../../dist/core.mjs';
const hash=x=>createHash('sha256').update(x).digest('hex');
const before=JSON.parse(readFileSync('../prefix-audit-before/raw-before-receipt.json','utf8'));
const cases=[];
for(const frozen of before.cases){
 const text=readFileSync('../prefix-audit-before/'+frozen.name+'.source.json','utf8');
 if(hash(text)!==frozen.sourceSha256)throw Error('Frozen source changed');
 const r=JSON.parse(core.classify_v3_json(text,before.options)),out=JSON.stringify(r,null,2)+'\n';
 writeFileSync(frozen.name+'.after.json',out,{flag:'wx'});
 const expected=frozen.expectedAfter;
 const passed=expected.validityGap ? r.status===expected.status&&r.dependencies.length===expected.dependencies&&r.validityGaps.length>0&&['G0','G1c','G2-item','G-nonadjacent'].every(k=>r.rules[k].status==='unknown') : r.models['elle-generalized-si-v1'].status===expected.si&&r.models['adya-pl-3-v1'].status===expected.pl3;
 cases.push({name:frozen.name,sourceSha256:frozen.sourceSha256,beforeSha256:frozen.beforeSha256,afterSha256:hash(out),passed,status:r.status,dependencies:r.dependencies.length,validityGaps:r.validityGaps.length,modelStatus:Object.fromEntries(Object.entries(r.models).map(([k,v])=>[k,v.status]))});
}
const receipt={kind:'author-v026-list-prefix-repair',passed:cases.every(x=>x.passed),sourceBuild:JSON.parse(readFileSync('build-manifest.json')),actualDatabaseExecution:false,formalPerformance:false,cases};
writeFileSync('author-after-receipt.json',JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});console.log(JSON.stringify(receipt,null,2));if(!receipt.passed)process.exitCode=1;