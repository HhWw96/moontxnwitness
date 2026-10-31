import {openSync,readSync,fstatSync,closeSync} from 'node:fs';
import {verifyConfiguredFetchV1 as verify,SQL_FETCH_V1_LIMITS as limits} from '../dist/sql-fetch-v1.mjs';
const paths=process.argv.slice(2);
if(paths.length<4||paths.length>5){console.error('Usage: node scripts/verify-configured-fetch-v1.mjs CONFIG EXECUTION NATIVE DELIVERIES [OPTIONS]');process.exit(2);}
function read(path,cap){
 const fd=openSync(path,'r');try{
  const info=fstatSync(fd);if(!info.isFile()||info.size>cap)throw new Error('Input exceeds explicit budget or is not a regular file');
  const bytes=Buffer.alloc(cap+1);let n=0,count;while(n<=cap&&(count=readSync(fd,bytes,n,cap+1-n,null))>0)n+=count;
  if(n>cap)throw new Error('Input exceeds explicit budget');const slice=bytes.subarray(0,n),text=slice.toString('utf8');
  if(!Buffer.from(text,'utf8').equals(slice))throw new Error('Invalid UTF8 input');return text;
 }finally{closeSync(fd);}
}
try{
 const caps=[limits.configBytes,limits.executionBytes,limits.nativeBytes,limits.deliveriesBytes,limits.optionsBytes];
 const inputs=paths.map((path,index)=>read(path,caps[index]));if(inputs.length===4)inputs.push('{}');
 const report=verify(...inputs);process.stdout.write(JSON.stringify(report)+'\n');process.exitCode=report.status==='matched'?0:['partial','unknown'].includes(report.status)?3:2;
}catch(error){console.error(error.message);process.exitCode=2;}
