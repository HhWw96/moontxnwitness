// Complete report parity and feature fallback; no performance claims.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync,mkdtempSync,mkdirSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {tmpdir} from 'node:os';
import {pathToFileURL,fileURLToPath} from 'node:url';

const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const [runtimeArg=resolve(root,'dist'),receiptArg]=process.argv.slice(2);
const runtime=resolve(runtimeArg),coreFile=resolve(runtime,'core.mjs');
const core=await import(pathToFileURL(coreFile));
const sdk=await import(pathToFileURL(resolve(runtime,'sdk.mjs')));
const digest=path=>createHash('sha256').update(readFileSync(path)).digest('hex');
const coreSha256=digest(coreFile),results=[];
function check(name,fn){fn();results.push({name,passed:true});}
const variants=[
  {name:'models',api:'classifyModelsV4',native:'classify_models_v4_native',text:'classify_models_v4_json',
    normalizer:'model_options_v4_content_json',guard:'model_report_v4_content_json',module:'models-v4.mjs',
    make:'makeModelsCapsuleV4',replay:'replayModelsCapsuleV4',verify:'verifyModelsV4',fixtures:[
      ['models-v4-register.json',{}],['register-cycle.json',{}],
      ['models-v4-list.json',{listProfile:'captured-list-prefix-state/v2'}],
      ['relation-atomic-point.json',{relationProfile:'captured-relation-row-slots/v1'}]]},
  {name:'relation',api:'classifyRelationModelsV4',native:'classify_relation_models_v4_native',text:'classify_relation_models_v4_json',
    normalizer:'relation_model_options_v4_content_json',guard:'relation_model_report_v4_content_json',module:'relation-models-v4.mjs',
    make:'makeRelationModelsCapsuleV4',replay:'replayRelationModelsCapsuleV4',verify:'verifyRelationModelsV4',fixtures:[
      ['relation-atomic-point.json',{}],['relation-predicate-categories.json',{}]]},
];
const input=name=>readFileSync(resolve(root,'examples',name),'utf8');
function normalized(variant,options){const value=JSON.parse(core[variant.normalizer](JSON.stringify(options)));assert.equal(value.valid,true);return JSON.stringify(value.options);}
function original(variant,source,options){const text=core[variant.text](source,normalized(variant,options));const value=JSON.parse(core[variant.guard](text));assert.equal(value.valid,true);return {text,report:value.value};}
function thrown(fn){try{fn();return null;}catch(error){return {type:error.constructor.name,message:error.message};}}

