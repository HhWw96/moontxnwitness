#!/usr/bin/env node
// Minimal independent verifier; stdout only, no result mutation or database access.
import {openSync,readSync,closeSync} from 'node:fs';
import {verifySQLCandidateV1,SQL_CANDIDATE_V1_LIMITS} from '../dist/sql-candidate-v1.mjs';
function read(path,maximum){
 const fd=openSync(path,'r'),chunks=[];let size=0;
 try{for(;;){const part=Buffer.alloc(Math.min(65536,maximum+1-size)),n=readSync(fd,part,0,part.length,null);if(!n)break;size+=n;if(size>maximum)throw new Error('Input exceeds bound');chunks.push(part.subarray(0,n));}}
 finally{closeSync(fd);}
 return new TextDecoder('utf-8',{fatal:true}).decode(Buffer.concat(chunks));
}
try{
 const args=process.argv.slice(2);
 if(args.length<4||args.length>5)throw new Error('Usage: node scripts/verify-sql-candidate-v1.mjs CONFIG.json SQL.txt PARAMS.json CANDIDATE.json [OPTIONS.json]');
 const [config,sql,params,candidate,options]=args,limit=SQL_CANDIDATE_V1_LIMITS;
 const report=verifySQLCandidateV1(read(config,limit.configBytes),read(sql,limit.sqlBytes),read(params,limit.parameterBytes),read(candidate,limit.candidateBytes),options?read(options,limit.optionsBytes):{});
 process.stdout.write(JSON.stringify(report,null,2)+'\n');process.exitCode=report.valid===true?0:report.status==='unknown'?3:2;
}catch(error){process.stderr.write(error.message+'\n');process.exitCode=2;}
