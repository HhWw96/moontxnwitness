import fs from "node:fs";
import path from "node:path";
import {pathToFileURL} from "node:url";
import {performance} from "node:perf_hooks";
import {demand,digest,sameBytes,CASES} from "./common.mjs";
const args=process.argv.slice(2);
demand(args.length===2&&path.isAbsolute(args[0])&&/^[a-f0-9]{64}$/.test(args[1]),"locked job required");
demand(process.platform==="linux"&&process.env.MOONTXN_PERF_EXCLUSIVE_JOB==="1","Linux exclusive hosted worker only");
const raw=fs.readFileSync(args[0]);demand(digest(raw)===args[1],"job config hash");
const j=JSON.parse(raw);const c=CASES.find(x=>x.id===j.caseId);
demand(c&&JSON.stringify(c)===JSON.stringify(j.case)&&["baseline","candidate"].includes(j.role)&&["cold","timed"].includes(j.phase),"fixed worker operation");
demand(j.sdkPath===path.resolve(j.bundle,"runtimes",j.role,"dist","sdk.mjs")&&j.inputPath===path.resolve(j.bundle,"inputs",c.input+".json"),"worker path mapping");
demand(path.resolve(j.outputDir).startsWith(path.resolve(j.resultRoot)+path.sep)&&!fs.existsSync(j.outputDir),"new result directory");
fs.mkdirSync(j.outputDir);
function save(name,data){const p=path.join(j.outputDir,name);const b=Buffer.isBuffer(data)?data:Buffer.from(JSON.stringify(data,null,2)+"\n");fs.writeFileSync(p,b,{flag:"wx"});return p;}
let outputs=[];let lastResult;
try{
 const input=fs.readFileSync(j.inputPath,"utf8");
 const reference=j.phase==="timed"&&j.referencePath?fs.readFileSync(j.referencePath):null;
 const sdk=await import(pathToFileURL(j.sdkPath).href);
 demand(typeof sdk[c.method]==="function","exact SDK export absent");
 const call=()=>c.method==="analyze"?sdk.analyze(input):sdk[c.method](input,c.options);
 const count=j.phase==="cold"?1:35;
 for(let k=0;k<count;k++){
  const phase=j.phase==="cold"?"cold":k<5?"warmup":"sample";
  const start=performance.now();const result=call();const stop=performance.now();
  demand(result&&typeof result==="object"&&typeof result.then!=="function","synchronous SDK object required");
  if(j.phase==="cold"){
   demand(typeof process.send==="function","IPC result delivery required");
   await new Promise((resolve,reject)=>process.send({event:"first-sdk-result",caseId:j.caseId,role:j.role,result},e=>e?reject(e):resolve()));
  }
  const bytes=Buffer.from(JSON.stringify(result),"utf8");
  demand(bytes.length<=33554432,"output byte budget");
  const name=phase+"-"+String(k).padStart(3,"0")+".json";
  save(name,bytes);
  const compare=reference??(j.referencePath?fs.readFileSync(j.referencePath):null);
  if(compare)sameBytes(bytes,compare);
  const row={phase,index:k,file:name,bytes:bytes.length,sha256:digest(bytes),sdkMs:stop-start};
  demand(Number.isFinite(row.sdkMs)&&row.sdkMs>=0,"invalid duration");
  outputs.push(row);lastResult=result;
 }
 const measuredPhaseMaxRSSKiB=process.resourceUsage().maxRSS;
 let verification=null;
 if(c.method==="reduceV3"){
  demand(lastResult.reducedCapture&&lastResult.report,"reduction lacks final capture/report");
  verification=sdk.verifyV3(lastResult.reducedCapture,lastResult.report);
  save("verification.json",verification);demand(verification.valid===true,"final reduced report verification failed");
 }
 const receipt={id:j.id,caseId:j.caseId,role:j.role,phase:j.phase,batch:j.batch,passed:true,outputs,measuredPhaseMaxRSSKiB,finalProcessMaxRSSKiB:process.resourceUsage().maxRSS,pid:process.pid,nodeVersion:process.version,verification,verificationTimed:false};
 save("receipt.json",receipt);
 process.stdout.write(JSON.stringify({passed:true,id:j.id,outputs:outputs.length})+"\n");
}catch(e){save("FAILED.json",{passed:false,error:String(e?.stack??e),outputs,firstFailureOnly:true});throw e;}
