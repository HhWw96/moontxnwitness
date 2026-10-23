// Offline fixture producer. Authentic mode accepts only completed public24 providers.
// No download, compiler, database, source rewriting or stable replay integration.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,existsSync,copyFileSync,readdirSync} from 'node:fs';
import {resolve,dirname,relative,isAbsolute} from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
const VERSION='0.2.4';
const sha=raw=>createHash('sha256').update(raw).digest('hex'),canonical=x=>JSON.stringify(x,null,2)+'\n';
function safe(name){
  assert.equal(typeof name,'string');assert.ok(name&&!name.includes('\\')&&!name.includes(':')&&!name.startsWith('/'));
  assert.ok(!name.split('/').some(p=>!p||p==='.'||p==='..'));return name;
}
function bound(provider,base,name){
  const raw=readFileSync(resolve(base,safe(name))),record=provider.bindings[name];
  assert.ok(record,'Input outside frozen provider');assert.equal(raw.length,record.bytes);assert.equal(sha(raw),record.sha256);
  return raw;
}
export async function produceV024(providerDirectory,outputDirectory,{developmentProbe=false,expectedSource}={}){
  const base=resolve(providerDirectory),out=resolve(outputDirectory),text=readFileSync(resolve(base,'provider.json'),'utf8'),provider=JSON.parse(text);
  assert.equal(provider.format,'moontxnwitness-v024-provider/v1');assert.equal(provider.version,VERSION);
  assert.equal(provider.databaseExecutedHere,false);assert.equal(provider.compilerExecutedHere,false);
  if(developmentProbe){
    assert.equal(expectedSource,undefined,'A development probe cannot assert a public source pin');
    assert.equal(provider.actualPublishedProducer,false);assert.equal(provider.authorDistRead,true);
    assert.equal(provider.originMode,'development-author-checkout');
  }else{
    assert.ok(typeof expectedSource==='string'&&/^[0-9a-f]{40}$/.test(expectedSource),'Explicit reviewed expected public source SHA required');
    assert.equal(provider.expectedSourceCommit,expectedSource);
    assert.equal(provider.actualPublishedProducer,true,'Public24 has not been established by this provider');
    assert.equal(provider.authorDistRead,false);assert.equal(provider.originMode,'verified-anonymous-public-download');
    assert.equal(provider.publicationValidationPassed,true);assert.equal(provider.sourceCommit,expectedSource);
    const publication=JSON.parse(bound(provider,base,'origin/publication.json'));
    assert.equal(sha(bound(provider,base,'origin/publication.json')),provider.publicationReceiptSha256);
    assert.equal(publication.passed,true);assert.equal(publication.version,VERSION);assert.equal(publication.github.ci.headSha,expectedSource);
    assert.equal(publication.github.assets.find(a=>a.name.endsWith('-portable.zip')).sha256,provider.publicPackage.sha256);
    assert.equal(publication.mooncakes.sha256,provider.registryPackage.sha256);
  }
  assert.equal(existsSync(out),false,'Frozen fixture directory must not exist');
  for(const name of Object.keys(provider.bindings))bound(provider,base,name);
  const runtime=resolve(base,safe(provider.runtimeDirectory)),sdk=await import(pathToFileURL(resolve(runtime,'sdk.mjs')).href);
  const orm=await import(pathToFileURL(resolve(runtime,'orm-profile.mjs')).href);
  const evidence=await import(pathToFileURL(resolve(runtime,'evidence.mjs')).href);
  assert.equal(sdk.version(),VERSION);
  const prefix=provider.packageDirectory+'/';
  const read=name=>bound(provider,base,prefix+safe(name)).toString('utf8');
  mkdirSync(out,{recursive:false});mkdirSync(resolve(out,'producer-runtime'));
  const write=(name,value)=>{
    const raw=Buffer.from(typeof value==='string'?value:canonical(value));writeFileSync(resolve(out,name),raw,{flag:'wx'});
    return {file:name,bytes:raw.length,sha256:sha(raw)};
  };
  const producerFiles={};
  for(const name of Object.keys(provider.runtime)){
    const raw=bound(provider,base,'runtime/'+name);copyFileSync(resolve(runtime,name),resolve(out,'producer-runtime',name));
    producerFiles[name]={file:'producer-runtime/'+name,bytes:raw.length,sha256:sha(raw)};
  }
  write('provider-origin.json',text);
  const cases=[];
  for(const row of provider.commonCases){
    const input=read(row.inputPath);let report,capsule,replay;
    if(row.type==='execution'){
      report=sdk.inspectExecutionFailuresV3(input);capsule=sdk.makeExecutionCapsuleV3(input);replay=sdk.replayExecutionCapsuleV3(capsule);
      assert.ok(report.transactionOutcomes.some(t=>t.status==='unknown'));assert.equal(report.captureCoverage.complete,false);
    }else if(row.type==='v3'){
      report=sdk.analyzeV3(input);capsule=sdk.makeCapsuleV3(input,report);replay=sdk.replayCapsuleV3(capsule);
    }else{
      assert.ok(['v1','v2'].includes(row.type));report=row.type==='v1'?sdk.analyze(input):sdk.analyzeWithOptions(input);
      capsule=evidence.makeCapsule(input,report);replay=evidence.replayCapsule(capsule);
    }
    assert.equal(replay.valid,true);assert.equal(JSON.parse(capsule).engineVersion,VERSION);
    if(row.type!=='execution')assert.equal(report.status,row.expectedStatus);
    cases.push({name:row.name,type:row.type,operation:'analyze',expectedStatus:row.expectedStatus,
      inputOrigin:{kind:'unchanged-original-public-bundle-facts',path:row.inputPath,originalInputUnchanged:true,newDatabaseExecution:false},
      input:write(row.name+'.input.json',input),report:write(row.name+'.report.json',report),
      capsule:write(row.name+'.capsule.json',capsule),producerReplay:write(row.name+'.producer-replay.json',replay)});
  }
  function profile(name,input,operation,options,origin,expectedStatus){
    const report=operation==='reduce'?orm.reduceOrmProfileV3(input,options):orm.analyzeOrmProfileV3(input,options);
    const capsule=operation==='reduce'?orm.makeOrmProfileReductionCapsuleV3(input,options):orm.makeOrmProfileCapsuleV3(input,options);
    const replay=orm.replayOrmProfileCapsuleV3(capsule);assert.equal(replay.valid,true);assert.deepEqual(replay.report,report);
    assert.equal(report.status,expectedStatus);assert.equal(orm.verifyOrmProfileV3(input,report,options).valid,true);
    assert.equal(JSON.parse(capsule).engineVersion,VERSION);assert.equal(replay.envelopeText,input);
    if(expectedStatus==='consistent'){
      assert.equal(report.analysisCoverageAccepted,true);assert.equal(report.result.originalDiagnosticCoverage.complete,false);
    }else if(expectedStatus==='reduced'){
      assert.equal(report.result.reduction.oneMinimal,true);assert.equal(report.result.reduction.sourceClosure.complete,true);
      assert.equal(report.result.reduction.reducedHistory.transactions.length,3);
    }else if(expectedStatus==='budget')assert.equal(report.result.reduction.oneMinimal,false);
    else if(expectedStatus==='inconclusive')assert.equal(report.analysisCoverageAccepted,false);
    cases.push({name,type:'orm-profile',operation,requestOptions:options,expectedStatus,
      inputOrigin:origin,input:write(name+'.input.json',input),report:write(name+'.report.json',report),
      capsule:write(name+'.capsule.json',capsule),producerReplay:write(name+'.producer-replay.json',replay)});
  }
  for(const row of provider.actualOrmCases)profile(row.name,read(row.inputPath),'analyze',{},
    {kind:'original-observed-current-orm-source',path:row.inputPath,originalInputUnchanged:true,newDatabaseExecution:false},'consistent');
  const synthetic=read(provider.syntheticProfilePath),syntheticOrigin={kind:'frozen-explicitly-synthetic-wire-anomaly',
    path:provider.syntheticProfilePath,actualPostgresAnomaly:false,newDatabaseExecution:false,originalInputUnchanged:true};
  profile('orm-synthetic-analyze',synthetic,'analyze',{},syntheticOrigin,'violation');
  profile('orm-synthetic-reduce',synthetic,'reduce',{},syntheticOrigin,'reduced');
  profile('orm-synthetic-zero-budget',synthetic,'reduce',{maxChecks:0},syntheticOrigin,'budget');
  const source=JSON.parse(read(provider.actualOrmCases[0].inputPath));
  source.businessValue={version:'0.2.0',decimal:1.25,text:'吴芳芳\\n/😀'};
  const modified=JSON.stringify(source);
  profile('orm-unsupported-business-metadata',modified,'analyze',{},
    {kind:'explicitly-derived-unsupported-top-level-field',basePath:provider.actualOrmCases[0].inputPath,
      originalInputUnchanged:false,changedField:'businessValue',expectedCoverage:'inconclusive',newDatabaseExecution:false},'inconclusive');
  assert.equal(JSON.parse(modified).businessValue.version,'0.2.0');
  const unmatched=JSON.parse(read(provider.actualOrmCases[0].inputPath));
  for(const [field,file]of [['traceText','trace.json'],['lifecycleText','lifecycle.jsonl'],['journalIndexText','journal-index.json']])
    unmatched[field]=read(provider.lostCommitDirectory+file);
  assert.ok(sdk.inspectExecutionFailuresV3(unmatched.traceText).transactionOutcomes.some(t=>t.status==='unknown'));
  profile('orm-unmatched-unknown-commit',JSON.stringify(unmatched),'analyze',{},
    {kind:'explicitly-mixed-unmatched-original-source-pieces',basePath:provider.actualOrmCases[0].inputPath,
      earlierUnknownCommitPath:provider.lostCommitDirectory,originalInputUnchanged:false,
      expectedCoverage:'inconclusive',newDatabaseExecution:false},'inconclusive');
  assert.equal(cases.length,15);
  const manifest={schema:1,format:developmentProbe?'moontxnwitness-development-v024-fixtures/v1':'moontxnwitness-actual-public-producer-fixtures/v1',
    producerEngineVersion:VERSION,actualPublishedProducer:!developmentProbe,
    sourceCommit:developmentProbe?null:provider.sourceCommit,expectedSourceCommit:developmentProbe?null:expectedSource,authorSourceCommit:provider.authorSourceCommit??null,
    publicPackage:provider.publicPackage??null,registryPackage:provider.registryPackage??null,
    publicationReceiptSha256:provider.publicationReceiptSha256??null,
    providerSha256:sha(text),producerBuild:provider.buildManifest,producerFiles,
    minimalOrmReplayFiles:provider.minimalOrmReplayFiles,fullSdkEsmFiles:provider.fullSdkEsmFiles,
    headerRewriting:false,authorDistRead:developmentProbe,actualDatabaseExecutedHere:false,compilerExecutedHere:false,
    allOriginalProducerReplaysPassed:true,developmentProbe,cases,
    scope:developmentProbe?'Development-only producer probe; these fixtures are NOT authentic public24 and must not be adopted as published compatibility evidence.':
      'Fresh capsules naturally generated by anonymously downloaded actual public24; observed, synthetic and deliberately unmatched inputs labelled separately; no live DB or future SDK compatibility acceptance.'};
  write('manifest.json',manifest);
  return {passed:true,producerEngineVersion:VERSION,cases:cases.length,actualPublishedProducer:!developmentProbe,
    developmentProbe,actualDatabaseExecutedHere:false,compilerExecutedHere:false,manifestSha256:sha(readFileSync(resolve(out,'manifest.json')))};
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const args=process.argv.slice(2);
  if(args[0]==='--development-probe'){
    assert.equal(args.length,3,'Usage: --development-probe NONPUBLIC_PROVIDER NEW_OUTPUT');
    console.log(JSON.stringify(await produceV024(args[1],args[2],{developmentProbe:true})));
  }else{
    assert.ok(args.length===6&&args[0]==='--provider'&&args[2]==='--expected-source'&&args[4]==='--out',
      'Usage: --provider VERIFIED_PROVIDER --expected-source VERIFIED_TAG_SHA --out NEW_OUTPUT');
    console.log(JSON.stringify(await produceV024(args[1],args[5],{expectedSource:args[3]})));
  }
}
