import{readFileSync,writeFileSync}from'node:fs';import{createHash}from'node:crypto';import*as core from'./core.mjs';
const hash=x=>createHash('sha256').update(x).digest('hex');
const models=['adya-pl-1-v1','adya-pl-2-v1','adya-pl-2.99-v1','elle-generalized-si-v1','adya-pl-3-v1','strict-pl-ss-v1'];
const cases=[
 ['interleaved-read-ends-other-final-append','not-refuted',false,false],
 ['read-ends-own-append-not-external-intermediate','not-refuted',false,false],
 ['dirty-final-source-keeps-G1a-without-false-G1b','not-refuted',true,false],
 ['intermediate-last-append-positive-control','refuted',false,false],
 ['interleaved-read-ends-writer-final-control','not-refuted',false,false],
 ['list-external-commit-b','unknown',false,true],['list-external-commit-ba','unknown',false,true],
 ['list-external-abort-b','unknown',true,true],['list-external-abort-ba','unknown',true,true]
].map(([id,g1b,g1a,gap])=>({id,source:'cases/'+id+'.source.json',expected:{g1b,g1aRefuted:g1a,validityGap:gap}}));
const plan={kind:'author-v026-G1b-last-version-and-prefix-semantic-regression',basis:'semantic-decision.json',models,cases};writeFileSync('author-fixed-plan.json',JSON.stringify(plan,null,2)+'\n',{flag:'wx'});
const results=[];
for(const row of cases){const text=readFileSync(row.source,'utf8'),report=JSON.parse(core.classify_v3_json(text,JSON.stringify({models}))),out=JSON.stringify(report,null,2)+'\n';writeFileSync(row.id+'.before.json',out,{flag:'wx'});const e=row.expected,got=report.rules?.G1b?.status;const valid=JSON.parse(core.verify_classification_v3_json(text,JSON.stringify(report))).valid;const passed=(e.g1b==='not-refuted'?got!=='refuted':got===e.g1b)&&(!e.g1aRefuted||report.rules.G1a.status==='refuted')&&(!e.validityGap||(report.validityGaps.length>0&&report.rules.INT.status==='unknown'))&&valid;results.push({id:row.id,expected:e,passed,sourceSha256:hash(text),outputSha256:hash(out),selfVerified:valid,g1a:report.rules?.G1a?.status,g1b:got,int:report.rules?.INT?.status,validityGaps:report.validityGaps?.length});}
const receipt={kind:'author-pre-fix-G1b-semantic-regression',passed:results.every(x=>x.passed),preservesIndependentExpectations:true,build:JSON.parse(readFileSync('build-manifest.json')),planSha256:hash(readFileSync('author-fixed-plan.json')),actualDatabaseExecution:false,formalPerformance:false,results};writeFileSync('author-before-receipt.json',JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});console.log(JSON.stringify(receipt,null,2));if(receipt.passed)throw Error('Expected frozen pre-fix candidate to retain independently observed semantic failures');