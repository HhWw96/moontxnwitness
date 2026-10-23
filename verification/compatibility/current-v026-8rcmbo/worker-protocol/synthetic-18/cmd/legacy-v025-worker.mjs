// Fixed private protocol only. Original public25 modules remain unchanged ESM.
import {pathToFileURL} from 'node:url';
import {resolve} from 'node:path';
import {verifyPublicV025Runtime} from './legacy-v025-runtime.mjs';
const FORMAT='moontxnwitness-historical-worker/v1',MAX_BYTES=384*1024*1024;
function plain(value){return value!==null&&typeof value==='object'&&!Array.isArray(value);}
async function main(){
 if(process.argv.length!==2)throw new Error('Historical worker does not accept command-line parameters');
 const chunks=[];let total=0;for await(const chunk of process.stdin){total+=chunk.length;if(total>MAX_BYTES)throw new Error('Historical request byte budget exceeded');chunks.push(chunk);}
 const bytes=Buffer.concat(chunks),text=bytes.toString('utf8');if(!Buffer.from(text,'utf8').equals(bytes))throw new Error('Historical request UTF-8 differs');
 const request=JSON.parse(text);
 if(!plain(request)||Object.keys(request).sort().join(',')!=='arguments,format,id,operation'||request.format!==FORMAT||!(/^[0-9a-f]{32}$/).test(request.id)||!Array.isArray(request.arguments))throw new Error('Historical protocol differs');
 const args=request.arguments,operation=request.operation;
 const methods={'verify-orm':['orm-profile.mjs','verifyOrmProfileV3',2,3],'replay-orm':['orm-profile.mjs','replayOrmProfileCapsuleV3',1,1],'verify-classification':['classification.mjs','verifyClassificationV3',2,3],'replay-classification':['classification.mjs','replayClassificationCapsuleV3',1,1]};
 if(!Object.hasOwn(methods,operation))throw new Error('Historical operation refused');
 const [name,method,min,max]=methods[operation];if(args.length<min||args.length>max)throw new Error('Historical argument count differs');
 const candidate=operation.startsWith('verify-')?args[1]:args[0],header=typeof candidate==='string'?JSON.parse(candidate):candidate;
 const expectedFormat=operation==='verify-orm'?'moontxnwitness-orm-profile-report/v1':operation==='replay-orm'?'moontxnwitness-orm-profile/v1':operation==='verify-classification'?'moontxnwitness-classification-report/v1':'moontxnwitness-classification/v1';
 if(!plain(header)||header.format!==expectedFormat||(name==='orm-profile.mjs'?header.engineVersion:header.engine?.version)!=='0.2.5')throw new Error('Historical request must target original public25 format and engine');
 const verified=verifyPublicV025Runtime(),module=await import(pathToFileURL(resolve(verified.runtimeRoot,name)).href);
 if(typeof module[method]!=='function')throw new Error('Historical method is absent');
 const result=module[method](...args);if(!plain(result)||typeof result.valid!=='boolean')throw new Error('Historical module did not return a verification result');
 const output=Buffer.from(JSON.stringify({format:FORMAT,id:request.id,result})+'\n');if(output.length>MAX_BYTES)throw new Error('Historical response byte budget exceeded');
 await new Promise((resolve,reject)=>process.stdout.write(output,error=>error?reject(error):resolve()));
}
try{await main();}catch{process.stderr.write('Fixed historical worker refused the request.\n');process.exitCode=2;}
