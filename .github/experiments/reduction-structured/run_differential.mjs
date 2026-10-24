// One correctness pass only. No compilation, subprocess, warmup, timing or fixture writes.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync,mkdirSync,readdirSync,lstatSync,realpathSync,existsSync} from 'node:fs';
import {resolve,relative,dirname,sep} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
const here=dirname(fileURLToPath(import.meta.url));
const args=process.argv.slice(2),opt={};
for(let i=0;i<args.length;i+=2){
  assert.ok(['--baseline-runtime','--candidate-runtime','--bindings','--bindings-sha256','--output'].includes(args[i]));
  assert.equal(opt[args[i]],undefined);assert.ok(args[i+1]);opt[args[i]]=args[i+1];
}
for(const key of ['--baseline-runtime','--candidate-runtime','--bindings','--bindings-sha256','--output'])assert.ok(opt[key],key+' required');
const sha=b=>createHash('sha256').update(b).digest('hex');
const read=p=>readFileSync(p);
const parse=p=>JSON.parse(read(p));
const manifest=parse(resolve(here,'CANDIDATE.json'));
const bindingRaw=read(resolve(opt['--bindings']));
assert.match(opt['--bindings-sha256'],/^[a-f0-9]{64}$/);assert.equal(sha(bindingRaw),opt['--bindings-sha256']);
const bindings=JSON.parse(bindingRaw);
assert.equal(bindings.schema,1);assert.equal(bindings.baseCommit,manifest.baseCommit);
assert.equal(bindings.baseline.sourceFileSha256,manifest.baselineRawSha256);
assert.equal(bindings.candidate.sourceFileSha256,manifest.candidateRawSha256);
assert.equal(sha(read(resolve(here,manifest.baselineSourceFile))),manifest.baselineRawSha256);
assert.equal(sha(read(resolve(here,manifest.candidateSourceFile))),manifest.candidateRawSha256);
assert.equal(sha(read(resolve(here,'candidate.patch'))),manifest.patchSha256);
for(const row of manifest.inputs){const raw=read(resolve(here,'inputs',row.path));assert.equal(raw.length,row.bytes);assert.equal(sha(raw),row.sha256);}
function inventory(root,folder=root){
  const out=[];for(const name of readdirSync(folder).sort()){
    const path=resolve(folder,name),stat=lstatSync(path);assert.equal(stat.isSymbolicLink(),false,'runtime link rejected');
    if(stat.isDirectory())out.push(...inventory(root,path));
    else {assert.ok(stat.isFile());out.push(relative(root,path).split(sep).join('/'));}
  }return out.sort();
}
function bindRuntime(role){
  const root=realpathSync(resolve(opt['--'+role+'-runtime']));
  assert.ok(Array.isArray(bindings[role].files)&&bindings[role].files.length>0,'runtime must be externally frozen');
  const seen=new Set();for(const row of bindings[role].files){
    assert.equal(typeof row.path,'string');assert.ok(!row.path.includes('\\')&&!row.path.startsWith('/')&&!row.path.split('/').some(p=>p==='..'||p==='.'||!p));
    assert.equal(seen.has(row.path),false);seen.add(row.path);
    const path=resolve(root,row.path);assert.ok(path.startsWith(root+sep));
    const raw=read(path);assert.equal(raw.length,row.bytes);assert.equal(sha(raw),row.sha256);
  }
  assert.deepEqual(inventory(root),[...seen].sort(),'exact full runtime closure');
  for(const path of ['sdk.mjs','core.mjs','capture-core.mjs','build-manifest.json'])assert.ok(seen.has(path));
  const build=parse(resolve(root,'build-manifest.json'));
  assert.equal(sha(read(resolve(root,'core.mjs'))),build.coreSha256);
  assert.equal(sha(read(resolve(root,'capture-core.mjs'))),build.captureCoreSha256);
  return root;
}
const roots={baseline:bindRuntime('baseline'),candidate:bindRuntime('candidate')};
const out=resolve(opt['--output']);assert.equal(existsSync(out),false,'new output directory required');mkdirSync(out,{recursive:false});
const save=(name,value,raw=false)=>writeFileSync(resolve(out,name),raw?value:JSON.stringify(value,null,2)+'\n',{flag:'wx'});
const receipt={schema:1,kind:'fixed-model-reduction-exact-differential',passed:false,performanceMeasured:false,
  actualDatabaseExecution:false,bindingsSha256:sha(bindingRaw),baseCommit:manifest.baseCommit,cases:[],calls:0};
