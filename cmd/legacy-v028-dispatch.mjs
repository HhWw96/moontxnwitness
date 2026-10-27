// Lightweight, synchronous selection only. Unmatched engines retain existing routes.
import {targets028,assertOperation028} from './legacy-v028-policy.mjs';
import {callLegacyV028} from './legacy-v028.mjs';
export function routeLegacyV028(operation,args,currentVersion){
 if(currentVersion==='0.2.8'||!targets028(operation,args))return {matched:false};
 try{assertOperation028(operation,args);let result=callLegacyV028(operation,args);
  if(['verify-v1v2','replay-v1v2'].includes(operation)&&Object.hasOwn(result,'currentEngine'))result={...result,currentEngine:currentVersion};
  return {matched:true,result};
 }catch(error){return {matched:true,result:{valid:false,reason:'legacy028-unavailable-or-refused: '+error.message}};}
}
