import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';import {resolve} from 'node:path';import {createHash} from 'node:crypto';
import {parserCases} from './parser-inputs.mjs';import {analysisCases} from './analysis-inputs.mjs';import {projectMetadata,projectionGuards} from './metadata-projection.mjs';
const sha=b=>createHash('sha256').update(b).digest('hex'),load=p=>JSON.parse(readFileSync(p));
const typedJson=value=>JSON.stringify(logicalHistory(value),(_key,item)=>typeof item==='bigint'?{'$moonbitInt64':item.toString()}:item);
function fields(value,names){assert.deepEqual(Object.keys(value).sort(),names.slice().sort());}
function mapContents(map,valueCheck){
  const entries=map.entries.filter(item=>item!==undefined);
  assert.equal(entries.length,map.size,'Every occupied map entry is represented');
  const seen=new Set();
  const logical=entries.map(item=>{assert.equal(typeof item.key,'string');assert.equal(seen.has(item.key),false);seen.add(item.key);valueCheck(item.value);return[item.key,item.value];});
  return logical.sort((a,b)=>a[0]<b[0]?-1:a[0]>b[0]?1:0);
}
function logicalHistory(h){
  fields(h,['model','initial','version_orders','transactions']);
  const string=value=>assert.equal(typeof value,'string');
  const option=value=>{if(value===undefined)return {'$optionNone':true};assert.equal(typeof value,'bigint');return value;};
  return {model:h.model,initial:mapContents(h.initial,string),
    version_orders:mapContents(h.version_orders,values=>{assert.ok(Array.isArray(values));values.forEach(string);}),
    transactions:h.transactions.map(t=>{
      fields(t,['id','status','ops','start','end']);string(t.id);
      return {id:t.id,status:t.status,ops:t.ops.map(op=>{fields(op,['kind','key','version']);string(op.key);string(op.version);return {kind:op.kind,key:op.key,version:op.version};}),start:option(t.start),end:option(t.end)};
    })};
}

