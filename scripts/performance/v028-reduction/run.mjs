import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import {spawn} from "node:child_process";
import {fileURLToPath} from "node:url";
import {performance} from "node:perf_hooks";
import {demand,digest,fileRecord,plainAncestors,readPlan,auditRole,schedule,sequential,summarize,sameBytes,validateWorker} from "./common.mjs";
const argv=process.argv.slice(2);
demand(argv.length===7&&argv[0]==="--plan"&&argv[2]==="--expected-plan-sha256"&&argv[4]==="--out"&&argv[6]==="--execute-exclusive-linux-hosted","explicit fixed invocation required");
const planPath=path.resolve(argv[1]),expected=argv[3],out=argv[5];
demand(path.isAbsolute(argv[1])&&path.isAbsolute(out),"absolute input/output paths");
demand(process.platform==="linux"&&process.env.GITHUB_ACTIONS==="true"&&process.env.RUNNER_OS==="Linux"&&process.env.MOONTXN_PERF_EXCLUSIVE_JOB==="1","dedicated Linux hosted job required");
demand(Number(process.versions.node.split(".")[0])===24,"fixed Node major 24");
const p=readPlan(planPath,expected),bundle=path.dirname(planPath);
demand(!fs.existsSync(out)&&!path.resolve(out).startsWith(bundle+path.sep)&&!bundle.startsWith(path.resolve(out)+path.sep),"new output outside frozen bundle");
plainAncestors(path.dirname(out));fs.mkdirSync(out);
function write(name,data){const dst=path.join(out,name);const b=Buffer.isBuffer(data)?data:Buffer.from(JSON.stringify(data,null,2)+"\n");fs.writeFileSync(dst,b,{flag:"wx"});return dst;}
function availableMemory(){const txt=fs.readFileSync("/proc/meminfo","utf8");const m=txt.match(/^MemAvailable:\s+(\d+)\s+kB$/m);demand(m,"MemAvailable unavailable");return Number(m[1])*1024;}
const nodeIdentity={path:process.execPath,...fileRecord(process.execPath),version:process.version};
const hosted={repository:process.env.GITHUB_REPOSITORY??null,sha:process.env.GITHUB_SHA??null,workflowRef:process.env.GITHUB_WORKFLOW_REF??null,workflowSha:process.env.GITHUB_WORKFLOW_SHA??null,runId:process.env.GITHUB_RUN_ID??null,attempt:process.env.GITHUB_RUN_ATTEMPT??null,runner:process.env.RUNNER_NAME??null};
write("EXECUTION-INTENT.json",{planSha256:expected,nodeIdentity,hosted,hostname:os.hostname(),platform:process.platform,arch:process.arch,cpus:os.cpus(),totalMemoryBytes:os.totalmem(),exclusiveJobAcknowledged:true,noCompilationOrDatabaseByController:true,OSFileCacheNotFlushed:true,candidateAdopted:false});
const jobs=schedule(p);const completed=[];const stdioCaptureRecords=[];
async function runOne(j){
 demand(availableMemory()>=p.protocol.minimumAvailableBytes,"resource gate before worker");
 const c=p.cases.find(x=>x.id===j.caseId);
 const dir=path.join(out,j.id),jobPath=path.join(out,j.id+".job.json");
 const before=auditRole(bundle,p,j.role);
 write(j.id+".runtime-before.json",before);
 const ref=j.role==="baseline"&&j.phase==="cold"?null:path.join(out,"cold-"+j.caseId+"-baseline","cold-000.json");
 const config={...j,case:c,bundle,resultRoot:out,outputDir:dir,inputPath:path.join(bundle,p.inputs[c.input].path),sdkPath:path.join(bundle,p.runtimes[j.role].root,"sdk.mjs"),referencePath:ref};
 const bytes=Buffer.from(JSON.stringify(config,null,2)+"\n");fs.writeFileSync(jobPath,bytes,{flag:"wx"});
 const childEnv={PATH:path.dirname(process.execPath)+":/usr/bin:/bin",LANG:"C.UTF-8",LC_ALL:"C.UTF-8",TZ:"UTC",TMPDIR:out,MOONTXN_PERF_EXCLUSIVE_JOB:"1"};
 let stdout=[],stderr=[],stdoutBytes=0,stderrBytes=0,stdoutRetainedBytes=0,stderrRetainedBytes=0,first=null,coldMs=null,childError=null,stdioCapture=null,stdioWriteError=null,postFailure=null;
 const spawnStart=performance.now();
 let child,executionError=null,auditError=null,closeCode=null,closeSignal=null,childClosedMs=null;
 try{
  await new Promise((resolve,reject)=>{
   child=spawn(process.execPath,[path.join(bundle,"worker.mjs"),jobPath,digest(bytes)],{stdio:["ignore","pipe","pipe","ipc"],shell:false,env:childEnv,cwd:bundle});
   let timer=setTimeout(()=>{child.kill("SIGKILL");childError??=new Error("worker timeout");},p.protocol.workerTimeoutMs);
   child.on("message",m=>{
    const arrived=performance.now();
    try{
     demand(j.phase==="cold"&&first===null&&m?.event==="first-sdk-result"&&m.caseId===j.caseId&&m.role===j.role,"unexpected/duplicate first result");
     coldMs=arrived-spawnStart;first=Buffer.from(JSON.stringify(m.result));
    }catch(e){childError??=e;child.kill("SIGKILL");}
   });
   child.stdout.on("data",b=>{
    stdoutBytes+=b.length;const room=Math.max(0,1048576-stdoutRetainedBytes);
    if(room>0){const kept=Buffer.from(b.subarray(0,room));stdout.push(kept);stdoutRetainedBytes+=kept.length;}
    if(stdoutBytes>1048576){childError??=new Error("stdout budget");child.kill("SIGKILL");}
   });
   child.stderr.on("data",b=>{
    stderrBytes+=b.length;const room=Math.max(0,1048576-stderrRetainedBytes);
    if(room>0){const kept=Buffer.from(b.subarray(0,room));stderr.push(kept);stderrRetainedBytes+=kept.length;}
    if(stderrBytes>1048576){childError??=new Error("stderr budget");child.kill("SIGKILL");}
   });
   child.on("error",e=>{childError??=e;});
   child.on("close",(code,signal)=>{childClosedMs=performance.now()-spawnStart;closeCode=code;closeSignal=signal;clearTimeout(timer);try{demand(!childError&&code===0&&!signal,"worker failed: "+String(childError??code??signal));resolve();}catch(e){reject(e);}});
  });
 }catch(e){executionError=e;}finally{
  stdioCapture={id:j.id,stdout:{budgetBytes:1048576,receivedBytes:stdoutBytes,retainedBytes:stdoutRetainedBytes,droppedBytes:stdoutBytes-stdoutRetainedBytes,truncated:stdoutBytes>stdoutRetainedBytes,writeStatus:"not-attempted",persistedBytes:null,observedFileBytes:null,writeError:null},stderr:{budgetBytes:1048576,receivedBytes:stderrBytes,retainedBytes:stderrRetainedBytes,droppedBytes:stderrBytes-stderrRetainedBytes,truncated:stderrBytes>stderrRetainedBytes,writeStatus:"not-attempted",persistedBytes:null,observedFileBytes:null,writeError:null}};
  stdioCaptureRecords.push(stdioCapture);
  function persistStdio(name,data,capture){
   try{write(name,data);capture.writeStatus="written";capture.persistedBytes=data.length;capture.observedFileBytes=data.length;}
   catch(e){capture.writeStatus="failed";capture.writeError=String(e);capture.persistedBytes=null;try{capture.observedFileBytes=fs.statSync(path.join(out,name)).size;}catch{capture.observedFileBytes=null;}stdioWriteError??=e;postFailure??=e;}
  }
  persistStdio(j.id+".stdout.original",Buffer.concat(stdout),stdioCapture.stdout);
  persistStdio(j.id+".stderr.original",Buffer.concat(stderr),stdioCapture.stderr);
  try{const after=auditRole(bundle,p,j.role);write(j.id+".runtime-after.json",after);demand(JSON.stringify(before)===JSON.stringify(after),"runtime changed across worker");}catch(e){auditError=e;postFailure??=e;}
  try{write(j.id+".process.json",{exitCode:closeCode,signal:closeSignal,workerWallMs:childClosedMs,executionError:executionError?String(executionError):null,auditError:auditError?String(auditError):null,stdioWriteError:stdioWriteError?String(stdioWriteError):null,coldSpawnToFirstResultMs:coldMs,stdioCapture});}catch(e){postFailure??=e;}
 }
 if(executionError)throw executionError;if(postFailure)throw postFailure;if(auditError)throw auditError;
 const receiptPath=path.join(dir,"receipt.json"),w=JSON.parse(fs.readFileSync(receiptPath,"utf8"));
 demand(w.id===j.id&&w.caseId===j.caseId&&w.role===j.role&&w.phase===j.phase&&w.batch===j.batch&&w.passed===true&&w.nodeVersion===process.version,"receipt identity");
 validateWorker({...w,spawnToFirstResultMs:coldMs},j);
 const expectedFiles=[...w.outputs.map(x=>x.file),"receipt.json",...(c.method==="reduceV3"?["verification.json"]:[])].sort();
 demand(JSON.stringify(fs.readdirSync(dir).sort())===JSON.stringify(expectedFiles),"unknown/duplicate result member");
 demand(j.phase!=="cold"||first!==null,"cold first delivery absent");
 for(const row of w.outputs){
  demand(row.file===row.phase+"-"+String(row.index).padStart(3,"0")+".json","output member name");
  const raw=fs.readFileSync(path.join(dir,row.file));demand(raw.length===row.bytes&&digest(raw)===row.sha256,"raw SDK output digest");
  if(j.phase==="cold")sameBytes(raw,first);
  if(ref)sameBytes(raw,fs.readFileSync(ref));
 }
 return {...w,spawnToFirstResultMs:coldMs,parentWorkerWallMs:childClosedMs,receiptSha256:digest(fs.readFileSync(receiptPath)),runtimeBefore:before,runtimeAfterUnchanged:true,stdioCapture};
}
try{
 await sequential(jobs,async j=>{const w=await runOne(j);completed.push(w);write(j.id+".parent-receipt.json",w);process.stdout.write(JSON.stringify({worker:j.id,completed:completed.length,total:56})+"\n");return w;});
 demand(fileRecord(process.execPath).sha256===nodeIdentity.sha256,"Node binary changed");
 for(const role of ["baseline","candidate"])auditRole(bundle,p,role);
 const summary=summarize(p,completed);
 write("COMPLETE-WORKERS.json",completed);
 write("SUMMARY.json",{...summary,planSha256:expected,nodeIdentity,hosted,completeCallsOutsideVerification:1484,optionalFinalReducedReportVerifications:24,originalInputsUnchanged:true,runtimeClosuresUnchanged:true,coldAuditExcluded:true,formalAcceptanceRequiresExternalExclusiveHostedJobEvidence:true,stdioCaptureRecords,allReceivedStdioBytesRetained:stdioCaptureRecords.every(x=>!x.stdout.truncated&&!x.stderr.truncated&&x.stdout.writeStatus==="written"&&x.stderr.writeStatus==="written"&&x.stdout.persistedBytes===x.stdout.receivedBytes&&x.stderr.persistedBytes===x.stderr.receivedBytes)});
 process.exitCode=summary.controlsPassed?0:2;
}catch(e){write("FAILED.json",{passed:false,error:String(e?.stack??e),completedWorkers:completed.length,firstFailureOnly:true,retries:0,rawSDKOutputFilesNotDeleted:true,stdioCaptureRecords,allReceivedStdioBytesRetained:stdioCaptureRecords.every(x=>!x.stdout.truncated&&!x.stderr.truncated&&x.stdout.writeStatus==="written"&&x.stderr.writeStatus==="written"&&x.stdout.persistedBytes===x.stdout.receivedBytes&&x.stderr.persistedBytes===x.stderr.receivedBytes),stdioRetentionPolicy:"Each stream retains exact first1048576 received bytes; overflow kills worker; received/retained/dropped/truncated and written/failed/persisted-byte states are explicit",planSha256:expected});throw e;}