const cases=[];
function add(id,text,options='{}'){cases.push({id,text,options});}
for(const [model,path] of [['list','fixtures/list-v3/manual.json'],['relation','fixtures/relation-v3/boundary.json']]){
  for(const row of parse(resolve(here,'inputs',path))){
    assert.equal(sha(Buffer.from(row.traceText)),row.inputSha256);
    add(model+'-frozen-'+row.id,row.traceText,JSON.stringify({analysisOptions:row.options||{}}));
  }
}
for(const model of ['list','relation']){
  const text=read(resolve(here,'inputs','fixtures',model+'-v3','reduction-source-closure.json')).toString('utf8');
  for(const budget of [0,1,2,256])add(model+'-source-closure-checks-'+budget,text,JSON.stringify({maxChecks:budget}));
  for(const options of [{maxStates:0},{maxStates:1},{maxOperationChecks:0}])add(model+'-analysis-'+Object.entries(options)[0].join('-'),text,JSON.stringify({maxChecks:256,analysisOptions:options}));
  const unicode=JSON.parse(text);unicode.clockDomain='reduction-证据-😀';add(model+'-unicode-identity',JSON.stringify(unicode));
  const wrong=JSON.parse(text);wrong.dataModel='unsupported-model';add(model+'-unsupported-model',JSON.stringify(wrong));
  for(const value of [-1,257,0.5,true])add(model+'-invalid-maxChecks-'+value,text,JSON.stringify({maxChecks:value}));
  add(model+'-invalid-analysis-option',text,'{"analysisOptions":{"unexpected":1}}');
}
for(const model of ['list','relation']){
  const text=read(resolve(here,'inputs','fixtures',model+'-v3','reduction-source-closure.json')).toString('utf8');
  assert.equal(Buffer.byteLength(text,'utf8'),text.length,'ASCII byte/scalar boundary fixture');
  for(const limit of [8388608,8388609])add(model+'-text-limit-'+limit,' '.repeat(limit-text.length)+text,'{"maxChecks":0}');
}
const register=read(resolve(here,'inputs','examples/v3-write-skew.json')).toString('utf8');
for(const budget of [0,1,256])add('register-unchanged-checks-'+budget,register,JSON.stringify({maxChecks:budget}));
for(const [id,text] of [['truncated','{'],['empty',''],['duplicate-key','{"traceSchema":3,"traceSchema":3}'],['array-root','[]'],['invalid-literal','tru'],['raw-surrogate','"\\ud800"']])add('invalid-'+id,text);
add('invalid-options-json',register,'{');add('non-object-options',register,'null');
assert.equal(new Set(cases.map(row=>row.id)).size,cases.length);
try{
  const runtime={};for(const role of ['baseline','candidate'])runtime[role]={
    core:await import(pathToFileURL(resolve(roots[role],'core.mjs')).href),
    sdk:await import(pathToFileURL(resolve(roots[role],'sdk.mjs')).href)};
  assert.equal(runtime.baseline.core.version(),runtime.candidate.core.version(),'same product version required');
  for(let index=0;index<cases.length;index++){
    const row=cases[index],name=String(index+1).padStart(3,'0');
    save(name+'-input.json',row.text,true);save(name+'-options.json',row.options,true);
    const record={id:row.id,inputSha256:sha(row.text),optionsSha256:sha(row.options)};receipt.cases.push(record);
    const core={};for(const role of ['baseline','candidate']){
      receipt.calls++;core[role]=runtime[role].core.reduce_v3_json(row.text,row.options);
      assert.equal(typeof core[role],'string');save(name+'-'+role+'-core.json',core[role],true);
      record[role+'CoreSha256']=sha(core[role]);
    }
    assert.equal(core.candidate,core.baseline,'complete core output: '+row.id);
    const sdk={},outcomes={};for(const role of ['baseline','candidate']){
      receipt.calls++;
      try {
        sdk[role]=runtime[role].sdk.reduceV3(row.text,row.options);
        outcomes[role]={returned:true,value:sdk[role]};
        save(name+'-'+role+'-sdk.json',sdk[role]);
      } catch(error) {
        assert.ok(error instanceof Error,'SDK must throw an Error instance');
        outcomes[role]={returned:false,error:{className:error.constructor.name,name:error.name,message:error.message}};
      }
      save(name+'-'+role+'-sdk-outcome.json',outcomes[role]);
    }
    assert.deepEqual(outcomes.candidate,outcomes.baseline,'complete SDK return/exception outcome: '+row.id);
    if(outcomes.baseline.returned){
      assert.deepEqual(sdk.baseline,JSON.parse(core.baseline),'SDK/core full returned output: '+row.id);
    }else{
      // The unchanged SDK rejects UTF-8 over 8MiB before calling the core.
      // Preserve that API boundary and compare the exact original exception.
      assert.ok(row.id.endsWith('-text-limit-8388609'),'Unexpected SDK exception: '+row.id);
      assert.equal(Buffer.byteLength(row.text,'utf8'),8388609);
      assert.deepEqual(outcomes.baseline.error,{className:'RangeError',name:'RangeError',message:'v3 input exceeds 8388608 UTF-8 bytes'});
      record.sdkExceptionCompared=true;
    }
    if(outcomes.baseline.returned&&Object.hasOwn(sdk.baseline,'report')){
      const verified={};for(const role of ['baseline','candidate']){
        receipt.calls++;verified[role]=runtime[role].sdk.verifyV3(sdk[role].reducedCapture,sdk[role].report);
        save(name+'-'+role+'-verification.json',verified[role]);assert.equal(verified[role].valid,true,'final complete revalidation: '+row.id);
      }
      assert.deepEqual(verified.candidate,verified.baseline);
      record.finalRevalidation=true;
    }
    if(row.id.endsWith('-checks-0')){assert.equal(sdk.baseline.checks,0);assert.equal(sdk.baseline.oneMinimal,false);}
    record.passed=true;
  }
  assert.equal(receipt.cases.filter(row=>row.sdkExceptionCompared).length,2,'Both original SDK over-limit exceptions must be compared');
  receipt.passed=true;
}catch(error){receipt.error=String(error.stack||error);save('FIRST-FAILURE.json',{error:receipt.error,completed:receipt.cases.filter(r=>r.passed).length,calls:receipt.calls});process.exitCode=1;}
finally{save('RECEIPT.json',receipt);console.log(JSON.stringify({passed:receipt.passed,cases:receipt.cases.length,calls:receipt.calls,output:out,performanceMeasured:false}));}