import { createHash } from 'node:crypto';
import { readdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
export function sourceFingerprint(root) {
  const names=['moon.mod'];
  function visit(folder){for(const entry of readdirSync(resolve(root,folder),{withFileTypes:true})){
    const name=folder+'/'+entry.name;
    if(entry.isDirectory())visit(name);
    else if(name.endsWith('.mbt') || entry.name==='moon.pkg')names.push(name);
  }}
  visit('src');
  const h=createHash('sha256');for(const name of names.sort()){h.update(name+'\0');h.update(readFileSync(resolve(root,name)));h.update('\0');}
  return h.digest('hex');
}
