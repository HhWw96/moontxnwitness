import {createHash} from 'node:crypto';
import {readdirSync,readFileSync,existsSync} from 'node:fs';
import {resolve} from 'node:path';

// Bind the executed sources and shipped runtime, not just the MoonBit module.
// Documentation edits do not require rerunning code; executable edits do.
export function verificationFingerprint(root,{includeDist=true}={}) {
  const names=['moon.mod','package.json'];
  function visit(folder,bindAll=false) {
    for(const entry of readdirSync(resolve(root,folder),{withFileTypes:true})) {
      if(entry.name==='__pycache__')continue;
      const name=folder+'/'+entry.name;
      if(entry.isDirectory())visit(name,bindAll);
      else if(bindAll || /\.(?:mbt|mjs|py|json|jsonl|clj|sqlite3|(?:tar|py)\.gz)$/.test(name) || entry.name==='moon.pkg' || entry.name==='requirements.txt')names.push(name);
    }
  }
  for(const folder of ['cmd','src','scripts','integrations','experiments','fixtures',...(includeDist?['dist']:[])])visit(folder);
  // The independent v3 audits execute these helpers and consume this fixed
  // historical collection. New run receipts stay outside these input paths.
  if(existsSync(resolve(root,'verification/v3/tools')))visit('verification/v3/tools');
  for(const folder of ['verification/v3/synthetic-dislock-source-closure-v1','verification/business/dislock/v3-647afacfcbe14586b46714bac34c8f30','verification/faults/mlflow/run-c7227fba032f4c92b127b7357252107c'])if(existsSync(resolve(root,folder)))visit(folder,true);
  for(const folder of ['verification/configured-user-profile/v024-initial','verification/capture-persistence/v023-initial'])if(existsSync(resolve(root,folder)))visit(folder,true);
  if(existsSync(resolve(root,'verification/model-profile-v3/v027-initial')))visit('verification/model-profile-v3/v027-initial',true);
  for(const name of ['verification/v3/dislock-explicit-policy-preregistration-2026-10-21.json','verification/v3/dislock-sql-supplement-preregistration-2026-10-21.json'])if(existsSync(resolve(root,name)))names.push(name);
  names.push('examples/postgres-requirements.txt');
  names.push('examples/orm-requirements.txt');
  names.push('examples/list-cycle.json', 'examples/list-roundtrip.mjs');
  names.push('examples/relation-source-closure.json', 'examples/relation-roundtrip.mjs');
  names.push('examples/register-cycle.json', 'examples/register-cycle-roundtrip.mjs');
  names.push('examples/execution-roundtrip.mjs');
  names.push('examples/orm-profile-roundtrip.mjs');
  names.push('examples/model-profile-roundtrip.mjs');
  names.push('examples/classification-roundtrip.mjs');
  return Object.fromEntries(names.sort().map(name=>[name,
    createHash('sha256').update(readFileSync(resolve(root,name))).digest('hex')]));
}
