import fs from "node:fs";
import path from "node:path";
import {pathToFileURL} from "node:url";
import {Session} from "node:inspector/promises";
import {demand,digest,readPlan,auditRole,fileRecord} from "../common.mjs";
import {validatePlan,profileLoop,JOBS} from "./profile-core.mjs";
const a=process.argv.slice(2);demand(a.length===2&&path.isAbsolute(a[0])&&/^[0-9a-f]{64}$/.test(a[1]),"locked job");
demand(process.platform==="linux"&&process.env.MOONTXN_CPU_DIAGNOSTIC==="1"&&Number(process.versions.node.split(".")[0])===24,"Linux Node24 diagnostic only");
const raw=fs.readFileSync(a[0]);demand(digest(raw)===a[1],"job SHA");const j=JSON.parse(raw),praw=fs.readFileSync(j.planPath);
demand(digest(praw)===j.planSha256,"diagnostic plan SHA");const p=validatePlan(JSON.parse(praw)),spec=JOBS.find(x=>x.id===j.id);
demand(spec&&spec.input===j.input&&spec.role===j.role&&j.bundle===path.dirname(path.dirname(j.planPath)),"fixed job mapping");
demand(j.sdkPath===path.join(j.bundle,"runtimes",j.role,"dist","sdk.mjs")&&j.inputPath===path.join(j.bundle,"inputs",j.input+".json"),"exact SDK/input paths");
demand(path.resolve(j.outputDir).startsWith(path.resolve(j.resultRoot)+path.sep)&&!fs.existsSync(j.outputDir),"fresh contained worker output");
fs.mkdirSync(j.outputDir);
const files=[];let primary=null,profileState=null,verification=null;
function retain(name,raw){const state={name,bytes:raw.length,sha256:digest(raw),writeStatus:"not-attempted",observedFileBytes:null,error:null};files.push(state);try{fs.writeFileSync(path.join(j.outputDir,name),raw,{flag:"wx"});state.writeStatus="written";state.observedFileBytes=raw.length;}catch(e){state.writeStatus="failed";state.error=String(e);try{state.observedFileBytes=fs.statSync(path.join(j.outputDir,name)).size;}catch{}primary??=e;}return state;}
try{
 const original=readPlan(path.join(j.bundle,"plan.json"),p.originalPlanSha256);auditRole(j.bundle,original,j.role);
 for(const f of p.tools){const got=fileRecord(path.join(j.bundle,f.path));demand(got.bytes===f.bytes&&got.sha256===f.sha256,"diagnostic tool changed");}
 const input=fs.readFileSync(j.inputPath,"utf8"),sdk=await import(pathToFileURL(j.sdkPath).href);
 demand(typeof sdk.reduceV3==="function"&&typeof sdk.verifyV3==="function","exact SDK exports");
 const options=p.options;profileState=await profileLoop({session:new Session(),call:()=>sdk.reduceV3(input,options)});
 primary??=profileState.primaryError;
 // Output work follows stop/disconnect attempts; successful scope requires both confirmations.
 if(profileState.profile){const b=Buffer.from(JSON.stringify(profileState.profile));demand(b.length<=p.settings.maxOutputBytes,"CPU profile output budget");retain(primary?"partial.cpuprofile":"profile.cpuprofile",b);}
 else primary??=new Error("CPU profile unavailable");
 if(profileState.last!==null){
  demand(typeof profileState.last==="object"&&typeof profileState.last.then!=="function","synchronous SDK object");
  const b=Buffer.from(JSON.stringify(profileState.last));demand(b.length<=p.settings.maxOutputBytes,"final SDK output budget");retain("final-report.json",b);
  if(!primary){demand(profileState.last.reducedCapture&&profileState.last.report,"complete reduction result");verification=sdk.verifyV3(profileState.last.reducedCapture,profileState.last.report);retain("verification.json",Buffer.from(JSON.stringify(verification)));demand(verification.valid===true,"final report verification");}
 }
 demand(!primary,"profile or persistence failed: "+String(primary));demand(profileState.completed===128,"complete fixed loop");
}catch(e){primary??=e;}
const receipt={id:j.id,input:j.input,role:j.role,passed:!primary,error:primary?String(primary.stack??primary):null,completedSDKCalls:profileState?.completed??0,requestedSDKCalls:128,profileAvailable:!!profileState?.profile,stopError:profileState?.stopError?String(profileState.stopError):null,disconnectError:profileState?.disconnectError?String(profileState.disconnectError):null,profileBoundaryPolicy:profileState?.profileBoundaryPolicy??null,profileScopeProven:profileState?.profileScopeProven??false,stopConfirmed:profileState?.stopConfirmed??false,disconnectSucceeded:profileState?.disconnectSucceeded??false,resultRetentionPolicy:"Only last completed reduceV3 result is serialized after profiling; intermediate result objects overwritten",lastCompletedResultAvailable:profileState?.last!==null&&profileState?.last!==undefined,finalReportPersisted:files.some(f=>f.name==="final-report.json"&&f.writeStatus==="written"),intermediateSDKResultObjectsNotSerialized:true,verification,verificationProfiled:false,files,nodeVersion:process.version,formalPerformanceMeasurement:false,candidateAdopted:false};
try{fs.writeFileSync(path.join(j.outputDir,primary?"FAILED.json":"receipt.json"),JSON.stringify(receipt,null,2)+"\n",{flag:"wx"});}
catch(io){process.stderr.write("worker receipt persistence failed: "+String(io)+"; original error: "+String(primary)+"\n");primary??=io;}
if(primary)throw primary;
process.stdout.write(JSON.stringify({id:j.id,passed:true,completedSDKCalls:128})+"\n");
