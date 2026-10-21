// Remote-only actual MoonBit/Elle smoke comparison. Never interprets Elle rules.
import {readFileSync,writeFileSync,existsSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';

const [sdkArg,inputArg,preparedArg,elleArg,outputArg]=process.argv.slice(2);
if(!outputArg)throw Error('Usage: compare-tool.mjs SDK RAW_INPUT ADAPTER_RECEIPT ELLE_RESULT NEW_RECEIPT');
const output=resolve(outputArg);if(existsSync(output))throw Error('Refuse old comparison receipt');
const inputBytes=readFileSync(resolve(inputArg)),adapter=JSON.parse(readFileSync(resolve(preparedArg),'utf8'));
const raw=JSON.parse(inputBytes),elle=JSON.parse(readFileSync(resolve(elleArg),'utf8'));
const sha=x=>createHash('sha256').update(x).digest('hex');
const runtimeRoot=dirname(resolve(sdkArg));
const build=JSON.parse(readFileSync(resolve(runtimeRoot,'build-manifest.json'),'utf8'));
const coreSha=sha(readFileSync(resolve(runtimeRoot,'core.mjs'))),captureSha=sha(readFileSync(resolve(runtimeRoot,'capture-core.mjs')));
if(coreSha!==build.coreSha256||captureSha!==build.captureCoreSha256)throw Error('Actual runtime/build-manifest binding differs');
if(elle.inputEdnSha256!==sha(readFileSync(resolve(dirname(resolve(preparedArg)),'requests.edn'))))throw Error('Actual Elle input binding differs');
const sdk=await import(pathToFileURL(resolve(sdkArg)).href);
if(sha(inputBytes)!==adapter.sourceInputSha256)throw Error('Original input/adapter binding differs');
const eligible=adapter.cases.filter(x=>x.disposition==='eligible').map(x=>x.id).sort();
const actualIds=elle.cases.map(x=>x.id).sort();
if(new Set(actualIds).size!==actualIds.length||JSON.stringify(eligible)!==JSON.stringify(actualIds))throw Error('Actual Elle case set differs');
const rows=[];
for(const item of raw.cases){
  const adapted=adapter.cases.find(x=>x.id===item.id);
  if(!adapted)throw Error('Missing adapter case');
  if(adapted.disposition!=='eligible'){
    rows.push({id:item.id,disposition:adapted.disposition,checkerExecuted:false,
      passed:adapted.disposition===item.expected.adapter});continue;
  }
  try{
    const actual=elle.cases.find(x=>x.id===item.id);if(!actual)throw Error('Missing actual Elle result');
    const report=sdk.analyzeV3(item.input),verified=sdk.verifyV3(item.input,report);
    const unknown=actual.valid==='unknown';
    rows.push({id:item.id,disposition:'eligible',actualElleResult:actual.valid,
      actualMoonBitStatus:report.status,knownCoverageDifference:unknown,
      passed:actual.passed===true&&report.status===item.expected.toolStatus&&verified.valid===true,
      report,verification:verified});
  }catch(error){rows.push({id:item.id,passed:false,error:String(error)});}
}
const receipt={schema:1,kind:'actual-Elle-MoonBit-raw-smoke',passed:adapter.passed===true&&elle.passed===true&&rows.every(x=>x.passed),
  actualElleResultConsumed:true,actualMoonBitExecuted:true,actualDatabaseExecution:false,formalPerformanceMeasurement:false,
  sixModelParityClaimed:false,arbitrarySqlCoverageClaimed:false,
  actualDualCheckerCases:eligible.length,adapterOnlyOutsideCases:adapter.cases.filter(x=>x.disposition==='outside').length,
  adapterOnlyInvalidCases:adapter.cases.filter(x=>x.disposition==='invalid').length,
  originalInputSha256:sha(inputBytes),sdkFileSha256:sha(readFileSync(resolve(sdkArg))),
  actualBuildManifest:build,actualCoreSha256:coreSha,actualCaptureCoreSha256:captureSha,
  elleResultSha256:sha(readFileSync(resolve(elleArg))),cases:rows};
writeFileSync(output,JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({passed:receipt.passed,cases:rows.length,receiptSha256:sha(readFileSync(output))}));
if(!receipt.passed)process.exitCode=1;