for(const variant of variants){
  check(variant.name+' exports a native output bridge',()=>assert.equal(typeof core[variant.native],'function'));
  for(const [file,defaults]of variant.fixtures){
    for(const extra of [{},{models:'elle-core'},{maxSourceChecks:0},{maxStates:0},{maxStates:1},{maxEdgeChecks:1}]){
      const options={...defaults,...extra},source=input(file),label=variant.name+' '+file+' '+JSON.stringify(extra);
      check(label+' full report, evidence and runtime counters equal text transport',()=>{
        const expected=original(variant,source,options),native=core[variant.native](source,normalized(variant,options));
        assert.notEqual(native,null,'exercise native output rather than fallback');
        assert.deepEqual(native,expected.report);
        assert.equal(JSON.stringify(native),JSON.stringify(expected.report),'all fields and insertion order');
        const report=sdk[variant.api](source,options);
        assert.deepEqual(report,expected.report);
        assert.equal(Object.getPrototypeOf(report),Object.prototype);
        assert.equal(sdk[variant.verify](source,report,options).valid,true);
      });
    }
    check(variant.name+' '+file+' capsules retain original pretty text and independently replay',()=>{
      const source=input(file),expected=original(variant,source,defaults);
      const text=sdk[variant.make](source,defaults),capsule=JSON.parse(text);
      assert.equal(capsule.reportText,expected.text);
      assert.equal(sdk[variant.replay](text,defaults).valid,true);
      const report=sdk[variant.api](source,defaults);report.models[0].status='altered';
      assert.equal(sdk[variant.verify](source,report,defaults).valid,false);
    });
  }
  const [fixture,defaults]=variant.fixtures[0],source=input(fixture);
  check(variant.name+' repeated calls do not share mutable report collections',()=>{
    const before=JSON.stringify(sdk[variant.api](source,defaults));
    const report=sdk[variant.api](source,defaults);report.models.length=0;
    assert.equal(JSON.stringify(sdk[variant.api](source,defaults)),before);
  });
  // Scoped modules retain every other export. No production file is modified.
  const scratch=mkdtempSync(resolve(tmpdir(),'mtw-native-model-'));
  for(const mode of ['missing','null','throws','native-only']){
    const folder=resolve(scratch,mode);mkdirSync(folder);
    const overrides=[variant.text,...(mode==='missing'? [variant.native]:mode==='native-only'? [variant.guard]:[variant.native])];
    const names=Object.keys(core).filter(name=>!overrides.includes(name));
    assert(names.every(name=>/^[A-Za-z_$][\w$]*$/.test(name)));
    const actual=JSON.stringify(pathToFileURL(coreFile).href);
    let bridge=`import * as actual from ${actual};\nexport {${names.join(',')}} from ${actual};\nexport let textCalls=0;\n`;
    bridge+=`export function ${variant.text}(...args){textCalls++;return actual.${variant.text}(...args);}\n`;
    if(mode==='null')bridge+=`export function ${variant.native}(){return null;}\n`;
    if(mode==='throws')bridge+=`export function ${variant.native}(){throw new Error('native unavailable');}\n`;
    if(mode==='native-only')bridge+=`export function ${variant.guard}(){throw new Error('unexpected report reparse');}\n`;
    writeFileSync(resolve(folder,'core.mjs'),bridge,{flag:'wx'});
    writeFileSync(resolve(folder,variant.module),readFileSync(resolve(runtime,variant.module)),{flag:'wx'});
    const scoped=await import(pathToFileURL(resolve(folder,variant.module)));
    const observed=await import(pathToFileURL(resolve(folder,'core.mjs')));
    check(variant.name+' '+mode+' uses the expected output transport',()=>{
      assert.deepEqual(scoped[variant.api](source,defaults),original(variant,source,defaults).report);
      assert.equal(observed.textCalls,mode==='native-only'?0:1);
    });
    if(mode!=='native-only')for(const [badSource,badOptions]of [['{',defaults],['{}',defaults],[source,{models:[]}],[source,'{"models":[],"mo\\u0064els":[]}']]){
      check(variant.name+' '+mode+' retains text validation errors '+JSON.stringify([badSource.slice(0,20),badOptions]),()=>{
        const expected=thrown(()=>sdk[variant.api](badSource,badOptions));
        assert.notEqual(expected,null);
        assert.deepEqual(thrown(()=>scoped[variant.api](badSource,badOptions)),expected);
      });
    }
  }
}
// Source nesting can fit its own guard but exceed the report guard after the
// observations/history wrapper. Native output must not widen that old limit.
for(const depth of [55,56,57,58,61]){
  check('register original condition nesting '+depth+' retains report guard and verification compatibility',()=>{
    const source=JSON.parse(input('models-v4-register.json'));
    let predicate=null;for(let i=0;i<depth;i++)predicate=[predicate];
    source.events.splice(2,0,{kind:'condition',tx:'A',predicate,matched:false});
    source.events=source.events.map((event,index)=>({...event,seq:index+1,time:index}));
    const text=JSON.stringify(source),variant=variants[0],options={maxSourceChecks:0};
    const optionText=normalized(variant,options),wire=core[variant.text](text,optionText);
    const guard=JSON.parse(core[variant.guard](wire));
    if(guard.valid===true){
      assert.deepEqual(sdk[variant.api](text,options),guard.value);
      assert.equal(sdk[variant.verify](text,guard.value,options).valid,true);
    }else{
      assert.equal(core[variant.native](text,optionText),null);
      assert.deepEqual(thrown(()=>sdk[variant.api](text,options)),{type:'TypeError',message:guard.error});
    }
  });
}
assert.equal(digest(coreFile),coreSha256);
const receipt={format:'moontxnwitness-native-model-transport-check/v1',passed:true,tests:results.length,results,
  coreSha256,modelSdkSha256:digest(resolve(runtime,'models-v4.mjs')),relationSdkSha256:digest(resolve(runtime,'relation-models-v4.mjs')),
  runtimeUnchanged:true,legacyCapsuleTextUnchanged:true,formalPerformanceMeasurement:false};
if(receiptArg)writeFileSync(resolve(receiptArg),JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify(receiptArg?{passed:true,tests:results.length,coreSha256}:receipt));
