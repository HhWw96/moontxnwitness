// Experimental schema 2: preserve raw presence facts independently of projection.
import {spawnSync} from 'node:child_process';
import {readFileSync,writeFileSync,readdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
import {normalizeCapture,normalizePresenceCapture,analyzeWithOptions,shrinkWithOptions,version} from '../../dist/sdk.mjs';
import {makeCapsule,replayCapsule} from '../../dist/evidence.mjs';

const args=process.argv.slice(2);
const folder=args.indexOf('--output')>=0 ? resolve(args[args.indexOf('--output')+1]) : null;
if(!folder || !args.includes('--schema'))throw Error('Use --schema new_mtw_provenance_schema --output new_folder');
const digest=path=>createHash('sha256').update(readFileSync(path)).digest('hex');
const binding=path=>{const bytes=readFileSync(resolve(folder,path));return {path,bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex')};};
const save=(name,value)=>{writeFileSync(resolve(folder,name),JSON.stringify(value,null,2)+'\n');return binding(name);};
const manifest=JSON.parse(readFileSync('dist/build-manifest.json','utf8'));
const sources=[
  'integrations/python/moontxnwitness_capture/capture.py',
  'experiments/provenance/prototype.py',
  'experiments/provenance/capture_profile.py',
  'experiments/provenance/presence_profile.py',
  'experiments/provenance/presence_postgres.py',
  'experiments/provenance/presence_e2e.mjs',
  'dist/sdk.mjs','dist/evidence.mjs','dist/build-manifest.json',
  ...readdirSync('dist').filter(name=>name.endsWith('core.mjs')).map(name=>'dist/'+name),
];
const captureSource={files:Object.fromEntries(sources.map(path=>[path,digest(path)])),
  buildManifestSourceSha256:manifest.sourceSha256};
const child=spawnSync(process.env.MTW_PYTHON || (process.platform==='win32'?'python':'python3'),
  ['experiments/provenance/presence_postgres.py',...args],{encoding:'utf8',windowsHide:true});
if(child.stdout)process.stdout.write(child.stdout);
if(child.stderr)process.stderr.write(child.stderr);
if(child.status!==0)process.exit(child.status??1);
const receipt=JSON.parse(readFileSync(resolve(folder,'presence-database.json'),'utf8'));
let capsules=0;
try {
  for(const item of receipt.scenarios){
    const raw=readFileSync(resolve(folder,item.trace),'utf8');
    const normalized=normalizePresenceCapture(raw);
    item.artifactBindings={trace:binding(item.trace),
      coverage:save(item.name+'.coverage.json',normalized),audit:binding(item.audit)};
    if(item.protocol)item.artifactBindings.protocol=binding(item.protocol);
    assert.equal(normalizeCapture(raw).status,'invalid',item.name+': stable schema-1 entry must reject schema 2');
    assert.equal(normalized.status,item.expectedStatus,item.name+': '+JSON.stringify(normalized));
    if(normalized.status!=='ready'){assert.equal(normalized.history,null);continue;}
    const history=normalized.history;
    item.artifactBindings.history=save(item.name+'.history.json',history);
    const report=analyzeWithOptions(history);
    assert.equal(report.status,item.expectedVerdict,item.name);
    item.artifactBindings.report=save(item.name+'.report.json',report);
    const capsule=makeCapsule(JSON.stringify(history),report);
    assert.equal(replayCapsule(capsule).valid,true,item.name);
    const name=item.name+'.capsule.json';
    writeFileSync(resolve(folder,name),capsule);
    item.artifactBindings.capsule=binding(name);
    capsules++;
    if(report.status==='violation'){
      const reduced=shrinkWithOptions(history);
      assert.equal(reduced.reducedHistory.transactions.length,2,item.name);
      assert.equal(reduced.oneMinimal,true,item.name);
      item.artifactBindings.reduction=save(item.name+'.reduction.json',reduced);
    }
    if(item.name==='crud-absence-reinsert-rollback'){
      const original=JSON.parse(raw), checks=[];
      const reject=(name,change)=>{
        const altered=structuredClone(original);change(altered);
        const outcome=normalizePresenceCapture(JSON.stringify(altered));
        assert.notEqual(outcome.status,'ready','Presence fact tampering accepted: '+name);
        assert.equal(outcome.history,null);
        checks.push({name,status:outcome.status,historyExported:false});
      };
      reject('initial-presence',d=>{d.presenceFacts.initial[0].present=!d.presenceFacts.initial[0].present;});
      reject('read-presence',d=>{d.presenceFacts.reads[0].present=!d.presenceFacts.reads[0].present;});
      reject('write-presence',d=>{d.presenceFacts.writes[0].newPresent=!d.presenceFacts.writes[0].newPresent;});
      reject('missing-write-fact',d=>{d.presenceFacts.writes.shift();});
      reject('missing-read-fact',d=>{d.presenceFacts.reads.shift();});
      reject('mismatched-seq',d=>{d.presenceFacts.writes[0].seq=d.presenceFacts.reads[0].seq;});
      reject('unobserved-predecessor',d=>{d.presenceFacts.writes[0].predecessor='00000000-0000-4000-8000-000000000001';});
      reject('wrong-action',d=>{d.presenceFacts.writes[0].action='insert';});
      item.artifactBindings.tamperChecks=save(item.name+'.tamper-checks.json',checks);
    }
  }
  for(const [path,hash] of Object.entries(captureSource.files))assert.equal(digest(path),hash,'Source changed during run: '+path);
  Object.assign(receipt,{status:'passed',passed:true,coreVersion:version(),replayedCapsules:capsules,captureSource,
    projectionVersion:'column-presence-register-v0.1.2-experimental',
    projectionScope:'frozen text keys; observed positive/negative point reads and actual CRUD writes; metadata predecessor is not an application read',
    bindingClaim:'SHA-256 detects artifact mismatch; it does not authenticate observation, deployment, or v3 completion',
    generatedAt:new Date().toISOString()});
  save('presence-receipt.json',receipt);
  console.log('Experimental presence: '+receipt.scenarios.length+' actual PostgreSQL scenarios, '+capsules+' replayed capsules.');
} catch(error){
  save('presence-core-failure.json',{status:'failed',phase:'core',errorClass:error.name,message:error.message,actualDatabaseExecution:true});
  throw error;
}
