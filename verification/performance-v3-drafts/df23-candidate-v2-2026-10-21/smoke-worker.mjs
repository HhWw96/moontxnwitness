import fs from 'node:fs';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {performance} from 'node:perf_hooks';
const [enginePath,fixturePath,outputPath]=process.argv.slice(2),hash=x=>createHash('sha256').update(x).digest('hex');
assert.ok(enginePath&&fixturePath&&outputPath&&!fs.existsSync(outputPath));
const load=performance.now(),core=await import(pathToFileURL(enginePath));const loadMs=performance.now()-load;
const fixture=JSON.parse(fs.readFileSync(fixturePath)),text=JSON.stringify(fixture.history);
let last;const run=()=>{last=fixture.operation==='shrink'?core.shrink_options_json(text,'{}'):core.analyze_options_json(text,'{}');return JSON.parse(last);};
const cold=performance.now();run();const firstMs=performance.now()-cold;
run();const rows=[];
for(let i=0;i<3;i++){const start=performance.now(),output=run();rows.push(performance.now()-start);assert.equal(output.status,fixture.status);}
const medianMs=[...rows].sort((a,b)=>a-b)[1];
const result={schema:1,diagnosticOnly:true,formalReleaseGateApplicable:false,scenario:fixture.name,version:core.version(),engineSha256:hash(fs.readFileSync(enginePath)),fixtureSha256:hash(fs.readFileSync(fixturePath)),workerSha256:hash(fs.readFileSync(new URL(import.meta.url))),loadMs,firstMs,medianMs,rows,peakRssKiB:process.resourceUsage().maxRSS,outputSha256:hash(last),outputBytes:Buffer.byteLength(last)};
fs.writeFileSync(outputPath,JSON.stringify(result,null,2)+'\n',{flag:'wx'});console.log(JSON.stringify(result));
