import fs from "node:fs";
export function demand(ok,label){if(!ok)throw new Error(label);}
export const SETTINGS=Object.freeze({iterations:128,samplingIntervalUs:100,workerTimeoutMs:120000,minimumAvailableBytes:1073741824,maxOutputBytes:33554432,stdioBudgetBytes:1048576,workers:4,profiledReduceCalls:512,finalVerifications:4,formalPerformanceMeasurement:false});
export const JOBS=Object.freeze([{id:"list-baseline",input:"list",role:"baseline"},{id:"list-candidate",input:"list",role:"candidate"},{id:"relation-baseline",input:"relation",role:"baseline"},{id:"relation-candidate",input:"relation",role:"candidate"}]);
export function validatePlan(p){
 demand(p?.format==="moontxnwitness-v028-reduction-cpu-diagnostic/v1","diagnostic format");
 demand(p.parent==="c96fc56339022e76c43775ad1fe4714c7e1f7fda"&&p.branch==="experimental/v028-reduction-cpu-diagnostic-20261025","fixed diagnostic parent/branch");
 demand(p.originalPlanSha256==="4f09d227801b316db95604f7dbd601aebd2f735c4a132e4334dec41b0d966641","original performance plan");
 demand(JSON.stringify(p.settings)===JSON.stringify(SETTINGS)&&JSON.stringify(p.jobs)===JSON.stringify(JOBS),"fixed four jobs/counts/settings");
 demand(JSON.stringify(p.options)==='{"maxChecks":256}'&&p.method==="reduceV3","complete original reduceV3 budget");
 demand(p.tools?.length===3&&JSON.stringify(p.tools.map(x=>x.path).sort())==='["cpu/profile-core.mjs","cpu/run.mjs","cpu/worker.mjs"]',"three diagnostic tools");
 for(const f of p.tools)demand(Number.isSafeInteger(f.bytes)&&f.bytes>0&&/^[0-9a-f]{64}$/.test(f.sha256),"diagnostic tool locks");
 return p;
}
export async function profileLoop({session,call,iterations=128,samplingIntervalUs=100}){
 demand(iterations===128&&samplingIntervalUs===100,"fixed profile loop");
 let connected=false,started=false,stopConfirmed=false,disconnectSucceeded=false,profile=null,last=null,completed=0,primaryError=null,stopError=null,disconnectError=null;
 try{
  session.connect();connected=true;
  await session.post("Profiler.enable");
  await session.post("Profiler.setSamplingInterval",{interval:samplingIntervalUs});
  await session.post("Profiler.start");started=true;
  try{for(let k=0;k<iterations;k++){last=call();completed++;}}
  catch(e){primaryError=e;}
  finally{if(started){try{const response=await session.post("Profiler.stop");profile=response.profile??null;stopConfirmed=true;}catch(e){stopError=e;primaryError??=e;}}}
 }catch(e){primaryError??=e;}
 finally{if(connected)try{session.disconnect();disconnectSucceeded=true;}catch(e){disconnectError=e;primaryError??=e;}}
 return {profile,last,completed,primaryError,stopError,disconnectError,stopConfirmed,disconnectSucceeded,profileScopeProven:stopConfirmed&&disconnectSucceeded,profileBoundaryPolicy:"Profiler.start resolved through Profiler.stop request; only fixed synchronous full SDK calls and loop assignment/counter; no imports/JSON/hash/file/verification in loop"};
}
export function newStream(budget=1048576){return {budgetBytes:budget,receivedBytes:0,retainedBytes:0,droppedBytes:0,truncated:false,chunks:[],writeStatus:"not-attempted",persistedBytes:null,observedFileBytes:null,writeError:null};}
export function receive(stream,b){
 stream.receivedBytes+=b.length;const room=Math.max(0,stream.budgetBytes-stream.retainedBytes);
 if(room>0){const kept=Buffer.from(b.subarray(0,room));stream.chunks.push(kept);stream.retainedBytes+=kept.length;}
 stream.droppedBytes=stream.receivedBytes-stream.retainedBytes;stream.truncated=stream.droppedBytes>0;
 return stream.receivedBytes>stream.budgetBytes;
}
export function persistStream(p,stream,io=fs){
 try{const b=Buffer.concat(stream.chunks);io.writeFileSync(p,b,{flag:"wx"});stream.writeStatus="written";stream.persistedBytes=b.length;stream.observedFileBytes=b.length;return null;}
 catch(e){stream.writeStatus="failed";stream.writeError=String(e);stream.persistedBytes=null;try{stream.observedFileBytes=io.statSync(p).size;}catch{stream.observedFileBytes=null;}return e;}
}
export function captureRecord(id,streams){return {id,...Object.fromEntries(Object.entries(streams).map(([name,{chunks,...s}])=>[name,{...s}]))};}
export function allStdioRetained(records){return records.length>0&&records.every(x=>["stdout","stderr"].every(k=>x[k]&&!x[k].truncated&&x[k].writeStatus==="written"&&x[k].persistedBytes===x[k].receivedBytes));}
export async function collectChild(child,{timeoutMs=120000,budget=1048576,signals=process}={}){
 const streams={stdout:newStream(budget),stderr:newStream(budget)};
 let primaryError=null,code=null,signal=null,closed=false,kills=0;
 const kill=e=>{primaryError??=e;kills++;try{child.kill("SIGKILL");}catch(k){primaryError??=k;}};
 const cancel=()=>kill(new Error("controller cancelled"));
 let timer;
 try{
  await new Promise(resolve=>{
   child.on("close",(c,s)=>{closed=true;code=c;signal=s;clearTimeout(timer);resolve();});
   child.on("error",e=>kill(e));
   try{
    child.stdout.on("data",b=>{if(receive(streams.stdout,b))kill(new Error("stdout budget"));});
    child.stderr.on("data",b=>{if(receive(streams.stderr,b))kill(new Error("stderr budget"));});
    signals.on("SIGINT",cancel);signals.on("SIGTERM",cancel);
    timer=setTimeout(()=>kill(new Error("worker timeout")),timeoutMs);
   }catch(e){kill(e);} // Setup failure also cancels this child and awaits its actual close.
  });
 }finally{clearTimeout(timer);signals.off("SIGINT",cancel);signals.off("SIGTERM",cancel);}
 if(code!==0||signal)primaryError??=new Error("worker exit "+code+"/"+signal);
 return {streams,primaryError,code,signal,closed,kills,killAwaited:closed};
}
