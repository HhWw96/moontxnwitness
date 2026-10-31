import {frozenInputs} from './input-cache.mjs';
import {createHash} from 'node:crypto';
import {readdirSync,readFileSync,existsSync} from 'node:fs';
import {resolve} from 'node:path';

// Bind the executed sources and shipped runtime, not just the MoonBit module.
// Documentation edits do not require rerunning code; executable edits do.
export function verificationFingerprint(root,{includeDist=true}={}) {
  const pinned=frozenInputs(root);
  const indexName=JSON.parse(readFileSync(resolve(root,'scripts/frozen-inputs.json'),'utf8')).index;
  if(typeof indexName!=='string'||!/^[\w.-]+$/.test(indexName))throw Error('Invalid frozen index name');
  const names=['moon.mod','package.json','scripts/'+indexName,...Object.keys(pinned).filter(n=>!n.startsWith('artifacts/'))];
  function visit(folder,bindAll=false) {
    for(const entry of readdirSync(resolve(root,folder),{withFileTypes:true})) {
      if(entry.name==='__pycache__')continue;
      const name=folder+'/'+entry.name;
      if(entry.isDirectory())visit(name,bindAll);
      else if(bindAll || /\.(?:mbt|mjs|cjs|py|json|jsonl|clj|sqlite3|(?:tar|py)\.gz)$/.test(name) || entry.name==='moon.pkg' || entry.name==='requirements.txt')names.push(name);
    }
  }
  for(const folder of ['cmd','src','scripts','integrations','experiments','fixtures',...(includeDist?['dist']:[])])visit(folder);
  if(existsSync(resolve(root,'cmd/legacy/v025')))visit('cmd/legacy/v025',true);
  if(existsSync(resolve(root,'cmd/legacy/v026')))visit('cmd/legacy/v026',true);
  if(existsSync(resolve(root,'cmd/legacy/v027')))visit('cmd/legacy/v027',true);
  if(existsSync(resolve(root,'cmd/legacy/v028')))visit('cmd/legacy/v028',true);
  // The independent v3 audits execute these helpers and consume this fixed
  // historical collection. New run receipts stay outside these input paths.
  if(existsSync(resolve(root,'verification/v3/tools')))visit('verification/v3/tools');
  for(const folder of ['verification/v3/synthetic-dislock-source-closure-v1','verification/business/dislock/v3-647afacfcbe14586b46714bac34c8f30','verification/faults/mlflow/run-c7227fba032f4c92b127b7357252107c'])if(existsSync(resolve(root,folder)))visit(folder,true);
  for(const folder of ['verification/configured-user-profile/v024-initial','verification/capture-persistence/v023-initial'])if(existsSync(resolve(root,folder)))visit(folder,true);
  if(existsSync(resolve(root,'verification/model-profile-v3/v027-initial')))visit('verification/model-profile-v3/v027-initial',true);
  for(const name of ['verification/v3/dislock-explicit-policy-preregistration-2026-10-21.json','verification/v3/dislock-sql-supplement-preregistration-2026-10-21.json'])if(existsSync(resolve(root,name)))names.push(name);
  names.push('examples/postgres-requirements.txt');
  names.push('verification/formal-harness-fix/reproduction/original-full-capture-cost.yml.gz');
  names.push('examples/orm-requirements.txt');
  names.push('examples/list-cycle.json', 'examples/list-roundtrip.mjs');
  names.push('examples/relation-source-closure.json', 'examples/relation-roundtrip.mjs');
  names.push('examples/register-cycle.json', 'examples/register-cycle-roundtrip.mjs');
  names.push('examples/mlflow-http-roundtrip.mjs');
  names.push('examples/v4-anomalies-roundtrip.mjs');
  names.push('examples/execution-roundtrip.mjs');
  names.push('examples/orm-profile-roundtrip.mjs');
  names.push('examples/model-profile-roundtrip.mjs');
  names.push('examples/classification-roundtrip.mjs');
  names.push('examples/classification-models-roundtrip.mjs');
  const result=Object.fromEntries([...new Set(names)].sort().map(name=>[name,
    createHash('sha256').update(readFileSync(resolve(root,name))).digest('hex')]));
  for(const[name,record]of Object.entries(pinned))if(!name.startsWith('artifacts/')&&result[name]!==record.sha256)throw Error('Frozen input differs from pinned bytes: '+name);
  return result;
}
