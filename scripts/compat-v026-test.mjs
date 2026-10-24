// Current consumer versus original, externally pinned, anonymously downloaded public26 outputs.
// This file never regenerates an expected report or changes a recorded engine/header.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,lstatSync,realpathSync} from 'node:fs';
import {resolve,relative,isAbsolute,sep} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import childProcess from 'node:child_process';
import {syncBuiltinESMExports,createRequire} from 'node:module';
import {PUBLIC026_FIXTURE_MANIFEST_SHA256} from './public026-fixture-binding.mjs';

const [runtimeArg,fixturesArg,outputArg,...extra]=process.argv.slice(2);
assert.ok(runtimeArg&&fixturesArg&&outputArg&&!extra.length,'Usage: CURRENT_RUNTIME GENUINE26_FIXTURES NEW_OUTPUT');
const runtime=resolve(runtimeArg),fixtures=resolve(fixturesArg),output=resolve(outputArg);
mkdirSync(output);
const sha=x=>createHash('sha256').update(x).digest('hex'),canonical=x=>JSON.stringify(x,null,2)+'\n';
const require=createRequire(import.meta.url),checks=[],VERSION='0.2.6';
const SOURCE='4c74fd29f45c2e6756a20881fefb03677fa9bf52';
const receipt={format:'genuine-public026-current-consumer/v1',passed:false,node:process.version,
  originalFixtureManifestSha256:PUBLIC026_FIXTURE_MANIFEST_SHA256,sourceCommit:SOURCE,
  expectedRegenerated:false,actualDatabaseExecution:false,compilerExecuted:false,
  formalPerformanceMeasurement:false,independentAcceptance:false,checks};
const workerCounts={v024:0,v025:0,v026:0};
const spawn=childProcess.spawnSync;
childProcess.spawnSync=(...args)=>{
  for(const version of Object.keys(workerCounts))
    if(args[1]?.some?.(x=>String(x).endsWith('legacy-'+version+'-worker.mjs')))workerCounts[version]++;
  return spawn(...args);
};
syncBuiltinESMExports();
const workerTotal=()=>Object.values(workerCounts).reduce((a,b)=>a+b,0);
const legacy24=()=>Object.keys(require.cache).filter(n=>n.replaceAll('\\','/').includes('/legacy/v024/')&&n.endsWith('.cjs')).length;
function check(name,fn){fn();checks.push({name,passed:true});}
function safeFile(name){
  assert.equal(typeof name,'string');
  assert.ok(name&&!name.includes('\\')&&!name.includes(':')&&!name.startsWith('/')&&
    !name.split('/').some(part=>!part||part==='.'||part==='..'),'unsafe fixture path');
  const path=resolve(fixtures,name),rel=relative(realpathSync(fixtures),realpathSync(path));
  assert.ok(rel&&!isAbsolute(rel)&&rel!=='..'&&!rel.startsWith('..'+sep),'fixture escapes its directory');
  assert.ok(lstatSync(path).isFile()&&!lstatSync(path).isSymbolicLink(),'regular immutable fixture required');
  return path;
}
function bound(record){
  assert.ok(record&&Number.isSafeInteger(record.bytes)&&record.bytes>=0&&record.bytes<=256*1024*1024);
  assert.match(record.sha256,/^[0-9a-f]{64}$/);
  const raw=readFileSync(safeFile(record.file));
  assert.equal(raw.length,record.bytes);assert.equal(sha(raw),record.sha256);return raw;
}
function originalResult(actual,expected,type,currentVersion){
  if(type==='v1'||type==='v2'){
    assert.equal(expected.currentEngine,VERSION);assert.equal(expected.recordedEngine,VERSION);
    assert.equal(actual.currentEngine,currentVersion);assert.equal(actual.recordedEngine,VERSION);
    assert.deepEqual(actual,{...expected,currentEngine:currentVersion});
  }else assert.deepEqual(actual,expected);
}
const HOST_METHODS={
  'orm-profile':['verifyOrmProfileV3','replayOrmProfileCapsuleV3'],
  'category-classification':['verifyClassificationV3','replayClassificationCapsuleV3'],
  'model-classification':['verifyModelsClassificationV3','replayModelsClassificationCapsuleV3'],
};
const MODEL_NAMES=['model-empty-default','model-empty-pl1','model-list-skew','model-internal',
  'model-strict-bound','model-strict-equal','model-g1a','model-g1b','model-source-gap',
  'model-relation-unsupported','model-zero-budget','model-retained-lost-commit','model-g0','model-register-g2'];
