import fs from "node:fs";
import path from "node:path";
import {demand,digest,validatePlan,readPlan,auditRole,schedule,sequential,summarize,sameBytes,stats,quantile,controlGate,safeRelative,validateWorker,CASES,PROTOCOL} from "./common.mjs";
const root=path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/,"$1"));
const planPath=path.resolve(process.argv[2]??path.join(root,"plan.json"));
const raw=fs.readFileSync(planPath);const p=JSON.parse(raw.toString("utf8"));const bundle=path.dirname(planPath);
const tests=[];let sdkCalls=0;
function pass(name,f){f();tests.push({name,passed:true});}
function refuses(name,f){let rejected=false;try{f();}catch{rejected=true;}demand(rejected,"negative control accepted: "+name);tests.push({name,passed:true});}
function change(f){const q=structuredClone(p);f(q);return ()=>validatePlan(q);}
function fake(j,delta=0){
 const c=CASES.find(x=>x.id===j.caseId),bytes=Buffer.from(JSON.stringify({id:j.caseId,model:c.input,unicode:"中文🙂"}));
 const n=j.phase==="cold"?1:35;
 return {...j,passed:true,pid:7,nodeVersion:"v24.synthetic",spawnToFirstResultMs:j.phase==="cold"?12:null,measuredPhaseMaxRSSKiB:j.role==="baseline"?100000:95000,finalProcessMaxRSSKiB:110000,verification:c.method==="reduceV3"?{valid:true}:null,outputs:Array.from({length:n},(_,k)=>{
 const phase=j.phase==="cold"?"cold":k<5?"warmup":"sample";
 return {phase,index:k,file:phase+"-"+String(k).padStart(3,"0")+".json",bytes:bytes.length,sha256:digest(bytes),sdkMs:(j.role==="baseline"?5:4.5)+delta};
 })};
}
try{
 pass("fixed real plan accepted",()=>validatePlan(p));
 pass("externally pinned plan bytes accepted",()=>readPlan(planPath,digest(raw)));
 refuses("wrong outer plan hash",()=>readPlan(planPath,"0".repeat(64)));
 refuses("changed warmup count",change(q=>q.protocol.warmups=4));
 refuses("changed sample count",change(q=>q.protocol.samples=29));
 refuses("changed batch count",change(q=>q.protocol.batches=2));
 refuses("changed cold worker count",change(q=>q.protocol.coldWorkers=0));
 refuses("changed batch BA ordering",change(q=>q.protocol.batchRoleOrder[1]=["baseline","candidate"]));
 refuses("changed Node major",change(q=>q.protocol.nodeMajor=22));
 refuses("changed control tolerance",change(q=>q.protocol.controls="relaxed"));
 refuses("removed workload",change(q=>q.cases.pop()));
 refuses("reordered workloads",change(q=>q.cases.reverse()));
 refuses("unknown operation",change(q=>q.cases[0].method="custom"));
 refuses("changed maxChecks",change(q=>q.cases[0].options.maxChecks=255));
 refuses("changed control to target",change(q=>q.cases[2].category="target"));
 refuses("changed baseline commit",change(q=>q.baseCommit="0".repeat(40)));
 refuses("changed candidate commit",change(q=>q.candidateCommit="0".repeat(40)));
 refuses("wrong actual artifact",change(q=>q.artifact.sha256="0".repeat(64)));
 refuses("wrong compiled core pin",change(q=>q.runtimes.candidate.build.coreSha256="0".repeat(64)));
 refuses("missing runtime file",change(q=>q.runtimes.baseline.files.pop()));
 refuses("duplicate runtime member",change(q=>q.runtimes.baseline.files[1].path=q.runtimes.baseline.files[0].path));
 refuses("case-fold duplicate runtime member",change(q=>q.runtimes.baseline.files[1].path=q.runtimes.baseline.files[0].path.toUpperCase()));
 refuses("runtime traversal",change(q=>q.runtimes.baseline.files[0].path="../escape"));
 refuses("changed source closure fixture",change(q=>q.inputs.list.sha256="0".repeat(64)));
 refuses("changed frozen Git input path",change(q=>q.inputs.list.frozenGitPath="different.json"));
 refuses("changed tool inventory",change(q=>q.tools.pop()));
 for(const name of ["../x","/root/x","C:/x","a\\x","a//b","a/./b","a/../b","a:stream","tail.","tail "])refuses("unsafe path "+name,()=>safeRelative(name));
 pass("nested relative path accepted",()=>safeRelative("legacy/v026/core.mjs"));
 pass("exact Unicode bytes accepted",()=>sameBytes(Buffer.from("中文🙂"),Buffer.from("中文🙂")));
 refuses("different Unicode code point",()=>sameBytes(Buffer.from("🙂"),Buffer.from("😀")));
 refuses("different engine SHA has no exemption",()=>sameBytes(Buffer.from('{"engine":{"coreSha256":"a"}}'),Buffer.from('{"engine":{"coreSha256":"b"}}')));
 refuses("output size change",()=>sameBytes(Buffer.from("same"),Buffer.from("same ")));
 pass("odd median",()=>demand(quantile([3,1,2],.5)===2,"median"));
 pass("even median",()=>demand(quantile([4,1,3,2],.5)===2.5,"median"));
 pass("nearest-rank P95 30",()=>demand(quantile(Array.from({length:30},(_,i)=>i+1),.95)===29,"P95"));
 pass("nearest-rank P95 90",()=>demand(quantile(Array.from({length:90},(_,i)=>i+1),.95)===86,"P95"));
 refuses("NaN sample",()=>stats([1,NaN]));
 refuses("negative sample",()=>stats([1,-1]));
 refuses("zero-duration sample",()=>stats([0,0]));
 refuses("missing samples",()=>stats([]));
 refuses("nonfinite control",()=>controlGate(1,Infinity));
 pass("absolute 2ms tolerance exactly equal",()=>demand(controlGate(5,7).passed,"boundary"));
 pass("relative 10percent tolerance exactly equal",()=>demand(controlGate(30,33).passed,"boundary"));
 pass("absolute regression over boundary rejected",()=>demand(!controlGate(5,7.000001).passed,"boundary"));
 pass("relative regression over boundary rejected",()=>demand(!controlGate(30,33.000001).passed,"boundary"));
 const jobs=schedule(p);
 pass("56 total workers",()=>demand(jobs.length===56,"count"));
 pass("14 independent cold workers",()=>demand(jobs.filter(x=>x.phase==="cold").length===14,"cold count"));
 pass("42 independent timed workers",()=>demand(jobs.filter(x=>x.phase==="timed").length===42,"timed count"));
 for(const c of CASES)for(let b=1;b<=3;b++)pass(c.id+" batch "+b+" AB BA AB",()=>demand(JSON.stringify(jobs.filter(x=>x.caseId===c.id&&x.batch===b).map(x=>x.role))===JSON.stringify(PROTOCOL.batchRoleOrder[b-1]),"role order"));
 const workers=jobs.map(j=>fake(j));const result=summarize(p,workers);
 pass("mock report includes 1260 formal samples",()=>demand(result.formalSamples===1260,"formal samples"));
 pass("mock controls and target separation",()=>demand(result.cases.filter(x=>x.category==="control").length===5&&result.cases.filter(x=>x.category==="target").length===2&&result.controlsPassed,"case scope"));
 pass("two target speedups reported without mandatory125",()=>demand(result.cases.slice(0,2).every(x=>x.speedup===5/4.5)&&result.performanceTargetNotMandatory125,"target threshold"));
 pass("reused PID allowed",()=>demand(workers.every(x=>x.pid===7)&&result.measurementCompleted,"PID reuse"));
 pass("unadopted state",()=>demand(result.candidateAdopted===false,"adoption"));
 for(const [name,mutate] of [
 ["missing worker",a=>a.pop()],
 ["worker order",a=>[a[0],a[1]]=[a[1],a[0]]],
 ["failed worker",a=>a[0].passed=false],
 ["missing sample",a=>a[14].outputs.pop()],
 ["duplicate sample index",a=>a[14].outputs[10].index=9],
 ["wrong output phase",a=>a[14].outputs[5].phase="warmup"],
 ["wrong output hash",a=>a[14].outputs[5].sha256="x"],
 ["nonfinite SDK sample",a=>a[14].outputs[5].sdkMs=Infinity],
 ["wrong RSS units",a=>a[14].measuredPhaseMaxRSSKiB=-1],
 ["missing cold delivery",a=>a[0].spawnToFirstResultMs=null]
 ])refuses(name,()=>{const a=structuredClone(workers);mutate(a);summarize(p,a);});
 const bad=structuredClone(workers),badWorker=bad.find(x=>x.caseId==="analyze-list"&&x.role==="candidate"&&x.batch===1);
 badWorker.outputs.filter(x=>x.phase==="sample").slice(0,2).forEach(x=>x.sdkMs=100);
 const reg=summarize(p,bad),control=reg.cases.find(x=>x.id==="analyze-list");
 pass("batch-only regression is not hidden by pooled P95",()=>demand(control.pooled.control.passed&&!control.batches[0].control.passed&&!reg.controlsPassed,"batch gate"));
 pass("real baseline complete102 read-only hash audit",()=>demand(auditRole(bundle,p,"baseline").filesVerified===102,"audit"));
 pass("real candidate complete102 read-only hash audit",()=>demand(auditRole(bundle,p,"candidate").filesVerified===102,"audit"));
 let active=0,peak=0,attempts=[];
 const done=await sequential([1,2,3],async n=>{active++;peak=Math.max(peak,active);attempts.push(n);await Promise.resolve();active--;return n;});
 pass("mock transport strictly serial",()=>demand(peak===1&&done.length===3,"concurrency"));
 attempts=[];let failed=false;
 try{await sequential([1,2,3,4],async n=>{attempts.push(n);if(n===3)throw new Error("synthetic first failure");return n;});}catch{failed=true;}
 pass("mock transport stops first failure without retry",()=>demand(failed&&JSON.stringify(attempts)==="[1,2,3]","retry/continued"));
 const receipt={format:"moontxnwitness-v028-performance-pure-controls/v1",passed:true,testCount:tests.length,tests,sdkCalls,compilation:false,network:false,performanceTiming:false,syntheticDurationsOnly:true,actualProductionRuntimeImported:false,actualRuntimeFileHashAuditOnly:true,actualFormalBenchmarkExecuted:false};
 fs.writeFileSync(path.join(bundle,"PURE-MOCK-FIRST-RESULT.json"),JSON.stringify(receipt,null,2)+"\n",{flag:"wx"});
 console.log(JSON.stringify({passed:true,testCount:tests.length,sdkCalls,performanceTiming:false}));
}catch(e){fs.writeFileSync(path.join(bundle,"PURE-MOCK-FIRST-FAILED.json"),JSON.stringify({passed:false,tests,error:String(e?.stack??e),sdkCalls,productionRuntimeImported:false},null,2)+"\n",{flag:"wx"});throw e;}
