// Synthetic implementation fault tests; no public runtime binding is installed.
import assert from 'node:assert/strict';
import * as fs from 'node:fs';
import {createRequire,syncBuiltinESMExports} from 'node:module';
import {createHash} from 'node:crypto';
import {dirname,resolve,join,relative,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawn,spawnSync} from 'node:child_process';
import {createCompactRuntimeLoader,COMPACT_RUNTIME_LIMITS as LIMITS} from '../cmd/compact-runtime.mjs';

const project=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const digest=value=>createHash('sha256').update(value).digest('hex');
const native=createRequire(import.meta.url)('node:fs');
if(process.argv[2]==='--child'||process.argv[2]==='--child-hold'){
  const pin=JSON.parse(fs.readFileSync(process.argv[4],'utf8'));
  const loader=createCompactRuntimeLoader(pin,{installationRoot:process.argv[3]});
  console.log(JSON.stringify({root:loader.get(),pid:process.pid}));
  if(process.argv[2]==='--child-hold'){
    process.stdin.resume();process.stdin.once('data',()=>{loader.cleanup();process.exit(0);});
  }
}else{
  const parent=resolve(project,'artifacts/compact-runtime-tests');fs.mkdirSync(parent,{recursive:true});
  const disk=fs.statfsSync(parent,{bigint:true});
  assert.ok(disk.bavail*disk.bsize>=BigInt(LIMITS.minimumFreeBytes),'Insufficient test disk headroom');
  const results=[];
  class Skip extends Error{}
  function fixture(){
    const base=fs.mkdtempSync(join(parent,'run-'));
    assert.ok(relative(parent,base)&&!relative(parent,base).startsWith('..'+sep));
    const installation=join(base,'dist'),temporary=join(base,'temporary');
    fs.mkdirSync(installation);fs.mkdirSync(temporary);
    const data={core:Buffer.from('export const originalCore = true;\n'),sdk:Buffer.from("export {originalCore} from './core.mjs';\n")};
    const sources={core:'legacy/v031/core.mjs',sdk:'legacy-components/v032/sdk.mjs'};
    for(const [name,source]of Object.entries(sources)){
      const path=join(installation,...source.split('/'));fs.mkdirSync(dirname(path),{recursive:true});fs.writeFileSync(path,data[name]);
    }
    const row=name=>({bytes:data[name].length,sha256:digest(data[name]),source:sources[name]});
    const pin={version:'0.3.2',files:{'core.mjs':row('core'),'sdk.mjs':row('sdk'),'nested/again.mjs':row('core')}};
    const pinPath=join(base,'synthetic-pin.json');fs.writeFileSync(pinPath,JSON.stringify(pin));
    const loaders=[];
    function loader(value=pin,options={}){
      const instance=createCompactRuntimeLoader(value,{installationRoot:installation,temporaryRoot:temporary,...options});
      loaders.push(instance);return instance;
    }
    function cleanup(){
      for(const instance of loaders)try{instance.cleanup();}catch{}
      const absolute=resolve(base);assert.ok(relative(parent,absolute)&&!relative(parent,absolute).startsWith('..'+sep));
      fs.rmSync(absolute,{recursive:true,force:true});
    }
    return {base,installation,temporary,data,sources,pin,pinPath,loader,cleanup};
  }
  async function check(name,fn){
    const f=fixture();
    try{await fn(f);results.push({name,status:'passed'});}
    catch(error){if(error instanceof Skip)results.push({name,status:'skipped',reason:error.message});else results.push({name,status:'failed',error:error.stack});}
    finally{try{f.cleanup();}catch(error){results.push({name:name+' fixture cleanup',status:'failed',error:error.message});}}
  }
  function fileLink(target,path){
    try{fs.symlinkSync(target,path,'file');}
    catch(error){if(['EPERM','EACCES','ENOTSUP'].includes(error.code))throw new Skip('File symlink creation unavailable on this OS account');throw error;}
  }
  function directoryLink(target,path){fs.symlinkSync(target,path,process.platform==='win32'?'junction':'dir');}
  function patchFs(replacements,fn){
    const originals={};
    for(const [key,value]of Object.entries(replacements)){originals[key]=native[key];native[key]=value;}
    syncBuiltinESMExports();
    try{return fn();}finally{for(const [key,value]of Object.entries(originals))native[key]=value;syncBuiltinESMExports();}
  }
  await check('exact full runtime bytes and inventory with hardlink reuse',f=>{
    const l=f.loader(),root=l.get();assert.equal(l.verify(),root);
    assert.deepEqual(fs.readdirSync(root).sort(),['core.mjs','nested','sdk.mjs']);
    for(const [name,row]of Object.entries(f.pin.files))assert.equal(digest(fs.readFileSync(join(root,...name.split('/')))),row.sha256);
    assert.ok(root.startsWith(f.temporary+sep));assert.notEqual(root,f.installation);
  });
  await check('temporary runtime cannot be placed inside installation',f=>{
    for(const temporaryRoot of [f.installation,join(f.installation,'cache')])
      assert.throws(()=>f.loader(f.pin,{temporaryRoot}),/outside installation/);
    assert.equal(fs.existsSync(join(f.installation,'cache')),false);
  });
  await check('PIN is detached from later caller mutation',f=>{
    const pin=structuredClone(f.pin),l=f.loader(pin);pin.files['core.mjs'].source='../../outside';pin.files['extra.mjs']=pin.files['sdk.mjs'];
    assert.ok(fs.existsSync(join(l.get(),'core.mjs')));
  });
  await check('unreferenced immutable source pool files are inert',f=>{
    fs.writeFileSync(join(f.installation,'legacy/v031/unused.mjs'),'not selected');
    assert.equal(fs.existsSync(join(f.loader().get(),'unused.mjs')),false);
  });
  await check('unsafe destinations and sources are rejected before allocation',f=>{
    for(const name of ['../escape','/absolute','a//b','a/../b','a\\b','a:stream','a.','AUX.txt','a/COM1/x']){
      const pin={version:'0.3.2',files:{[name]:f.pin.files['core.mjs']}};assert.throws(()=>f.loader(pin),/Compact runtime/);
    }
    for(const source of ['core.mjs','../legacy/a','legacy/../a','legacy-components/v033/a','legacy/a:stream']){
      const pin=structuredClone(f.pin);pin.files['core.mjs'].source=source;assert.throws(()=>f.loader(pin),/Compact runtime/);
    }
    assert.deepEqual(fs.readdirSync(f.temporary),[]);
  });
  await check('case aliases and file-directory collisions are rejected',f=>{
    for(const extra of ['CORE.mjs','nested','Nested/other.mjs']){
      const pin=structuredClone(f.pin);pin.files[extra]=pin.files['core.mjs'];assert.throws(()=>f.loader(pin),/collision/);
    }
  });
  await check('member count size total depth and invalid PIN budgets reject early',f=>{
    for(const bytes of [-1,1.5,LIMITS.memberBytes+1,Number.MAX_SAFE_INTEGER]){
      const pin=structuredClone(f.pin);pin.files['core.mjs'].bytes=bytes;assert.throws(()=>f.loader(pin),/budget/);
    }
    const total={version:'0.3.2',files:{}};
    for(let n=0;n<33;n++)total.files['f'+n]={...f.pin.files['core.mjs'],bytes:LIMITS.memberBytes};
    assert.throws(()=>f.loader(total),/budget/);
    const count={version:'0.3.2',files:{}};for(let n=0;n<LIMITS.files+1;n++)count.files['f'+n]=f.pin.files['core.mjs'];
    assert.throws(()=>f.loader(count),/count budget/);
    assert.throws(()=>f.loader({version:'0.3.2',files:{['a/'.repeat(33)+'x']:f.pin.files['core.mjs']}}),/unsafe/);
    assert.deepEqual(fs.readdirSync(f.temporary),[]);
  });
  await check('missing source fails without an incomplete runtime',f=>{
    fs.unlinkSync(join(f.installation,...f.sources.sdk.split('/')));
    assert.throws(()=>f.loader().get());assert.deepEqual(fs.readdirSync(f.temporary),[]);
  });
  await check('changed source before first use is rejected',f=>{
    fs.writeFileSync(join(f.installation,...f.sources.core.split('/')),'changed');
    assert.throws(()=>f.loader().get(),/differs/);assert.deepEqual(fs.readdirSync(f.temporary),[]);
  });
  await check('every call rechecks source and never repairs a poisoned loader',f=>{
    const l=f.loader(),root=l.get(),source=join(f.installation,...f.sources.core.split('/'));
    fs.writeFileSync(source,'changed');assert.throws(()=>l.get(),/differs/);assert.ok(fs.existsSync(root));
    fs.writeFileSync(source,f.data.core);assert.throws(()=>l.get(),/previous validation failed/);
  });
  await check('changed destination remains unchanged after failed verification',f=>{
    const l=f.loader(),root=l.get(),target=join(root,'core.mjs');fs.unlinkSync(target);fs.writeFileSync(target,'foreign destination');
    assert.throws(()=>l.get(),/differs/);assert.equal(fs.readFileSync(target,'utf8'),'foreign destination');
    assert.deepEqual(fs.readFileSync(join(f.installation,...f.sources.core.split('/'))),f.data.core);
    fs.writeFileSync(target,f.data.core);assert.throws(()=>l.get(),/previous validation failed/);
  });
  await check('missing destination is not rebuilt',f=>{
    const l=f.loader(),root=l.get(),target=join(root,'sdk.mjs');fs.unlinkSync(target);
    assert.throws(()=>l.get(),/inventory/);assert.equal(fs.existsSync(target),false);
  });
  await check('extra destination file is refused',f=>{
    const l=f.loader(),root=l.get();fs.writeFileSync(join(root,'extra.mjs'),'extra');assert.throws(()=>l.get(),/unexpected/);
  });
  await check('extra empty destination directory is refused',f=>{
    const l=f.loader(),root=l.get();fs.mkdirSync(join(root,'extra'));assert.throws(()=>l.get(),/unexpected/);
  });
  await check('destination file symlink is refused even with expected bytes',f=>{
    const l=f.loader(),root=l.get(),outside=join(f.base,'outside-file'),target=join(root,'core.mjs');
    fs.writeFileSync(outside,f.data.core);fs.unlinkSync(target);fileLink(outside,target);assert.throws(()=>l.get(),/link/);
  });
  await check('source file symlink is refused even with expected bytes',f=>{
    const outside=join(f.base,'outside-file'),source=join(f.installation,...f.sources.core.split('/'));
    fs.writeFileSync(outside,f.data.core);fs.unlinkSync(source);fileLink(outside,source);assert.throws(()=>f.loader().get(),/shape|link/);
  });
  await check('file link metadata rejection is covered without OS symlink privileges',f=>{
    const source=join(f.installation,...f.sources.core.split('/')),original=fs.lstatSync;
    patchFs({lstatSync(path,...args){const st=original(path,...args);if(resolve(path)===source)return new Proxy(st,{get(target,key){if(key==='isSymbolicLink')return()=>true;return Reflect.get(target,key);}});return st;}},()=>assert.throws(()=>f.loader().get(),/shape|link/));
  });
  await check('source directory junction cannot escape immutable pools',f=>{
    const source=join(f.installation,'legacy/v031'),outside=join(f.base,'outside-source');fs.renameSync(source,outside);directoryLink(outside,source);
    assert.throws(()=>f.loader().get(),/directory link/);
  });
  await check('destination directory junction is rejected',f=>{
    const l=f.loader(),root=l.get(),original=join(root,'nested'),outside=join(f.base,'outside-tree');fs.renameSync(original,outside);directoryLink(outside,original);
    assert.throws(()=>l.get(),/link/);
  });
  await check('readonly installation is neither changed nor used as a cache',f=>{
    const paths=Object.values(f.sources).map(source=>join(f.installation,...source.split('/')));
    for(const path of paths)fs.chmodSync(path,0o444);
    fs.chmodSync(f.installation,0o555);
    const before=paths.map(path=>({mode:fs.statSync(path).mode,links:fs.statSync(path).nlink,sha:digest(fs.readFileSync(path))}));
    const l=f.loader(),root=l.get();l.cleanup();assert.equal(fs.existsSync(root),false);
    assert.deepEqual(paths.map(path=>({mode:fs.statSync(path).mode,links:fs.statSync(path).nlink,sha:digest(fs.readFileSync(path))})),before);
    fs.chmodSync(f.installation,0o700);for(const path of paths)fs.chmodSync(path,0o600);
  });
  await check('hardlink-unavailable filesystem falls back to exclusive verified copies',f=>{
    patchFs({linkSync(){const e=new Error('no hardlinks');e.code='EXDEV';throw e;}},()=>{
      const l=f.loader(),root=l.get();assert.deepEqual(fs.readFileSync(join(root,'core.mjs')),f.data.core);
      assert.notEqual(fs.statSync(join(root,'core.mjs')).ino,fs.statSync(join(f.installation,...f.sources.core.split('/'))).ino);
    });
  });
  await check('partial copy failure removes only this new runtime',f=>{
    const original=fs.writeSync;let writes=0;
    patchFs({linkSync(){const e=new Error('no hardlinks');e.code='EXDEV';throw e;},writeSync(fd,buffer,offset,length,position){
      if(writes++===0)return original(fd,buffer,offset,Math.min(3,length),position);
      const e=new Error('injected disk full');e.code='ENOSPC';throw e;
    }},()=>assert.throws(()=>f.loader().get(),/disk full/));
    assert.deepEqual(fs.readdirSync(f.temporary),[]);
    assert.deepEqual(fs.readFileSync(join(f.installation,...f.sources.core.split('/'))),f.data.core);
  });
  await check('below 500 MiB free refuses temporary writes',f=>{
    patchFs({statfsSync(){return {bavail:BigInt(LIMITS.minimumFreeBytes-1),bsize:1n};}},()=>assert.throws(()=>f.loader().get(),/500 MiB/));
    assert.deepEqual(fs.readdirSync(f.temporary),[]);
  });
  await check('cleanup unlinks an injected child link without touching its target',f=>{
    const l=f.loader(),root=l.get(),outside=join(f.base,'external');fs.mkdirSync(outside);fs.writeFileSync(join(outside,'marker'),'retain');directoryLink(outside,join(root,'injected-link'));
    l.cleanup();assert.equal(fs.existsSync(root),false);assert.equal(fs.readFileSync(join(outside,'marker'),'utf8'),'retain');
  });
  await check('cleanup refuses a replaced runtime root and never follows it',f=>{
    const l=f.loader(),root=l.get(),moved=join(f.temporary,'moved-original'),outside=join(f.base,'external');fs.mkdirSync(outside);fs.writeFileSync(join(outside,'marker'),'retain');
    fs.renameSync(root,moved);directoryLink(outside,root);assert.throws(()=>l.cleanup(),/identity differs/);
    assert.equal(fs.readFileSync(join(outside,'marker'),'utf8'),'retain');
  });
  await check('explicit cleanup is idempotent and a disposed loader cannot rebuild',f=>{
    const l=f.loader(),root=l.get();assert.equal(l.cleanup(),true);assert.equal(l.cleanup(),false);assert.equal(fs.existsSync(root),false);assert.throws(()=>l.get(),/disposed/);
  });
  await check('child process exit automatically recycles only its private tree',f=>{
    const child=spawnSync(process.execPath,[fileURLToPath(import.meta.url),'--child',f.installation,f.pinPath],{encoding:'utf8',windowsHide:true,timeout:15000,env:{...process.env,TEMP:f.temporary,TMP:f.temporary,TMPDIR:f.temporary}});
    assert.equal(child.status,0,child.stderr);const result=JSON.parse(child.stdout);assert.ok(result.root.startsWith(f.temporary+sep));assert.equal(fs.existsSync(result.root),false);
  });
  await check('concurrent parent processes have isolated temporary runtimes',async f=>{
    function child(){
      const p=spawn(process.execPath,[fileURLToPath(import.meta.url),'--child-hold',f.installation,f.pinPath],{windowsHide:true,env:{...process.env,TEMP:f.temporary,TMP:f.temporary,TMPDIR:f.temporary},stdio:['pipe','pipe','pipe']});
      const ready=new Promise((accept,reject)=>{let text='',errors='';const timer=setTimeout(()=>{p.kill();reject(new Error('Child ready timeout'));},15000);p.stderr.on('data',chunk=>{errors+=chunk;});p.on('error',error=>{clearTimeout(timer);reject(error);});p.on('exit',code=>{if(!text.includes('\n')){clearTimeout(timer);reject(new Error(errors||'Child exited '+code));}});p.stdout.on('data',chunk=>{text+=chunk;if(text.includes('\n')){clearTimeout(timer);try{accept(JSON.parse(text.split('\n')[0]));}catch(error){reject(error);}}});});
      return {p,ready};
    }
    const a=child(),b=child();
    try{
      const [first,second]=await Promise.all([a.ready,b.ready]);assert.notEqual(first.root,second.root);assert.notEqual(first.pid,second.pid);
      assert.ok(fs.existsSync(first.root)&&fs.existsSync(second.root));fs.writeFileSync(join(first.root,'parent-one-only'),'extra');
      assert.equal(fs.existsSync(join(second.root,'parent-one-only')),false);
      const exited=p=>new Promise((accept,reject)=>{p.once('exit',code=>code===0?accept():reject(new Error('Child failed '+code)));p.stdin.end('\n');});
      await exited(a.p);assert.equal(fs.existsSync(first.root),false);assert.ok(fs.existsSync(second.root));await exited(b.p);assert.equal(fs.existsSync(second.root),false);
    }finally{for(const c of [a,b])if(c.p.exitCode===null)c.p.kill();}
  });
  const failed=results.filter(result=>result.status==='failed'),skipped=results.filter(result=>result.status==='skipped');
  const receipt={suite:'compact-runtime-loader-synthetic-faults-v1',kind:'implementation-tests',passed:failed.length===0,
    checks:results.length,passedChecks:results.length-failed.length-skipped.length,skippedChecks:skipped.length,failedChecks:failed.length,
    public032BindingTested:false,workerRoutingTested:false,results,
    testedFileSha256:Object.fromEntries(['cmd/compact-runtime.mjs','scripts/compact-runtime-test.mjs'].map(name=>[name,digest(fs.readFileSync(join(project,name)))]))};
  fs.writeFileSync(join(project,'artifacts/compact-runtime-validation.json'),JSON.stringify(receipt,null,2)+'\n');
  console.log(JSON.stringify(receipt,null,2));if(failed.length)process.exitCode=1;
}
