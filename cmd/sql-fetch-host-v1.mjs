// Independent supplied-observation consistency only; never a source provenance grant.
export const SQL_FETCH_V1_LIMITS=Object.freeze({configBytes:262144,executionBytes:1048576,nativeBytes:524288,deliveriesBytes:2097152,optionsBytes:8192,reportBytes:33554432});
function text(value,maximum,label){
 if(typeof value!=='string'){
  let nodes=0;const active=new Set();
  function visit(item,depth){
   if(++nodes>65536||depth>64)throw new TypeError(label+' exceeds structured-input budget');
   if(typeof item==='number'&&!Number.isSafeInteger(item))throw new TypeError('Exact raw JSON text required for unsafe integers');
   if(item&&typeof item==='object'){
    if(active.has(item)||(!Array.isArray(item)&&![Object.prototype,null].includes(Object.getPrototypeOf(item))))throw new TypeError('Materialized plain JSON required');
    active.add(item);for(const v of Object.values(item))visit(v,depth+1);active.delete(item);
   }else if(!['string','boolean','number'].includes(typeof item)&&item!==null)throw new TypeError('Materialized JSON scalars required');
  }
  visit(value,0);
 }
 const raw=typeof value==='string'?value:JSON.stringify(value);
 if(typeof raw!=='string'||Buffer.byteLength(raw,'utf8')>maximum||Buffer.from(raw,'utf8').toString('utf8')!==raw)throw new TypeError(label+' is missing, oversized or contains malformed Unicode');
 return raw;
}
export function createSQLFetchV1(core) {
  for (const name of ["verify_configured_fetch_v1_json"]) if (typeof core[name]!=='function') throw new TypeError('Missing standalone-compatible SQL entry '+name);
  const {verify_configured_fetch_v1_json}=core;
  /** Raw original parameter JSON inside execution preserves full int64 identities. */
  function verifyConfiguredFetchV1(config,execution,native,deliveries,options={}){
   try{
    const args=[[config,262144,'config'],[execution,1048576,'execution'],[native,524288,'native'],[deliveries,2097152,'deliveries'],[options,8192,'options']].map(([v,n,label])=>text(v,n,label));
    return JSON.parse(text(verify_configured_fetch_v1_json(...args),33554432,'report'));
   }catch(error){return {format:'moontxnwitness-configured-fetch-verification/v1',status:'invalid',valid:false,sourceFactsProduced:false,sourceAuthenticated:false,gaps:[error.message]};}
  }
  return Object.freeze({verifyConfiguredFetchV1});
}
