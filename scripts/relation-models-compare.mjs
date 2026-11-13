/** Freeze a caller-supplied SDK and compare its public relation API with an independent interpreter. */
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync,copyFileSync,mkdirSync,openSync,readSync,writeSync,closeSync,existsSync,statSync} from 'node:fs';
import {dirname,resolve} from 'node:path';
import {spawnSync} from 'node:child_process';
import {fileURLToPath,pathToFileURL} from 'node:url';

const script=fileURLToPath(import.meta.url),base=dirname(script),sha=x=>createHash('sha256').update(x).digest('hex');
const [distName,outName,...args]=process.argv.slice(2);
assert(distName&&outName,'Usage: node scripts/relation-models-compare.mjs DIST NEW_OUTPUT [--count N] [--python EXECUTABLE]');
let count=1000,python=process.env.MTW_PYTHON??'python';
for(let i=0;i<args.length;i+=2){
  assert(i+1<args.length,'Missing comparison option value');
  if(args[i]==='--count')count=Number(args[i+1]);
  else if(args[i]==='--python')python=args[i+1];
  else assert.fail('Unknown comparison option: '+args[i]);
}
assert(Number.isInteger(count)&&count>=1&&count<=1000,'--count must be 1..1000; the seed remains fixed');
const dist=resolve(distName),out=resolve(outName),tools=resolve(out,'tools'),runtime=resolve(out,'runtime');
const binding=path=>{
  const digest=createHash('sha256'),buffer=Buffer.allocUnsafe(65536),fd=openSync(path,'r');let bytes=0,n;
  try{while((n=readSync(fd,buffer,0,buffer.length,null))>0){digest.update(buffer.subarray(0,n));bytes+=n;}}
  finally{closeSync(fd);}
  return {bytes,sha256:digest.digest('hex')};
};
const originals={};
for(const name of ['core.mjs','relation-models-v4.mjs']){
  const path=resolve(dist,name);assert(statSync(path).isFile(),'Required SDK file is missing: '+name);originals['runtime/'+name]={path,...binding(path)};
}
if(existsSync(resolve(dist,'build-manifest.json')))originals['runtime/build-manifest.json']={path:resolve(dist,'build-manifest.json'),...binding(resolve(dist,'build-manifest.json'))};
for(const name of ['relation-models-compare.mjs','relation-models-compare.py','relation-models-oracle.py','relation-models-corpus.py'])originals['tools/'+name]={path:resolve(base,name),...binding(resolve(base,name))};
mkdirSync(out);mkdirSync(tools);mkdirSync(runtime);
for(const [name,value]of Object.entries(originals))copyFileSync(value.path,resolve(out,name));
const sourceBindings=Object.fromEntries(Object.entries(originals).map(([name,{path,...value}])=>[name,value]));
writeFileSync(resolve(out,'source-bindings.json'),JSON.stringify(sourceBindings,null,2)+'\n',{flag:'wx'});
const stage=(name,argv)=>{
  const result=spawnSync(python,['-X','utf8','-B',...argv],{encoding:'utf8',maxBuffer:8*1024*1024,env:{...process.env,PYTHONUTF8:'1',PYTHONDONTWRITEBYTECODE:'1'}});
  writeFileSync(resolve(out,name+'.log'),(result.stdout??'')+(result.stderr??''),{flag:'wx'});
  if(result.error)throw result.error;
  assert.equal(result.status,0,name+' failed; original output is preserved in '+name+'.log');
};
let fd,verified=0;const failures=[],totals={};
try{
  stage('generate-reference',[resolve(tools,'relation-models-corpus.py'),'--output',resolve(out,'reference'),'--count',String(count),'--seed','20261113']);
  const corpusPath=resolve(out,'reference/histories.json'),cases=JSON.parse(readFileSync(corpusPath,'utf8'));
  assert.equal(cases.length,count);
  if(count===1000)assert.equal(sha(readFileSync(corpusPath)),'b6e7d376c4a4b4664c3f728b0a57ca9171399cbbc42088082ebdbd3871037a9a','Frozen common input bytes changed');
  const sdk=await import(pathToFileURL(resolve(runtime,'relation-models-v4.mjs')).href);
  fd=openSync(resolve(out,'sdk-results.jsonl'),'wx');
  for(const [i,item]of cases.entries()){
    try{
      const options={models:'elle-core',...item.options},report=sdk.classifyRelationModelsV4(item.source,options);
      const check=sdk.verifyRelationModelsV4(item.source,report,options);
      assert.equal(check.valid,true,'Public SDK source recomputation failed');verified++;
      for(const row of report.models)totals[row.model+'/'+row.status]=(totals[row.model+'/'+row.status]??0)+1;
      writeSync(fd,JSON.stringify({id:item.id,family:item.family,sourceSha256:sha(JSON.stringify(item.source)),options,optionsSha256:sha(JSON.stringify(options)),report,verified:true})+'\n');
    }catch(error){const row={id:item.id,error:String(error),verified:false};failures.push(row);writeSync(fd,JSON.stringify(row)+'\n');}
    if((i+1)%100===0)console.log(JSON.stringify({completed:i+1,sdkFailures:failures.length}));
  }
  closeSync(fd);fd=undefined;
  stage('compare-independent',[resolve(tools,'relation-models-compare.py'),'--histories',corpusPath,'--sdk-results',resolve(out,'sdk-results.jsonl'),'--output',resolve(out,'independent')]);
  assert.equal(failures.length,0,'Public SDK execution failures were retained');
  for(const [name,value]of Object.entries(originals)){
    const expected={bytes:value.bytes,sha256:value.sha256};
    assert.deepEqual(binding(value.path),expected,'Original source changed during execution: '+name);
    assert.deepEqual(binding(resolve(out,name)),expected,'Frozen execution source changed: '+name);
  }
  const independent=JSON.parse(readFileSync(resolve(out,'independent/independent-summary.json'),'utf8'));
  const summary={format:'moontxnwitness-maintained-relation-reference-campaign/v1',passed:true,publicApiExecution:true,publicPackageVerified:false,
    formalPerformanceMeasurement:false,histories:count,judgments:count*14,seed:20261113,fullFrozenCorpus:count===1000,
    sdkReportsVerified:verified,sdkFailures:failures,totals,categories:independent.categories,independentFailures:independent.failures,
    fullFourteenModelParity:false,scope:independent.scope,sourceBindings,
    inputs:{histories:binding(corpusPath),sdkResults:binding(resolve(out,'sdk-results.jsonl'))},
    independentSummary:binding(resolve(out,'independent/independent-summary.json'))};
  writeFileSync(resolve(out,'summary.json'),JSON.stringify(summary,null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify({passed:true,histories:count,judgments:count*14,categories:summary.categories,fullFourteenModelParity:false}));
}catch(error){
  if(fd!==undefined)closeSync(fd);
  writeFileSync(resolve(out,'failure.json'),JSON.stringify({passed:false,error:String(error),sdkReportsVerified:verified,sdkFailures:failures,sourceBindings},null,2)+'\n',{flag:'wx'});
  throw error;
}
