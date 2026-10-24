import fs from "node:fs";
import path from "node:path";
import {spawn} from "node:child_process";
import {demand,digest,readPlan,auditRole,fileRecord,plainAncestors} from "../common.mjs";
import {validatePlan,JOBS,collectChild,persistStream,captureRecord,allStdioRetained} from "./profile-core.mjs";
const a=process.argv.slice(2);demand(a.length===7&&a[0]==="--plan"&&a[2]==="--expected-plan-sha256"&&a[4]==="--out"&&a[6]==="--execute-hosted-cpu-diagnostic","explicit diagnostic invocation");
demand(path.isAbsolute(a[1])&&path.isAbsolute(a[5])&&/^[0-9a-f]{64}$/.test(a[3]),"absolute paths and SHA");
demand(process.platform==="linux"&&process.env.GITHUB_ACTIONS==="true"&&process.env.RUNNER_OS==="Linux"&&process.env.MOONTXN_CPU_DIAGNOSTIC==="1"&&Number(process.versions.node.split(".")[0])===24,"dedicated hosted Linux Node24 diagnostic");
const raw=fs.readFileSync(a[1]);demand(digest(raw)===a[3],"diagnostic plan hash");
const p=validatePlan(JSON.parse(raw)),bundle=path.dirname(path.dirname(a[1])),out=a[5];
demand(!fs.existsSync(out)&&!path.resolve(out).startsWith(bundle+path.sep)&&!bundle.startsWith(path.resolve(out)+path.sep),"new output outside bundle");
plainAncestors(path.dirname(out));fs.mkdirSync(out);
function write(name,obj){fs.writeFileSync(path.join(out,name),Buffer.isBuffer(obj)?obj:JSON.stringify(obj,null,2)+"\n",{flag:"wx"});}
function audit(role){
 const original=readPlan(path.join(bundle,"plan.json"),p.originalPlanSha256);
 const result=auditRole(bundle,original,role);
 demand(digest(fs.readFileSync(a[1]))===a[3],"diagnostic plan changed");
 for(const f of p.tools){plainAncestors(path.join(bundle,f.path));const v=fileRecord(path.join(bundle,f.path));demand(v.bytes===f.bytes&&v.sha256===f.sha256,"diagnostic tool changed");}
 return result;
}
const completed=[],captures=[];let current=null;
write("INTENT.json",{format:p.format,planSha256:a[3],head:process.env.GITHUB_SHA,runId:process.env.GITHUB_RUN_ID,attempt:process.env.GITHUB_RUN_ATTEMPT,nodeVersion:process.version,nodeBinary:fileRecord(process.execPath),fourSerialDiagnosticWorkers:true,formalPerformanceMeasurement:false,noSDKTimingOrSpeedRatios:true,candidateAdopted:false});
try{
 for(const spec of JOBS){
  current=spec.id;const mem=fs.readFileSync("/proc/meminfo","utf8").match(/^MemAvailable:\s+(\d+)\s+kB$/m);demand(mem&&Number(mem[1])*1024>=p.settings.minimumAvailableBytes,"1GiB available memory");
  const before=audit(spec.role);write(spec.id+".runtime-before.json",before);
  const job={...spec,bundle,planPath:a[1],planSha256:a[3],resultRoot:out,outputDir:path.join(out,spec.id),sdkPath:path.join(bundle,"runtimes",spec.role,"dist","sdk.mjs"),inputPath:path.join(bundle,"inputs",spec.input+".json")};
  const jraw=Buffer.from(JSON.stringify(job,null,2)+"\n"),jp=path.join(out,spec.id+".job.json");write(spec.id+".job.json",jraw);
  let result=null,primary=null;const cap={id:spec.id,stdout:null,stderr:null,childSpawned:false,childClosed:false};captures.push(cap);
  try{
   const env={PATH:path.dirname(process.execPath)+":/usr/bin:/bin",LANG:"C.UTF-8",LC_ALL:"C.UTF-8",TZ:"UTC",TMPDIR:out,MOONTXN_CPU_DIAGNOSTIC:"1"};
   const child=spawn(process.execPath,[path.join(bundle,"cpu/worker.mjs"),jp,digest(jraw)],{stdio:["ignore","pipe","pipe"],shell:false,env,cwd:bundle});
   cap.childSpawned=true;result=await collectChild(child,{timeoutMs:p.settings.workerTimeoutMs});cap.childClosed=result.closed;primary=result.primaryError;
   // Capture records are registered before either raw stream write; independent write states are honest on ENOSPC.
   for(const name of ["stdout","stderr"]){cap[name]=captureRecord(spec.id,{stream:result.streams[name]}).stream;}
   for(const name of ["stdout","stderr"]){const err=persistStream(path.join(out,spec.id+"."+name+".original"),result.streams[name]);cap[name]=captureRecord(spec.id,{stream:result.streams[name]}).stream;primary??=err;}
  }catch(e){primary??=e;}
  finally{
   try{const after=audit(spec.role);write(spec.id+".runtime-after.json",after);demand(JSON.stringify(before)===JSON.stringify(after),"runtime changed");}catch(e){primary??=e;}
   try{write(spec.id+".process.json",{exitCode:result?.code??null,signal:result?.signal??null,childClosed:result?.closed??false,killAwaited:result?.killAwaited??false,kills:result?.kills??0,error:primary?String(primary):null,stdioCapture:cap});}catch(e){primary??=e;}
  }
  if(primary)throw primary;
  const w=JSON.parse(fs.readFileSync(path.join(job.outputDir,"receipt.json")));
  demand(w.passed===true&&w.id===spec.id&&w.role===spec.role&&w.input===spec.input&&w.completedSDKCalls===128&&w.verification?.valid===true&&w.formalPerformanceMeasurement===false,"worker receipt complete");
  demand(JSON.stringify(fs.readdirSync(job.outputDir).sort())==='["final-report.json","profile.cpuprofile","receipt.json","verification.json"]',"exact worker outputs");
  for(const f of w.files){const b=fs.readFileSync(path.join(job.outputDir,f.name));demand(f.writeStatus==="written"&&b.length===f.bytes&&digest(b)===f.sha256,"raw worker file digest");}
  if(spec.role==="candidate")demand(fs.readFileSync(path.join(out,spec.input+"-baseline/final-report.json")).equals(fs.readFileSync(path.join(job.outputDir,"final-report.json"))),"final complete SDK report differs from baseline");
  completed.push({id:spec.id,receiptSha256:digest(fs.readFileSync(path.join(job.outputDir,"receipt.json"))),completedSDKCalls:128,finalReport:fileRecord(path.join(job.outputDir,"final-report.json")),cpuProfile:fileRecord(path.join(job.outputDir,"profile.cpuprofile"))});
 }
 write("COMPLETE.json",{diagnosticCompleted:true,workers:completed,profiledReduceCalls:512,untimedVerifyV3Calls:4,totalTopLevelSDKCalls:516,finalReportsEquivalent:true,stdioCaptureRecords:captures,allReceivedStdioBytesRetained:allStdioRetained(captures),formalPerformanceMeasurement:false,speedupClaimed:false,candidateAdopted:false,profileInterpretationPending:true});
}catch(e){
 try{write("FAILED.json",{passed:false,error:String(e?.stack??e),currentWorker:current,completed,stdioCaptureRecords:captures,allReceivedStdioBytesRetained:allStdioRetained(captures),captureAccountingComplete:captures.length>0&&captures.every(c=>c.stdout&&c.stderr),firstFailureOnly:true,retries:0,partialWorkerFilesNotDeleted:true,formalPerformanceMeasurement:false,candidateAdopted:false});}catch(io){process.stderr.write("FAILED receipt could not be persisted: "+String(io)+"; first error: "+String(e)+"\n");}
 throw e;
}