try{
  // Only a separately reviewed producer receipt may supply this source pin.
  // An absent pin is a hard failure before importing either current or historical SDK.
  assert.equal(typeof PUBLIC026_FIXTURE_MANIFEST_SHA256,'string','genuine public26 producer manifest is not externally pinned yet');
  assert.match(PUBLIC026_FIXTURE_MANIFEST_SHA256,/^[0-9a-f]{64}$/);
  assert.notEqual(PUBLIC026_FIXTURE_MANIFEST_SHA256,'0'.repeat(64));
  const manifestRaw=readFileSync(safeFile('manifest.json'));
  assert.equal(sha(manifestRaw),PUBLIC026_FIXTURE_MANIFEST_SHA256);
  const manifest=JSON.parse(manifestRaw);
  check('externally pinned genuine35 producer contract',()=>{
    assert.equal(manifest.format,'moontxnwitness-actual-public-producer-fixtures/v1');
    assert.equal(manifest.producerEngineVersion,VERSION);assert.equal(manifest.actualPublishedProducer,true);
    assert.equal(manifest.sourceCommit,SOURCE);assert.equal(manifest.expectedSourceCommit,SOURCE);
    for(const key of ['rawEsmIdentityPreserved','entirePublicDistPreserved','originalProducerReplaysPassed'])assert.equal(manifest[key],true);
    for(const key of ['authorDistRead','headerRewriting','actualDatabaseExecutedHere','compilerExecutedHere'])assert.equal(manifest[key],false);
    assert.equal(manifest.existingFamilies,21);assert.equal(manifest.modelCases,14);assert.equal(manifest.cases.length,35);
    assert.equal(new Set(manifest.cases.map(x=>x.name)).size,35);
    assert.deepEqual(manifest.cases.filter(x=>x.type==='model-classification').map(x=>x.name).sort(),[...MODEL_NAMES].sort());
    assert.equal(manifest.cases.filter(x=>x.type!=='model-classification').length,21);
    for(const row of manifest.cases)assert.ok(['v1','v2','v3','execution',...Object.keys(HOST_METHODS)].includes(row.type));
  });
  const providerRaw=readFileSync(safeFile('provider-origin.json'));
  assert.equal(sha(providerRaw),manifest.providerSha256);
  const provider=JSON.parse(providerRaw);
  check('original provider provenance and entire runtime are byte-bound',()=>{
    assert.equal(provider.format,'moontxnwitness-v026-provider/v1');assert.equal(provider.version,VERSION);
    assert.equal(provider.sourceCommit,SOURCE);assert.equal(provider.actualPublishedProducer,true);
    assert.deepEqual(manifest.producerBuild,provider.buildManifest);
    assert.equal(manifest.producerBuild.version,VERSION);
    for(const [name,record]of Object.entries(manifest.producerFiles)){
      assert.equal(record.file,'producer-runtime/'+name);const raw=bound(record);
      assert.deepEqual({bytes:raw.length,sha256:sha(raw)},provider.runtime[name]);
    }
    assert.deepEqual(Object.keys(manifest.producerFiles).sort(),Object.keys(provider.runtime).sort());
    assert.equal(manifest.producerFiles['core.mjs'].sha256,manifest.producerBuild.coreSha256);
    assert.equal(manifest.producerFiles['capture-core.mjs'].sha256,manifest.producerBuild.captureCoreSha256);
  });
  const allRecords=manifest.cases.flatMap(row=>['input','report','capsule','producerReplay'].map(key=>row[key]));
  check('all original inputs reports capsules and replay results match pinned raw SHA',()=>{for(const record of allRecords)bound(record);});
  const read=record=>bound(record).toString('utf8'),find=name=>{
    const row=manifest.cases.find(x=>x.name===name);assert.ok(row,'missing genuine family '+name);return row;
  };
  const sdk=await import(pathToFileURL(resolve(runtime,'sdk.mjs')).href);
  const evidence=await import(pathToFileURL(resolve(runtime,'evidence.mjs')).href);
  receipt.currentRuntimeVersion=sdk.version();receipt.currentCoreSha256=sha(readFileSync(resolve(runtime,'core.mjs')));
  assert.notEqual(sdk.version(),VERSION,'this gate must exercise a newer consumer');
  check('ordinary current imports start no historical worker or legacy24 core',()=>{assert.equal(workerTotal(),0);assert.equal(legacy24(),0);});
  check('normal generic ORM category and six-model analysis remain current and do not start historical workers',()=>{
    sdk.analyze(read(find('register-v1').input));
    const orm=sdk.analyzeOrmProfileV3(read(find('orm-actual-1').input));
    assert.equal(orm.engineVersion,sdk.version());assert.equal(sdk.verifyOrmProfileV3(read(find('orm-actual-1').input),orm).valid,true);
    const category=sdk.classifyV3(read(find('category-g0').input));assert.equal(category.engine.version,sdk.version());
    const models=sdk.classifyModelsV3(read(find('model-empty-default').input));assert.equal(models.engine.version,sdk.version());
    assert.equal(sdk.verifyModelsClassificationV3(read(find('model-empty-default').input),models).valid,true);
    assert.equal(workerTotal(),0);assert.equal(legacy24(),0);
  });
  receipt.normalAnalysisHistoricalWorkersStarted=workerTotal();
  const original=await import(pathToFileURL(safeFile('producer-runtime/sdk.mjs')).href);
  const oldEvidence=await import(pathToFileURL(safeFile('producer-runtime/evidence.mjs')).href);
  const oldHosts={
    'orm-profile':await import(pathToFileURL(safeFile('producer-runtime/orm-profile.mjs')).href),
    'category-classification':await import(pathToFileURL(safeFile('producer-runtime/classification.mjs')).href),
    'model-classification':await import(pathToFileURL(safeFile('producer-runtime/classification-models.mjs')).href),
  };
  assert.equal(original.version(),VERSION);
  const replay=(s,e,row,text)=>HOST_METHODS[row.type]?s[HOST_METHODS[row.type][1]](text):
    row.type==='execution'?s.replayExecutionCapsuleV3(text):row.type==='v3'?s.replayCapsuleV3(text):e.replayCapsule(text);
  const refuse=(row,text,name)=>check(row.name+' rejects '+name+' with original public26 refusal',()=>{
    const expected=replay(original,oldEvidence,row,text);assert.equal(expected.valid,false);
    assert.deepEqual(replay(sdk,evidence,row,text),expected);
  });
  for(const row of manifest.cases){
    const input=read(row.input),report=JSON.parse(read(row.report)),text=read(row.capsule);
    const cap=JSON.parse(text),expected=JSON.parse(read(row.producerReplay));
    check(row.name+' unchanged original26 capsule reproduces full original result',()=>{
      assert.equal(cap.engine?.version??cap.engineVersion,VERSION);assert.equal(expected.valid,true);
      originalResult(replay(sdk,evidence,row,text),expected,row.type,sdk.version());
      assert.deepEqual(replay(original,oldEvidence,row,text),expected);
    });
    check(row.name+' unknown engine is strictly refused',()=>{
      const c=structuredClone(cap);if(c.engine)c.engine.version='9.9.9';else c.engineVersion='9.9.9';
      assert.equal(replay(sdk,evidence,row,canonical(c)).valid,false);
    });
    if(HOST_METHODS[row.type]){
      const old=oldHosts[row.type],[verifyName,replayName]=HOST_METHODS[row.type];
      check(row.name+' original report verifies with its original host core budgets counts and evidence',()=>{
        const oldResult=old[verifyName](input,report,row.requestOptions);assert.equal(oldResult.valid,true);
        assert.deepEqual(sdk[verifyName](input,report,row.requestOptions),oldResult);
      });
      for(const [name,mutate]of [
        ['unknown-algorithm',c=>c.algorithm='unknown'],['extra-field',c=>c.extra=true],
        ['missing-budgets',c=>delete c.budgets],['changed-budget',c=>{const key=Object.keys(c.budgets).find(k=>Number.isSafeInteger(c.budgets[k]));assert.ok(key);c.budgets[key]++;}],
        ['source-binding',c=>{const key=Object.keys(c.sourceBindings).find(k=>typeof c.sourceBindings[k]==='string');assert.ok(key);c.sourceBindings[key]='0'.repeat(64);}],
        ['rehashed-options',c=>{const o=JSON.parse(c.requestOptionsText);o.maxStates=o.maxStates===0?1:0;c.requestOptionsText=JSON.stringify(o);c.requestOptionsSha256=sha(c.requestOptionsText);}],
        ['rehashed-result',c=>{const r=JSON.parse(c.reportText);r.status='forged';c.reportText=JSON.stringify(r);c.reportSha256=sha(c.reportText);}],
        ['rehashed-model-and-counts',c=>{const r=JSON.parse(c.reportText);r.coreAlgorithm='forged';r.verificationPasses={forged:0};c.reportText=JSON.stringify(r);c.reportSha256=sha(c.reportText);}],
        ['rehashed-sequence',c=>{const field=Object.hasOwn(c,'envelopeText')?'envelopeText':'sourceText';const value=JSON.parse(c[field]);if(value.events?.length)value.events[0].seq=99;else value.forcedUnobservedEvent={seq:99};c[field]=JSON.stringify(value);for(const key of Object.keys(c.sourceBindings))if(c.sourceBindings[key]!==null)c.sourceBindings[key]=sha(c[field]);}],
      ]){const changed=structuredClone(cap);mutate(changed);refuse(row,canonical(changed),name);}
      for(const [name,change]of [
        ['forged-conclusion',r=>r.status='forged'],['forged-model',r=>r.coreAlgorithm='forged'],
        ['forged-budget',r=>{const key=Object.keys(r.budgets).find(k=>Number.isSafeInteger(r.budgets[k]));assert.ok(key);r.budgets[key]++;}],['forged-counts',r=>r.verificationPasses={forged:0}],
      ])check(row.name+' original report refuses '+name,()=>{
        const value=structuredClone(report);change(value);const oldResult=old[verifyName](input,value,row.requestOptions);
        assert.equal(oldResult.valid,false);assert.deepEqual(sdk[verifyName](input,value,row.requestOptions),oldResult);
      });
      if(row.type==='model-classification'&&report.result.models&&Object.keys(report.result.models).length){
        for(const [label,mutate]of [
          ['model conclusion',value=>{const key=Object.keys(value.result.models)[0];value.result.models[key].status='forged';}],
          ['required model rules',value=>{const key=Object.keys(value.result.models)[0];value.result.models[key].requiredRules=['forged'];}],
          ['core verification count',value=>value.verificationPasses.coreClassification++],
        ]){
          check(row.name+' original report refuses changed '+label,()=>{
            const value=structuredClone(report);mutate(value);const oldResult=old[verifyName](input,value,row.requestOptions);
            assert.equal(oldResult.valid,false);assert.deepEqual(sdk[verifyName](input,value,row.requestOptions),oldResult);
          });
          const value=JSON.parse(cap.reportText);mutate(value);const c=structuredClone(cap);
          c.reportText=JSON.stringify(value);c.reportSha256=sha(c.reportText);refuse(row,canonical(c),'rehashed '+label);
        }
      }
      const duplicate=row.type==='orm-profile'?'engineVersion':'algorithm';
      const value=row.type==='orm-profile'?VERSION:cap.algorithm;
      const duplicateText=text.replace(/\n}\n$/,'\n,"'+duplicate+'":'+JSON.stringify(value)+'}\n');
      assert.notEqual(duplicateText,text,'producer canonical suffix changed; review before continuing');
      refuse(row,text+' ','noncanonical suffix');refuse(row,duplicateText,'duplicate original header');
    }else{
      const changed=structuredClone(cap);
      if(row.type==='execution'){
        const value=JSON.parse(changed.diagnosticText);value.algorithm='forged';changed.diagnosticText=JSON.stringify(value);changed.diagnosticSha256=sha(changed.diagnosticText);
        check(row.name+' original execution diagnostic matches original recorded result',()=>assert.deepEqual(sdk.inspectExecutionFailuresV3(input),report));
        const missing=structuredClone(cap);delete missing.budgets;refuse(row,canonical(missing),'missing execution budgets');
      }else{
        const value=JSON.parse(changed.reportText);value.status='forged';changed.reportText=JSON.stringify(value);changed.reportSha256=sha(changed.reportText);
        if(row.type==='v3')check(row.name+' original v3 report verifies unchanged',()=>{
          const old=original.verifyV3(input,report);assert.equal(old.valid,true);assert.deepEqual(sdk.verifyV3(input,report),old);
        });else check(row.name+' original v1 v2 report has only documented response currentEngine delta',()=>{
          const old=original.replayReport(input,report);assert.equal(old.valid,true);originalResult(sdk.replayReport(input,report),old,row.type,sdk.version());
        });
      }
      if(row.type==='v2'){
        const c=structuredClone(cap),value=JSON.parse(c.reportText);value.effectiveLimits.attempts++;
        c.reportText=JSON.stringify(value);c.reportSha256=sha(c.reportText);refuse(row,canonical(c),'rehashed false effective budget');
      }
      refuse(row,canonical(changed),'rehashed false semantic result');
    }
  }
  for(const [name,command]of [
    ['register-v1','replay'],['register-v2','replay'],['register','replay-v3'],
    ['list','replay-v3'],['relation','replay-v3'],['orm-actual-1','replay-orm-profile-v3'],
    ['orm-synthetic-reduce','replay-orm-profile-v3'],['category-g0','replay-classification-v3'],
    ['category-reduce-g2-item','replay-classification-v3'],['model-g0','replay-models-classification-v3'],
    ['model-list-skew','replay-models-classification-v3'],['model-source-gap','replay-models-classification-v3'],
  ]){
    const row=find(name);
    check(name+' current CLI preserves original replay',()=>{
      const child=spawn(process.execPath,[resolve(runtime,'moontxnwitness.mjs'),command,safeFile(row.capsule.file)],
        {encoding:'utf8',timeout:300000,maxBuffer:384*1024*1024,windowsHide:true});
      writeFileSync(resolve(output,name+'.cli.stdout.json'),child.stdout??'',{flag:'wx'});
      writeFileSync(resolve(output,name+'.cli.stderr.log'),child.stderr??'',{flag:'wx'});
      assert.equal(child.error,undefined);assert.equal(child.status,0);
      originalResult(JSON.parse(child.stdout),JSON.parse(read(row.producerReplay)),row.type,sdk.version());
    });
  }
  check('original unknown commits metadata zero budgets and unsupported facts remain explicit',()=>{
    const input=JSON.parse(read(find('orm-unsupported-business-metadata').input));
    assert.equal(input.businessValue.version,'0.2.0');assert.equal(input.businessValue.text,'吴芳芳\\n/😀');
    const zero=JSON.parse(read(find('orm-synthetic-zero-budget').report));
    assert.equal(zero.result.reduction.semanticCandidateChecks,0);assert.equal(zero.result.reduction.oneMinimal,false);
    assert.equal(JSON.parse(read(find('category-zero-budget').report)).status,'inconclusive');
    const unknown=JSON.parse(read(find('unknown-commit').report));assert.ok(unknown.transactionOutcomes.some(x=>x.status==='unknown'));
    const unsupported=JSON.parse(read(find('model-relation-unsupported').report));
    assert.equal(unsupported.scope.relationModelClassificationSupported,false);
    for(const row of manifest.cases)assert.equal(row.inputOrigin.databaseExecutedHere,false);
  });
  check('original input report capsule replay runtime and manifest bytes remain untouched',()=>{
    for(const record of allRecords)bound(record);
    for(const record of Object.values(manifest.producerFiles))bound(record);
    assert.equal(sha(readFileSync(safeFile('manifest.json'))),PUBLIC026_FIXTURE_MANIFEST_SHA256);
    assert.equal(sha(readFileSync(safeFile('provider-origin.json'))),manifest.providerSha256);
  });
  receipt.passed=true;receipt.originalProducerFamilies=35;receipt.originalExistingFamilies=21;receipt.originalModelFamilies=14;
  receipt.inProcessObservedHistoricalWorkerLaunches=workerTotal();receipt.inProcessHistoricalWorkerLaunchesByVersion={...workerCounts};
  receipt.old24LegacyModulesLoadedInParentByNormalAnalysis=0;receipt.originalReportsAndCapsulesRemainByteIdentical=true;
  receipt.verificationResponseOnlyCurrentEngineDeltaAllowedFor=['v1','v2'];
}catch(error){receipt.failure={name:error.name,message:error.message};process.exitCode=1;}
receipt.checkCount=checks.length;
writeFileSync(resolve(output,'receipt.json'),canonical(receipt),{flag:'wx'});
console.log(JSON.stringify({passed:receipt.passed,currentRuntimeVersion:receipt.currentRuntimeVersion,node:receipt.node,
  checks:checks.length,originalProducerFamilies:receipt.originalProducerFamilies,
  normalAnalysisHistoricalWorkersStarted:receipt.normalAnalysisHistoricalWorkersStarted,
  inProcessObservedHistoricalWorkerLaunches:receipt.inProcessObservedHistoricalWorkerLaunches,
  expectedRegenerated:false,failure:receipt.failure??null}));
