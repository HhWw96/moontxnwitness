// Execute the actual producer modules with simulated driver/files/runtime imports.
// The VM never starts a driver, writes production evidence, or opens a database.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve,dirname,basename} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import vm from 'node:vm';

const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const packageNames=['__init__.py','capture.py','_provenance.py','_column_profile.py','_initialization_guard.py','_source_inventory.py','presence.py'];
const producers=[['experiments/provenance/presence_e2e.mjs','presence'],
  ['experiments/provenance/capture_profile_e2e.mjs','profile'],['experiments/business/dislock/e2e.mjs','business']];
const variants=['valid','unchanged-false','wrong-sha','missing-entry','changed-before-after','wrong-bytes','missing-inventory'];
const results=[];
for(const [name,prefix]of producers){
  for(const variant of variants){
    const writes=[];
    const bytes=path=>Buffer.from('simulated source:'+resolve(String(path)),'utf8');
    const inventory=Object.fromEntries(packageNames.map(name=>{
      const path='moontxnwitness_capture/'+name,b=bytes('integrations/python/'+path);
      return [path,{bytes:b.length,sha256:createHash('sha256').update(b).digest('hex')}];
    }));
    const receipt={scenarios:[],implementationSources:{before:structuredClone(inventory),after:structuredClone(inventory),unchanged:true}};
    const key='moontxnwitness_capture/presence.py';
    if(variant==='unchanged-false')receipt.implementationSources.unchanged=false;
    if(variant==='wrong-sha')for(const phase of ['before','after'])receipt.implementationSources[phase][key].sha256='0'.repeat(64);
    if(variant==='missing-entry')for(const phase of ['before','after'])delete receipt.implementationSources[phase][key];
    if(variant==='changed-before-after')receipt.implementationSources.before[key].bytes++;
    if(variant==='wrong-bytes')for(const phase of ['before','after'])receipt.implementationSources[phase][key].bytes++;
    if(variant==='missing-inventory')delete receipt.implementationSources;
    const fakeFs={
      readFileSync(path,encoding){
        let value;
        if(basename(String(path))===prefix+'-database.json')value=Buffer.from(JSON.stringify(receipt));
        else if(basename(String(path))==='build-manifest.json')value=Buffer.from(JSON.stringify({sourceSha256:'fixture-only'}));
        else value=bytes(path);
        return encoding==='utf8'?value.toString('utf8'):value;
      },
      writeFileSync(path,value){writes.push({path:String(path),value:JSON.parse(value)});},
      readdirSync(){return ['core.mjs','capture-core.mjs'];},
    };
    const context=vm.createContext({
      process:{argv:['fixture-node',name,'--schema','mtw_provenance_mock','--output','virtual-'+prefix],
        env:{MTW_PYTHON:'mock-driver-never-launched'},stdout:{write(){}},stderr:{write(){}},
        exit(code){throw new Error('Unexpected mock process exit '+code);}},
      console:{log(){},error(){}},
    });
    const modules=new Map();
    const unsupported=()=>{throw new Error('Core analysis is outside this metadata-only mock');};
    const linker=specifier=>{
      if(modules.has(specifier))return modules.get(specifier);
      let exports;
      if(specifier==='node:fs')exports=fakeFs;
      else if(specifier==='node:child_process')exports={spawnSync:()=>({status:0,stdout:'',stderr:''})};
      else if(specifier==='node:path')exports={resolve};
      else if(specifier==='node:crypto')exports={createHash};
      else if(specifier==='node:assert/strict')exports={default:assert};
      else if(specifier.endsWith('/sdk.mjs'))exports={normalizeCapture:unsupported,normalizePresenceCapture:unsupported,
        analyzeWithOptions:unsupported,shrinkWithOptions:unsupported,version:()=> 'fixture-only'};
      else if(specifier.endsWith('/evidence.mjs'))exports={makeCapsule:unsupported,replayCapsule:unsupported};
      else throw new Error('Unapproved VM import '+specifier);
      const module=new vm.SyntheticModule(Object.keys(exports),function(){for(const[key,value]of Object.entries(exports))this.setExport(key,value);},{context});
      modules.set(specifier,module);return module;
    };
    const module=new vm.SourceTextModule(readFileSync(resolve(root,name),'utf8'),{context,identifier:name});
    await module.link(linker);
    let executionError=null;
    try{await module.evaluate();}catch(error){executionError=error;}
    if(variant==='valid'){
      assert.equal(executionError,null);
      assert.equal(writes.length,1,name);
      assert.equal(basename(writes[0].path),prefix+'-receipt.json');
      assert.equal(writes[0].value.passed,true);
    }else{
      // The production producer writes its failure receipt, then rethrows so
      // its caller also receives a nonzero result. Both parts are required.
      assert.notEqual(executionError,null);
      assert.equal(writes.length,1,name+' '+variant);
      assert.equal(basename(writes[0].path),prefix+'-core-failure.json');
      assert.equal(writes[0].value.status,'failed');
      assert.equal(writes[0].value.phase,'core');
      assert.equal(writes.some(item=>item.value.passed===true),false);
    }
    results.push({producer:name,variant,passed:true,simulatedFilesystem:true,simulatedDriver:true});
  }
}
console.log(JSON.stringify({passed:true,cases:results.length,actualDatabaseExecution:false,actualCoreAnalysis:false,results}));
