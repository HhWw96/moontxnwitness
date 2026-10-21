import {createHash} from 'node:crypto';
import {readdirSync,readFileSync,existsSync} from 'node:fs';
import {resolve} from 'node:path';

// Bind the executed sources and shipped runtime, not just the MoonBit module.
// Documentation edits do not require rerunning code; executable edits do.
export function verificationFingerprint(root,{includeDist=true}={}) {
  const names=['moon.mod','package.json'];
  function visit(folder) {
    for(const entry of readdirSync(resolve(root,folder),{withFileTypes:true})) {
      if(entry.name==='__pycache__')continue;
      const name=folder+'/'+entry.name;
      if(entry.isDirectory())visit(name);
      else if(/\.(?:mbt|mjs|py|json|tar\.gz)$/.test(name) || entry.name==='moon.pkg')names.push(name);
    }
  }
  for(const folder of ['cmd','src','scripts','integrations','experiments','fixtures',...(includeDist?['dist']:[])])visit(folder);
  // The independent v3 audits execute these helpers and consume this fixed
  // historical collection. New run receipts stay outside these input paths.
  for(const folder of ['verification/v3/tools','verification/v3/synthetic-dislock-source-closure-v1','verification/business/dislock/v3-647afacfcbe14586b46714bac34c8f30'])if(existsSync(resolve(root,folder)))visit(folder);
  for(const name of ['verification/v3/dislock-explicit-policy-preregistration-2026-10-21.json','verification/v3/dislock-sql-supplement-preregistration-2026-10-21.json'])if(existsSync(resolve(root,name)))names.push(name);
  return Object.fromEntries(names.sort().map(name=>[name,
    createHash('sha256').update(readFileSync(resolve(root,name))).digest('hex')]));
}
