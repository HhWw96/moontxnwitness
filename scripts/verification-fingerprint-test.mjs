import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,symlinkSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {resolve,dirname,sep} from 'node:path';
import {inferenceExampleSourceFiles} from './verification-fingerprint.mjs';

const EXAMPLE='examples/inference-modules-v4';
const created=resolve(mkdtempSync(resolve(tmpdir(),'mtw-verification-fingerprint-')));
let checks=0;
function fixture(name) {
  const root=resolve(created,name);
  mkdirSync(resolve(root,EXAMPLE),{recursive:true});
  const write=(name,text='bound original bytes')=>{
    const path=resolve(root,EXAMPLE,name);
    assert(path.startsWith(resolve(root,EXAMPLE)+sep));
    mkdirSync(dirname(path),{recursive:true});
    writeFileSync(path,text);
  };
  for(const name of ['moon.mod','moon.pkg','moon.work','main.mbt','README.md','local-helper.mjs','fixture.bin'])write(name);
  return {root,write};
}
function bindings(root) {
  return Object.fromEntries(inferenceExampleSourceFiles(root).map(name=>[name,createHash('sha256').update(readFileSync(resolve(root,name))).digest('hex')]));
}
try {
  const {root,write}=fixture('generated-directories');
  const before=bindings(root);
  for(let i=0;i<9;i++)write('_build/wasm-gc/debug/generated-'+i+'.bin','platform-specific compiled bytes '+i);
  write('.mooncakes/dependency/package.json','{"generated":true}');
  assert.deepEqual(bindings(root),before);
  checks++;
  for(const name of ['nested/_build/source.mbt','nested/.mooncakes/source.mbt','_build-source/source.mbt','.mooncakes-source/source.mbt'])write(name);
  const nested=bindings(root);
  for(const name of ['nested/_build/source.mbt','nested/.mooncakes/source.mbt','_build-source/source.mbt','.mooncakes-source/source.mbt'])assert(Object.hasOwn(nested,EXAMPLE+'/'+name));
  checks++;
  write('main.mbt','changed executable source');
  assert.notEqual(bindings(root)[EXAMPLE+'/main.mbt'],before[EXAMPLE+'/main.mbt']);
  assert(Object.hasOwn(nested,EXAMPLE+'/fixture.bin'));
  checks++;
  for(const name of ['_build','.mooncakes']) {
    const file=fixture('same-name-file-'+name.replace('.',''));
    file.write(name,'a file cannot impersonate a generated directory');
    assert.throws(()=>inferenceExampleSourceFiles(file.root),/must be a real directory/);
    checks++;
    const linked=fixture('same-name-link-'+name.replace('.',''));
    const target=resolve(created,'link-target-'+name.replace('.',''));
    mkdirSync(target);
    writeFileSync(resolve(target,'must-not-be-traversed.mbt'),'external source');
    symlinkSync(target,resolve(linked.root,EXAMPLE,name),process.platform==='win32'?'junction':'dir');
    assert.throws(()=>inferenceExampleSourceFiles(linked.root),/must be a real directory/);
    checks++;
  }
  console.log(JSON.stringify({verificationFingerprintExampleBoundaries:true,checks,generatedDirectoriesIgnoredOnlyAtExampleRoot:true}));
} finally {
  // Delete only this process's newly created, explicitly bounded test tree.
  assert(created.startsWith(resolve(tmpdir())+sep));
  assert(created.slice(created.lastIndexOf(sep)+1).startsWith('mtw-verification-fingerprint-'));
  rmSync(created,{recursive:true,force:true});
}
