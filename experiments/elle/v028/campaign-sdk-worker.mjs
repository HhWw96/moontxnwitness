import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {pathToFileURL} from 'node:url';
export const digest=b=>crypto.createHash('sha256').update(b).digest('hex');
export function need(x,m){if(!x)throw new Error(m);}
export function classifyReport(input,report,verification){
 const status=report?.status,reason=report?.execution?.metrics?.reason??report?.evidence?.metrics?.reason??report?.evidence?.reason??null;
 const model=input.dataModel==='point-register-v1'?'register-serializable-v1':input.dataModel==='append-list-v1'?'append-list-serializable-v1':null;
 const qualified=verification?.valid===true&&report?.schemaVersion===3&&report?.version==='0.2.7'&&report?.tool==='MoonTxnWitness'&&report?.modelDefinition?.id===model&&report?.coverage?.complete===true;
 let category='unknown',boolean=null;
 if(verification?.valid!==true)category='verification-failure';
 else if(status==='invalid')category='invalid';
 else if(status==='consistent'||status==='violation'){category=qualified?status:'unqualified-'+status;if(qualified)boolean=status==='consistent';}
 else if(status==='inconclusive'){category=typeof reason==='string'&&(/budget|capacity|limit/.test(reason))?'budget':'unknown';}
 return {status:status??null,reason,category,comparisonBoolean:boolean,comparisonEligible:typeof boolean==='boolean',modelDefinition:report?.modelDefinition??null,coverageComplete:report?.coverage?.complete===true};
}
function writeNew(p,b){const fd=fs.openSync(p,'wx');try{fs.writeFileSync(fd,b);fs.fsyncSync(fd);}finally{fs.closeSync(fd);}}
function record(p){const b=fs.readFileSync(p);return {bytes:b.length,sha256:digest(b)};}
export function executeRows(job,sdk,root,io={writeNew,record}){
 need(job.rows.length===50,'exact original fifty rows');fs.mkdirSync(root);const ledger=path.join(root,'ledger.jsonl');io.writeNew(ledger,Buffer.alloc(0));let sequence=0,previous='0'.repeat(64),completed=0;
 const append=(row,phase,extra={})=>{const body=JSON.stringify({sequence:++sequence,id:row.id,inputSha256:row.inputSha256,phase,...extra});const raw=Buffer.from(JSON.stringify({body,bodySha256:digest(Buffer.from(body)),previousSha256:previous})+'\n');const fd=fs.openSync(ledger,'a');try{fs.writeFileSync(fd,raw);fs.fsyncSync(fd);}finally{fs.closeSync(fd);}previous=digest(Buffer.from(body));};
 for(const row of job.rows){
  let primary=null;try{
   need(/^(register|list)-\d+$/.test(row.id)&&digest(Buffer.from(JSON.stringify(row.input)))===row.inputSha256,'original SDK input identity');
   const inputRaw=Buffer.from(JSON.stringify(row.input));io.writeNew(path.join(root,row.id+'.input.json'),inputRaw);
   append(row,'analysis-intent');const report=sdk.analyzeV3(row.input);need(report&&typeof report==='object'&&typeof report.then!=='function','synchronous complete analyzeV3 result');
   const reportRaw=Buffer.from(JSON.stringify(report));need(reportRaw.length<=33554432,'full SDK report budget');const reportPath=path.join(root,row.id+'.report.json');io.writeNew(reportPath,reportRaw);append(row,'report-retained',{report:io.record(reportPath)});
   append(row,'verification-intent');const verification=sdk.verifyV3(row.input,report);const verifyRaw=Buffer.from(JSON.stringify(verification));need(verifyRaw.length<=1048576,'verification output budget');const verifyPath=path.join(root,row.id+'.verification.json');io.writeNew(verifyPath,verifyRaw);append(row,'verification-retained',{verification:io.record(verifyPath)});
   need(verification?.valid===true,'public SDK report semantic verification failed');
   const classification=classifyReport(row.input,report,verification);append(row,'completed',{classification});completed++;
  }catch(e){primary=e;try{append(row,'failure',{error:String(e?.stack??e)});}catch(ioError){process.stderr.write('ledger failure: '+String(ioError)+'; primary: '+String(primary)+'\n');}throw primary;}
 }
 const result={passed:true,completed,requested:50,ledger:io.record(ledger),lastBodySha256:previous,SDKSource:'anonymous fixed public v0.2.7 top-level dist/sdk.mjs',formalPerformanceMeasurement:false};io.writeNew(path.join(root,'receipt.json'),Buffer.from(JSON.stringify(result,null,2)+'\n'));return result;
}
async function main(){
 const a=process.argv.slice(2);need(a.length===2&&path.isAbsolute(a[0])&&/^[0-9a-f]{64}$/.test(a[1]),'locked SDK job');need(process.platform==='linux'&&process.env.MOONTXN_ELLE_CAMPAIGN_SDK==='1'&&process.versions.node.split('.')[0]==='24','hosted Linux Node24 only');
 const raw=fs.readFileSync(a[0]);need(digest(raw)===a[1],'SDK job SHA');const job=JSON.parse(raw);need(path.isAbsolute(job.publicDist)&&path.isAbsolute(job.output)&&job.output.startsWith(job.owner+path.sep)&&!fs.existsSync(job.output),'owned fresh SDK output');
 const manifestRaw=fs.readFileSync(job.publicManifest);need(digest(manifestRaw)===job.publicManifestSha256,'public manifest SHA');const manifest=JSON.parse(manifestRaw);need(manifest.files.length===102&&manifest.entryPoint==='sdk.mjs'&&manifest.archiveSha256==='4de093877bd75d55e327c5015484aead587e5be59bd22818d035c0fed4298c3d','public top-level release only');
 for(const f of manifest.files){const p=path.join(job.publicDist,f.path),r=record(p);need(r.bytes===f.bytes&&r.sha256===f.sha256,'public runtime member changed');}
 const sdk=await import(pathToFileURL(path.join(job.publicDist,'sdk.mjs')).href);need(sdk.version()==='0.2.7'&&typeof sdk.analyzeV3==='function'&&typeof sdk.verifyV3==='function','public027 exact API');
 const result=executeRows(job,sdk,job.output);for(const f of manifest.files){const r=record(path.join(job.publicDist,f.path));need(r.bytes===f.bytes&&r.sha256===f.sha256,'public runtime changed during SDK run');}process.stdout.write(JSON.stringify({passed:true,completed:result.completed})+'\n');
}
if(process.argv[1]&&pathToFileURL(path.resolve(process.argv[1])).href===import.meta.url)await main();