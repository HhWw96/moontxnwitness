#!/usr/bin/env node
import {readFileSync,writeFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {createConfiguredSessionV4} from '../cmd/configured-session-v4.mjs';
const args=process.argv.slice(2),flags={};
for(let i=0;i<args.length;i+=2){if(!['--runtime','--runtime-sha256','--input','--options','--report','--output'].includes(args[i])||args[i+1]===undefined||Object.hasOwn(flags,args[i]))throw new Error('Use unique --runtime CORE --runtime-sha256 SHA --input BUNDLE [--options OPTIONS] [--report REPORT | --output NEWREPORT]');flags[args[i]]=args[i+1];}
for(const key of ['--runtime','--runtime-sha256','--input'])if(!flags[key])throw new Error('Missing '+key);
if(flags['--report']&&flags['--output'])throw new Error('Verification and new output are separate operations');
const read=(name,max)=>{const b=readFileSync(resolve(name));if(b.length>max)throw new Error('Input exceeds declared bound');return b;};
const utf8=bytes=>new TextDecoder('utf-8',{fatal:true}).decode(bytes);
const moduleBytes=read(flags['--runtime'],16*1024*1024),sha=createHash('sha256').update(moduleBytes).digest('hex');
if(!/^[0-9a-f]{64}$/.test(flags['--runtime-sha256'])||sha!==flags['--runtime-sha256'])throw new Error('Caller-pinned runtime bytes differ');
// The compiled MoonBit bridge is self-contained. Import exactly the hashed bytes,
// not a mutable pathname between a hash check and module execution.
if(/^\s*import\b/m.test(utf8(moduleBytes)))throw new Error('Expected a self-contained compiled diagnostic bridge');
const core=await import('data:text/javascript;base64,'+moduleBytes.toString('base64'));
const sdk=createConfiguredSessionV4(core),input=utf8(read(flags['--input'],32*1024*1024)),options=flags['--options']?utf8(read(flags['--options'],8192)):'{}';
if(flags['--report']){const valid=sdk.verifyConfiguredSessionV4(input,utf8(read(flags['--report'],64*1024*1024)),options);process.stdout.write(JSON.stringify({valid,runtimeSha256:sha,isolationAnalysisReady:false})+'\n');if(!valid)process.exitCode=2;}
else {const result=sdk.diagnoseConfiguredSessionTextV4(input,options);if(flags['--output']){writeFileSync(resolve(flags['--output']),result+'\n',{flag:'wx'});const r=JSON.parse(result);process.stdout.write(JSON.stringify({status:r.status,resultConsistency:r.resultConsistency,initialSourceStatus:r.initialSourceStatus,sourceFactsProduced:false,isolationAnalysisReady:false,runtimeSha256:sha})+'\n');}else process.stdout.write(result+'\n');}
