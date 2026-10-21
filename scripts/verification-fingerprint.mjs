import {createHash} from 'node:crypto';
import {readdirSync,readFileSync} from 'node:fs';
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
  return Object.fromEntries(names.sort().map(name=>[name,
    createHash('sha256').update(readFileSync(resolve(root,name))).digest('hex')]));
}