export function runParserAndAnalysis({here,output,oracle15,baseline17,current20,check,retain}){
 check('metadata-projection-retains-all-nonheader-characters-and-business-versions',projectionGuards);
 check('original2542-full-typed-and-error-expectations-frozen15-legacy-actual17-actual20',()=>{
  const rows=parserCases(),expected=load(resolve(here,'provenance/parser/full-parser-difference-v3.json'));assert.equal(rows.length,2542);assert.equal(expected.checked,2542);assert.equal(expected.valid,368);assert.equal(expected.invalid,2174);const results=[];let valid=0,invalid=0;
  for(let i=0;i<rows.length;i++){
   const {text,requiredFast}=rows[i],e=expected.cases[i];let oldFlags,beforeFlags,afterFlags,oldOutput,beforeOutput,afterOutput;
   try{
    assert.equal(e.index,i);assert.equal(sha(text),e.inputSha256);assert.equal(text.length,e.inputCodeUnits);
    oldFlags=oracle15.benchmark_parser_agreement(text);beforeFlags=baseline17.benchmark_parser_agreement(text);afterFlags=current20.benchmark_parser_agreement(text);
    assert.equal(sha(oldFlags),e.flagsSha256);assert.equal(beforeFlags,oldFlags);assert.equal(afterFlags,oldFlags);const flags=JSON.parse(oldFlags);assert.equal(flags.agrees,true);if(requiredFast)assert.equal(flags.fastPath,true);
    if(flags.referenceValid){assert.equal(e.kind,'complete-typed-history');oldOutput=typedJson(oracle15.benchmark_parse(text));assert.equal(typedJson(oracle15.benchmark_parse_balanced(text)),oldOutput);beforeOutput=typedJson(baseline17.benchmark_parse_balanced(text));afterOutput=typedJson(current20.benchmark_parse_balanced(text));assert.equal(typedJson(baseline17.benchmark_parse(text)),oldOutput);assert.equal(typedJson(current20.benchmark_parse(text)),oldOutput);assert.equal(beforeOutput,oldOutput);assert.equal(afterOutput,oldOutput);valid++;}
    else{assert.equal(e.kind,'complete-public-error');oldOutput=oracle15.analyze_json(text);beforeOutput=baseline17.analyze_json(text);afterOutput=current20.analyze_json(text);const oldBody=projectMetadata(oldOutput,'0.1.5','legacy-parser-invalid').projectedText;assert.equal(projectMetadata(beforeOutput,'0.1.7','legacy-parser-invalid').projectedText,oldBody);assert.equal(projectMetadata(afterOutput,'0.2.0','legacy-parser-invalid').projectedText,oldBody);invalid++;}
    assert.equal(sha(oldOutput),e.outputSha256);assert.equal(Buffer.byteLength(oldOutput),e.outputBytes);results.push({index:i,inputSha256:e.inputSha256,kind:e.kind,originalOutputSha256:e.outputSha256,actual17OutputSha256:sha(beforeOutput),actual20OutputSha256:sha(afterOutput)});
   }catch(error){writeFileSync(resolve(output,'parser2542-first-failure.json'),JSON.stringify({index:i,text,expected:e,oldFlags,beforeFlags,afterFlags,oldOutput,beforeOutput,afterOutput,error:String(error),stack:error.stack},null,2)+'\n',{flag:'wx'});throw error;}
  }
  assert.equal(valid,368);assert.equal(invalid,2174);retain('parser2542-results.json',{passed:true,checked:2542,valid,invalid,oldExpectedHashesUnchanged:true,cases:results});return{checked:2542,valid,invalid,typedHistoryComplete:true,privateMapBucketLayoutExcluded:true,invalidEngineProjectionOnly:'/version'};
 });
 check('original117-raw-output-frozen15-hashes-and-full-actual17-vs-actual20-byte-projection',()=>{
  const rows=analysisCases(here),expected=load(resolve(here,'provenance/parser/complete-byte-equivalence-current.json'));assert.equal(expected.checks,117);const results=[];
  for(let i=0;i<rows.length;i++){
   const row=rows[i],e=expected.cases[i];let original,before,after;
   try{
    assert.equal(row.name,e.name);assert.equal(sha(row.input),e.inputSha256);assert.equal(sha(row.optionsText),e.optionsSha256);
    original=oracle15[row.fn](row.input,row.optionsText);assert.equal(sha(original),e.outputSha256);assert.equal(Buffer.byteLength(original),e.outputBytes);
    before=baseline17[row.fn](row.input,row.optionsText);after=current20[row.fn](row.input,row.optionsText);
    const profile=row.fn==='shrink_options_json'?'shrink-options':'analyze-options',a=projectMetadata(original,'0.1.5',profile),b=projectMetadata(before,'0.1.7',profile),c=projectMetadata(after,'0.2.0',profile);
    assert.equal(b.projectedText,a.projectedText,'Frozen17 must preserve every original15 nonheader character');assert.equal(c.projectedText,b.projectedText,'Actual18 must preserve every frozen17 nonheader character');
    retain('analysis117-'+i+'-original15.json',original);retain('analysis117-'+i+'-actual17.json',before);retain('analysis117-'+i+'-actual20.json',after);
    results.push({index:i,name:row.name,fn:row.fn,inputSha256:e.inputSha256,optionsSha256:e.optionsSha256,oldOriginalOutputSha256:e.outputSha256,actual17RawSha256:sha(before),actual20RawSha256:sha(after),projectedSha256:sha(c.projectedText),projectedPaths:c.paths,allOtherOriginalCharactersPreserved:true});
   }catch(error){writeFileSync(resolve(output,'analysis117-first-failure.json'),JSON.stringify({index:i,...row,expected:e,original,before,after,error:String(error),stack:error.stack},null,2)+'\n',{flag:'wx'});throw error;}
  }
  retain('analysis117-results.json',{passed:true,checked:117,completeRawOutputsRetained:true,cases:results});return{checked:117,fullRawBytesBeforeProjectionRetained:true,analysisPaths:['/version'],shrinkPaths:['/version','/report/version'],businessVersionsBudgetsCountsSourcesUnchanged:true};
 });
}
