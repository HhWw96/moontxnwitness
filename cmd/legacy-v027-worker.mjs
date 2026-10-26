// Fixed eight-operation protocol; original public027 ESM bytes are never rewritten.
import {pathToFileURL} from 'node:url';
import {resolve} from 'node:path';
import {verifyPublicV027Runtime} from './legacy-v027-runtime.mjs';
const FORMAT='moontxnwitness-historical-worker/v1',MAX_BYTES=384*1024*1024;
const METHODS=Object.freeze({
 'verify-orm':['orm-profile.mjs','verifyOrmProfileV3',2,3,'moontxnwitness-orm-profile-report/v1'],
 'replay-orm':['orm-profile.mjs','replayOrmProfileCapsuleV3',1,1,'moontxnwitness-orm-profile/v1'],
 'verify-classification':['classification.mjs','verifyClassificationV3',2,3,'moontxnwitness-classification-report/v1'],
 'replay-classification':['classification.mjs','replayClassificationCapsuleV3',1,1,'moontxnwitness-classification/v1'],
 'verify-models':['classification-models.mjs','verifyModelsClassificationV3',2,3,'moontxnwitness-isolation-model-report/v1'],
 'replay-models':['classification-models.mjs','replayModelsClassificationCapsuleV3',1,1,'moontxnwitness-isolation-models/v1'],
 'verify-model-profile':['model-profile.mjs','verifyModelProfileV3',2,3,'moontxnwitness-model-profile-report/v1'],
 'replay-model-profile':['model-profile.mjs','replayModelProfileCapsuleV3',1,1,'moontxnwitness-model-profile/v1'],
});
const plain=value=>value!==null&&typeof value==='object'&&!Array.isArray(value);
async function main(){
 if(process.argv.length!==2)throw new Error('Historical worker accepts no command-line selectors');
 const chunks=[];let total=0;for await(const chunk of process.stdin){total+=chunk.length;if(total>MAX_BYTES)throw new Error('Historical request byte budget exceeded');chunks.push(chunk);}
 const bytes=Buffer.concat(chunks),text=bytes.toString('utf8');if(!Buffer.from(text,'utf8').equals(bytes))throw new Error('Historical request UTF-8 differs');
 const request=JSON.parse(text);
 if(!plain(request)||Object.keys(request).sort().join(',')!=='arguments,format,id,operation'||request.format!==FORMAT||!(/^[0-9a-f]{32}$/).test(request.id)||!Array.isArray(request.arguments)||!Object.hasOwn(METHODS,request.operation))throw new Error('Historical protocol differs');
 const args=request.arguments,[name,method,min,max,format]=METHODS[request.operation];if(args.length<min||args.length>max)throw new Error('Historical argument count differs');
 const candidate=request.operation.startsWith('verify-')?args[1]:args[0],header=typeof candidate==='string'?JSON.parse(candidate):candidate;
 if(!plain(header)||header.format!==format||(name==='orm-profile.mjs'?header.engineVersion:header.engine?.version)!=='0.2.7')throw new Error('Historical request must target original public027 engine and format');
 const verified=verifyPublicV027Runtime(),module=await import(pathToFileURL(resolve(verified.runtimeRoot,name)).href);
 if(typeof module[method]!=='function')throw new Error('Historical method absent');
 const result=module[method](...args);if(!plain(result)||typeof result.valid!=='boolean')throw new Error('Historical module did not return a verification result');
 const output=Buffer.from(JSON.stringify({format:FORMAT,id:request.id,result})+'\n');if(output.length>MAX_BYTES)throw new Error('Historical response byte budget exceeded');
 await new Promise((resolve,reject)=>process.stdout.write(output,error=>error?reject(error):resolve()));
}
try{await main();}catch{process.stderr.write('Fixed historical worker refused the request.\n');process.exitCode=2;}
