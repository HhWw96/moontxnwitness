import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";

export function demand(ok, label) { if (!ok) throw new Error(label); }
export function digest(bytes) { return crypto.createHash("sha256").update(bytes).digest("hex"); }
export function safeRelative(value) {
  demand(typeof value === "string" && value.length > 0 && !value.includes("\\") && !value.startsWith("/"), "relative path required");
  demand(value.split("/").every(x => x && x !== "." && x !== ".." && !x.includes(":") && !/[. ]$/.test(x)), "unsafe relative member");
  return value;
}
export function under(root, relative) {
  const p = path.resolve(root, safeRelative(relative));
  demand(p.startsWith(path.resolve(root) + path.sep), "path escapes bundle");
  return p;
}
export function fileRecord(p) { const b = fs.readFileSync(p); return { bytes: b.length, sha256: digest(b) }; }
export function plainAncestors(p) {
  let q = path.resolve(p);
  for (;;) {
    const s = fs.lstatSync(q);
    demand(!s.isSymbolicLink(), "symlink/reparse ancestor refused: " + q);
    const parent = path.dirname(q);
    if (parent === q) break;
    q = parent;
  }
}
export function treeFiles(root) {
  plainAncestors(root);
  const found = [];
  function walk(dir, rel) {
    for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, ent.name), name = rel ? rel + "/" + ent.name : ent.name;
      const st = fs.lstatSync(p);
      demand(!st.isSymbolicLink(), "symlink/reparse member refused");
      if (st.isDirectory()) walk(p, name);
      else { demand(st.isFile(), "nonregular member refused"); found.push(safeRelative(name)); }
    }
  }
  walk(root, ""); return found.sort();
}
export const CASES = Object.freeze([
  { id: "reduce-list", method: "reduceV3", input: "list", options: { maxChecks: 256 }, category: "target" },
  { id: "reduce-relation", method: "reduceV3", input: "relation", options: { maxChecks: 256 }, category: "target" },
  { id: "reduce-register", method: "reduceV3", input: "register", options: { maxChecks: 256 }, category: "control" },
  { id: "analyze-list", method: "analyzeV3", input: "list", options: {}, category: "control" },
  { id: "analyze-relation", method: "analyzeV3", input: "relation", options: {}, category: "control" },
  { id: "analyze-register", method: "analyzeV3", input: "register", options: {}, category: "control" },
  { id: "analyze-legacy", method: "analyze", input: "legacy", options: {}, category: "control" }
]);
const INPUTS = Object.freeze({
 list: ["fixtures/list-v3/reduction-source-closure.json",2100,"ab2cb0407fc0a24ef98f45322c0c18b2b2b67b2d20d46716773601e99eca5ff4"],
 relation: ["fixtures/relation-v3/reduction-source-closure.json",4053,"34a1545ac2decc47a4508d0aa443c567f0a83f791fa05855a51ed06db5202c63"],
 register: ["examples/v3-write-skew.json",920,"9c543184d10303efc0e6e3455787af780b3c2577c9342392729a58263784ee31"],
 legacy: ["examples/write-skew.json",418,"35033736727b7a3558ae340ec6e0081a8ee2c8145df0e998cd380e81bb586f8e"]
});
const BUILD = Object.freeze({
 baseline: ["82d1bff2dbdbfba5a09b11095b4aa348fa445c36f70535f30fd52b4f9ab47518","4f1fceb7de3e541646feb80395b05ffedab1f457b308ec91e83092a485bdcfeb","21fec4d54602c70dba539fd305dcc65691d4d84ceaacb12caae5a5a520d1af39"],
 candidate:["7297ef31c66df35f79c13aaff0cbc2188a02ac6f3823fdb30544f48ad3ef2b23","c540115a0c673e77173a03df4b082b1d18ea7323af598cb3e0f5adef3365903d","b1d7a9bc3b8c9778458be128d4e166fb6f94924295ae40f3a55aac30ed333b3c"]
});
export const PROTOCOL = Object.freeze({
 warmups:5,samples:30,batches:3,coldWorkersPerRolePerCase:1,
 batchRoleOrder:[["baseline","candidate"],["candidate","baseline"],["baseline","candidate"]],
 nodeMajor:24,workerTimeoutMs:120000,minimumAvailableBytes:1073741824,maxOutputBytes:33554432,
 coldWorkers:14,timedWorkers:42,totalWorkers:56,formalSamples:1260,warmupOutputs:210,coldOutputs:14,
 outputComparison:"Exact JSON.stringify SDK-result bytes against baseline cold; no normalization or field exemptions",
 sampleTime:"Only complete synchronous SDK call; input file reads, external JSON formatting, hashes, disk writes and verifyV3 are outside",
 rss:"Linux process-lifetime maxRSS snapshot after all SDK/warm/sample output encoding/hash/write and before optional final verifyV3; final process maxRSS also retained",
 cold:"Parent spawn through IPC delivery of complete first SDK result; includes Node/job loading/input read/import/result transport; excludes parent full-runtime SHA audit; OS cache uncontrolled",
 controls:"For each batch and pooled, candidate P95 <= baseline P95 + max(10% baseline P95,2ms); all five controls must pass",
 targets:"Report both reduction targets independently; no mandatory 1.25 speed threshold, no default adoption"
});
export function validatePlan(p) {
 demand(p && p.format === "moontxnwitness-v028-reduction-paired-performance/v1", "plan format");
 demand(p.baseCommit === "c10b06c5bfcabd1f40b0ff0099717072a816ec74" && p.candidateCommit === "d7e170b2602b5c4675aa8b7645362a71ea14fbbb", "fixed commits");
 demand(JSON.stringify(p.cases) === JSON.stringify(CASES), "fixed seven cases/options/order required");
 demand(JSON.stringify(p.protocol) === JSON.stringify(PROTOCOL), "fixed protocol required");
 demand(JSON.stringify(Object.keys(p.runtimes).sort()) === '["baseline","candidate"]', "two runtime roles");
 for (const role of ["baseline","candidate"]) {
  const rt = p.runtimes[role], b = rt.build;
  demand(rt.root === "runtimes/" + role + "/dist" && rt.files.length === 102, "exact 102-file runtime");
  demand(b.version === "0.2.7" && b.sourceSha256 === BUILD[role][0] && b.coreSha256 === BUILD[role][1] && b.captureCoreSha256 === BUILD[role][2], "actual compiled runtime pins");
  const paths = rt.files.map(x => safeRelative(x.path));
  demand(new Set(paths.map(x => x.toLowerCase())).size === 102, "duplicate runtime member");
  for (const f of rt.files) demand(Number.isSafeInteger(f.bytes) && f.bytes >= 0 && /^[a-f0-9]{64}$/.test(f.sha256), "file lock");
 }
 demand(JSON.stringify(Object.keys(p.inputs).sort()) === '["legacy","list","register","relation"]', "four fixed inputs");
 for (const [label,[src,bytes,sha]] of Object.entries(INPUTS)) {
  const i=p.inputs[label];demand(i.path === "inputs/" + label + ".json" && i.frozenGitPath === src && i.bytes === bytes && i.sha256 === sha, "frozen input pin: " + label);
 }
 demand(p.artifact.id === 12639866943 && p.artifact.bytes === 12484783 && p.artifact.sha256 === "36fd50a08fc91ac6d1ec40d1baa2bbb3e730e048d2a08f068de39292f7524460", "original actual artifact pin");
 demand(p.evidence["REVIEW.json"]?.sha256==="b78861ddbe73ad70c40426d746bca277a631883723189e5fe99a771256d36844","actual independent correctness prerequisite");
 demand(p.tools.length === 4 && JSON.stringify(p.tools.map(x=>x.path).sort()) === '["common.mjs","run.mjs","test_mock.mjs","worker.mjs"]', "four fixed tools");
 return p;
}
export function readPlan(p, expectedSha) {
 demand(path.isAbsolute(p) && /^[a-f0-9]{64}$/.test(expectedSha), "absolute plan and hash required");
 plainAncestors(p);const bytes=fs.readFileSync(p);demand(digest(bytes)===expectedSha,"plan SHA mismatch");
 return validatePlan(JSON.parse(bytes.toString("utf8")));
}
export function auditRole(bundle,p,role) {
 const rt=p.runtimes[role],dir=under(bundle,rt.root);const paths=treeFiles(dir);
 demand(JSON.stringify(paths)===JSON.stringify(rt.files.map(f=>f.path).sort()),"runtime complete closure mismatch");
 for (const f of rt.files) {const got=fileRecord(under(dir,f.path));demand(got.bytes===f.bytes&&got.sha256===f.sha256,"runtime bytes changed: "+role+"/"+f.path);}
 demand(JSON.stringify(JSON.parse(fs.readFileSync(path.join(dir,"build-manifest.json"),"utf8")))===JSON.stringify(rt.build),"build manifest changed");
 for (const f of [...Object.values(p.inputs),...p.tools,...Object.values(p.evidence)]) {
  const q=under(bundle,f.path);plainAncestors(q);const got=fileRecord(q);demand(got.bytes===f.bytes&&got.sha256===f.sha256,"input/tool/evidence changed: "+f.path);
 }
 const proof=JSON.parse(fs.readFileSync(under(bundle,p.evidence["REVIEW.json"].path),"utf8"));
 demand(proof.differentialPassed===true&&proof.fullCandidateAcceptancePassed===false&&proof.actualHostedCases===284&&proof.actualHostedCalls===1658&&proof.finalReportVerificationsPerRuntime===261&&proof.sourceCommit===p.candidateCommit&&proof.baseCommit===p.baseCommit&&proof.formalPerformanceMeasured===false&&proof.readyForSeparatePerformancePlanning===true,"actual correctness scope prerequisite");
 return {role,filesVerified:102,closureSha256:digest(Buffer.from(JSON.stringify(rt.files))),sourceSha256:rt.build.sourceSha256,coreSha256:rt.build.coreSha256,captureCoreSha256:rt.build.captureCoreSha256,inputsToolsEvidenceVerified:true};
}
export function schedule(p) {
 validatePlan(p);const a=[];
 for (const c of p.cases) for(const role of ["baseline","candidate"]) a.push({id:"cold-"+c.id+"-"+role,phase:"cold",caseId:c.id,role,batch:null});
 for (let batch=0;batch<3;batch++) for (const c of p.cases) for(const role of p.protocol.batchRoleOrder[batch]) a.push({id:"batch"+(batch+1)+"-"+c.id+"-"+role,phase:"timed",caseId:c.id,role,batch:batch+1});
 demand(a.length===56,"worker count");return a;
}
export function sameBytes(a,b){demand(Buffer.isBuffer(a)&&Buffer.isBuffer(b)&&a.equals(b),"SDK output differs from baseline cold");return true;}
export function quantile(values,q) {
 demand(values.length>0&&values.every(v=>Number.isFinite(v)&&v>=0),"nonfinite/empty sample");
 const a=[...values].sort((x,y)=>x-y);
 if(q===0.5)return a.length%2?a[(a.length-1)/2]:(a[a.length/2-1]+a[a.length/2])/2;
 demand(q===0.95,"only preregistered P95");return a[Math.ceil(a.length*0.95)-1];
}
export function stats(v){demand(v.every(x=>x>0),"zero SDK duration refused");return {n:v.length,medianMs:quantile(v,0.5),p95Ms:quantile(v,0.95),minMs:Math.min(...v),maxMs:Math.max(...v)};}
export function controlGate(base,cand){demand(Number.isFinite(base)&&base>0&&Number.isFinite(cand)&&cand>0,"invalid control values");const allowance=Math.max(base*0.10,2);return {baselineP95Ms:base,candidateP95Ms:cand,allowedRegressionMs:allowance,maximumCandidateP95Ms:base+allowance,passed:cand<=base+allowance};}
export function validateWorker(w,j) {
 demand(w.id===j.id&&w.caseId===j.caseId&&w.role===j.role&&w.phase===j.phase&&w.batch===j.batch&&w.passed===true,"worker identity/order/exit");
 const count=j.phase==="cold"?1:35;
 demand(w.outputs.length===count,"exact worker output count");
 for(let k=0;k<count;k++){
  const x=w.outputs[k],phase=j.phase==="cold"?"cold":k<5?"warmup":"sample";
  demand(x.phase===phase&&x.index===k&&x.file===phase+"-"+String(k).padStart(3,"0")+".json","exact output sequence/identity");
  demand(Number.isSafeInteger(x.bytes)&&x.bytes>0&&/^[a-f0-9]{64}$/.test(x.sha256)&&Number.isFinite(x.sdkMs)&&x.sdkMs>0,"output size/hash/duration");
 }
 demand(Number.isSafeInteger(w.measuredPhaseMaxRSSKiB)&&w.measuredPhaseMaxRSSKiB>0&&Number.isSafeInteger(w.finalProcessMaxRSSKiB)&&w.finalProcessMaxRSSKiB>=w.measuredPhaseMaxRSSKiB,"RSS units/ordering");
 const c=CASES.find(x=>x.id===j.caseId);
 demand(c&&(c.method==="reduceV3"?w.verification?.valid===true:w.verification===null),"final verification scope");
 if(j.phase==="cold")demand(Number.isFinite(w.spawnToFirstResultMs)&&w.spawnToFirstResultMs>0,"cold parent delivery timing");
 return true;
}
export async function sequential(jobs,run) {const a=[];for(const j of jobs)a.push(await run(j));return a;}
export function summarize(p,workers) {
 const jobs=schedule(p);demand(workers.length===jobs.length,"all workers required");
 for(let i=0;i<jobs.length;i++){const w=workers[i],j=jobs[i];validateWorker(w,j);}
 const result=[];
 for(const c of p.cases){
  const cold={};for(const role of ["baseline","candidate"])cold[role]=workers.find(w=>w.caseId===c.id&&w.role===role&&w.phase==="cold");
  const batches=[];const pooled={baseline:[],candidate:[]};const rss={baseline:[],candidate:[]};
  for(let b=1;b<=3;b++){
   const pair={batch:b};
   for(const role of ["baseline","candidate"]){
    const w=workers.find(x=>x.caseId===c.id&&x.role===role&&x.batch===b&&x.phase==="timed");
    demand(w.outputs.length===35&&w.outputs.filter(x=>x.phase==="warmup").length===5,"warmup output count");
    const samples=w.outputs.filter(x=>x.phase==="sample");demand(samples.length===30,"sample count");
    const vals=samples.map(x=>x.sdkMs);pair[role]=stats(vals);pooled[role].push(...vals);rss[role].push(w.measuredPhaseMaxRSSKiB);
   }
   if(c.category==="control")pair.control=controlGate(pair.baseline.p95Ms,pair.candidate.p95Ms);
   batches.push(pair);
  }
  const base=stats(pooled.baseline),cand=stats(pooled.candidate);
  const row={id:c.id,category:c.category,method:c.method,batches,pooled:{baseline:base,candidate:cand},speedup:base.medianMs/cand.medianMs,rss:{baselinePeakRSSKiBByBatch:rss.baseline,candidatePeakRSSKiBByBatch:rss.candidate,baselineMedianPeakRSSKiB:quantile(rss.baseline,0.5),candidateMedianPeakRSSKiB:quantile(rss.candidate,0.5),candidateToBaselineRatio:quantile(rss.candidate,0.5)/quantile(rss.baseline,0.5)},cold:{baseline:{spawnToFirstResultMs:cold.baseline.spawnToFirstResultMs,sdkMs:cold.baseline.outputs[0].sdkMs,maxRSSKiB:cold.baseline.measuredPhaseMaxRSSKiB,outputBytes:cold.baseline.outputs[0].bytes},candidate:{spawnToFirstResultMs:cold.candidate.spawnToFirstResultMs,sdkMs:cold.candidate.outputs[0].sdkMs,maxRSSKiB:cold.candidate.measuredPhaseMaxRSSKiB,outputBytes:cold.candidate.outputs[0].bytes}}};
  if(c.category==="control")row.pooled.control=controlGate(base.p95Ms,cand.p95Ms);
  result.push(row);
 }
 return {format:"moontxnwitness-v028-reduction-paired-performance-result/v1",measurementCompleted:true,outputEquivalent:true,workers:56,formalSamples:1260,warmupOutputs:210,coldOutputs:14,cases:result,controlsPassed:result.filter(x=>x.category==="control").every(x=>x.pooled.control.passed&&x.batches.every(b=>b.control.passed)),candidateAdopted:false,performanceTargetNotMandatory125:true};
}
