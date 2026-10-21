// Independent fixed-SQL diagnostic audit. Expectations are frozen before SDK use.
// This does not run PostgreSQL, amend captured evidence, or grant SQL coverage.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,mkdirSync,writeFileSync} from 'node:fs';
import {resolve,dirname,relative} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {sourceFingerprint} from '../../../scripts/build-fingerprint.mjs';

const root=resolve(dirname(fileURLToPath(import.meta.url)),'../../..');
const hash=value=>createHash('sha256').update(value).digest('hex');
const copy=value=>JSON.parse(JSON.stringify(value));
const load=path=>JSON.parse(readFileSync(resolve(root,path),'utf8'));
const evidence='verification/business/dislock/v3-647afacfcbe14586b46714bac34c8f30';
const output=resolve(root,'verification/v3','dislock-sql-independent-'+new Date().toISOString().replace(/[:.]/g,'-'));
mkdirSync(output,{recursive:false});
const retain=(name,value)=>{const raw=JSON.stringify(value,null,2)+'\n';writeFileSync(resolve(output,name),raw,{flag:'wx'});return{path:relative(root,resolve(output,name)).replaceAll('\\','/'),sha256:hash(raw),bytes:Buffer.byteLength(raw)};};
const binding=path=>{const b=readFileSync(resolve(root,path));return{sha256:hash(b),bytes:b.length};};
const expected={
  'schedule-and-server-clock':{diagnostic:'all-fixed-sql-verified',futureAnalysis:'consistent'},
  'acquire-heartbeat-cleanup':{diagnostic:'all-fixed-sql-verified',futureAnalysis:'consistent'},
  'body-exception-cleanup':{diagnostic:'all-fixed-sql-verified',futureAnalysis:'consistent'},
  'busy-acquisition':{diagnostic:'incomplete-no-full-waiver',futureAnalysis:'inconclusive',reason:'Zero-row expired-row guard has no same-statement source; later SELECT cannot repair it.'},
  'ownership-lost':{diagnostic:'incomplete-no-full-waiver',futureAnalysis:'inconclusive',reason:'Zero-row owner predicate has no same-statement source.'},
  'heartbeat-reconnect':{diagnostic:'incomplete-no-full-waiver',futureAnalysis:'inconclusive',reason:'A disconnected older transaction remains unknown after reconnect.'},
  'aborted-commit-response':{diagnostic:'incomplete-no-full-waiver',futureAnalysis:'inconclusive',reason:'Confirmed server abort does not map the failed arbitrary statement.'},
};
const inputs=Object.fromEntries(Object.keys(expected).map(name=>[name,load(`${evidence}/${name}/capture.json`)]));
const stmt=(t,id)=>t.events.find(e=>e.kind==='statement'&&e.mappingId===`dislock.${id}/1`);
const rows=(t,id)=>t.events.find(e=>e.kind==='rows'&&e.statement===stmt(t,id).seq);
const firstFact=(t,kind)=>t.events.find(e=>e.kind===kind);
const profile=t=>t.sqlProfiles[0];
const meta=t=>profile(t).metadata;
const cases=[];
const add=(name,mutate,base='acquire-heartbeat-cleanup')=>cases.push({name,base,mutate});
add('original-sql-changed',t=>{stmt(t,'renew').sql+=' ';});
add('executed-sql-changed',t=>{stmt(t,'renew').executedSql+=' ';});
add('mapping-identity-changed',t=>{stmt(t,'renew').mappingId='dislock.expire/1';});
add('parameter-owner-changed',t=>{stmt(t,'renew').parameters[2]='unobserved-owner';});
add('parameter-key-changed',t=>{stmt(t,'renew').parameters[1]='unobserved-key';});
add('parameter-ttl-changed',t=>{stmt(t,'renew').parameters[0]=Number(stmt(t,'renew').parameters[0])+1;});
add('parameter-order-changed',t=>{const p=stmt(t,'renew').parameters;[p[0],p[1]]=[p[1],p[0]];});
add('parameter-missing',t=>{stmt(t,'renew').parameters.pop();});
add('parameter-extra',t=>{stmt(t,'renew').parameters.push('extra');});
add('delivered-prefix-changed',t=>{rows(t,'renew').rows[0][0]={captureType:'datetime',value:'2000-01-01 00:00:00+00:00'};});
add('business-columns-missing',t=>{delete rows(t,'renew').columns;});
add('business-typecode-changed',t=>{rows(t,'renew').columns[0].typeCode=25;});
add('business-column-name-changed',t=>{rows(t,'renew').columns[0].name='forged';});
add('business-column-extra',t=>{rows(t,'renew').columns.push({name:'forged',typeCode:25});});
add('old-type-metadata-reintroduced',t=>{const c=rows(t,'renew').columns[0];c.type=c.typeCode;delete c.typeCode;});
add('server-rows-missing',t=>{delete rows(t,'renew').serverRows;});
add('server-hidden-prefix-truncated',t=>{rows(t,'renew').serverRows[0].pop();});
add('result-not-fully-delivered',t=>{rows(t,'renew').complete=false;});
add('old-token-changed',t=>{rows(t,'renew').serverRows[0][1]='unobserved-old';});
add('new-token-changed',t=>{rows(t,'renew').serverRows[0][2]='unobserved-new';});
add('old-owner-changed',t=>{rows(t,'renew').serverRows[0][3]='unobserved-owner';});
add('same-statement-now-changed',t=>{rows(t,'renew').serverRows[0][5]={captureType:'datetime',value:'2000-01-01 00:00:00+00:00'};});
add('same-statement-now-naive',t=>{rows(t,'renew').serverRows[0][5]={captureType:'datetime',value:'2026-10-21 12:00:00'};});
add('upsert-actual-predecessor-changed',t=>{rows(t,'acquire-run').serverRows[0][7]='unobserved-predecessor';});
add('upsert-action-changed',t=>{rows(t,'acquire-run').serverRows[0][8]='UPDATE';});
add('write-version-changed',t=>{firstFact(t,'write').version='unobserved-write';});
add('write-predecessor-changed',t=>{firstFact(t,'write').predecessor='unobserved-predecessor';});
add('write-server-row-reference-changed',t=>{firstFact(t,'write').evidence.serverRow=1;});
add('write-fact-statement-reference-changed',t=>{firstFact(t,'write').statement=stmt(t,'renew').seq;});
add('condition-outcome-changed',t=>{firstFact(t,'condition').matched=false;});
add('condition-source-changed',t=>{firstFact(t,'condition').sourceVersion=firstFact(t,'write').predecessor;});
add('condition-bound-owner-changed',t=>{firstFact(t,'condition').evidence.owner='unobserved-owner';});
add('condition-clock-changed',t=>{firstFact(t,'condition').evidence.serverNow={captureType:'datetime',value:'2000-01-01 00:00:00+00:00'};});
add('committed-effect-missing',t=>{profile(t).effectLedger.shift();});
add('committed-effect-extra',t=>{const e=copy(profile(t).effectLedger[0]);e.version='unobserved-ledger-effect';profile(t).effectLedger.push(e);});
add('candidate-only-substituted-for-actual-effect',t=>{profile(t).effectLedger[0].action='CANDIDATE';});
add('initial-state-token-changed',t=>{profile(t).initialState[0].version='unobserved-initial';});
add('snapshot-token-changed',t=>{const s=t.events.find(e=>e.kind==='snapshot');s.initial[Object.keys(s.initial)[0]]='unobserved-initial';});
add('initial-snapshot-inconsistent',t=>{t.events.find(e=>e.kind==='snapshot').consistent=false;});
add('initialization-window-missing',t=>{delete meta(t).initializationWindow;});
add('initialization-commit-not-confirmed',t=>{meta(t).initializationWindow.at(-1).commandTag='ROLLBACK';});
add('initialization-snapshot-before-lock',t=>{const w=meta(t).initializationWindow;[w[1],w[3]]=[w[3],w[1]];});
add('catalog-missing',t=>{delete meta(t).catalog;});
add('catalog-unsafe-effect-enabled',t=>{meta(t).catalog.business.unsafeEffects.rewriteRules=1;});
add('catalog-business-column-changed',t=>{meta(t).catalog.business.columns[0][1]='integer';});
add('table-oid-cross-binding-broken',t=>{meta(t).tableOid+=1;});
add('trigger-oid-cross-binding-broken',t=>{meta(t).before.triggerOid+=1;});
add('function-oids-not-distinct',t=>{meta(t).before.functionOid=meta(t).after.functionOid;});
add('function-source-sha-wrong',t=>{meta(t).before.sourceSha256='0'.repeat(64);});
add('function-source-rehashed-but-not-frozen-template',t=>{const f=meta(t).before;f.source+='\n--unregistered alteration';f.sourceSha256=hash(f.source);f.functionCatalog[2]=f.source;});
add('function-security-catalog-changed',t=>{meta(t).before.functionCatalog[3]=true;});
add('trigger-definition-changed',t=>{meta(t).before.triggerDefinition+=' ';});
add('trigger-disabled',t=>{meta(t).before.enabled='D';});
add('trigger-extra-catalog-identity',t=>{meta(t).catalog.business.userTriggerOids.push(999999);});
add('initialization-nonce-cross-binding-broken',t=>{meta(t).marker.nonce='00000000-0000-0000-0000-000000000000';});
add('installation-ddl-sha-changed',t=>{meta(t).installationDdlSha256='0'.repeat(64);});
add('profile-removed',t=>{t.sqlProfiles=[];});
add('negative-guard-retroactively-claims-initial-source',t=>{const e=firstFact(t,'condition');e.sourceVersion=Object.values(t.events[0].initial)[0];delete e.evidence.sourceUnavailable;},'busy-acquisition');
add('unknown-outcome-cannot-be-repaired-by-removing-gaps',t=>{t.gaps=[];},'heartbeat-reconnect');
// Additional capture-closure premises, authorized only after the first retained
// failure. The original 59 mutations above and all seven expectations are kept.
add('supplement-exclusive-writers-not-established',t=>{t.scope.exclusiveWriters=false;});
add('supplement-explicit-input-coverage-gap',t=>{t.gaps=[{code:'external_writer',message:'Independent known omitted writer.'}];});
add('supplement-event-sequence-gap',t=>{t.events.at(-1).seq+=1;});
add('supplement-snapshot-not-first-event',t=>{const s=t.events[0],b=t.events[1];s.seq=2;b.seq=1;[t.events[0],t.events[1]]=[b,s];});
add('supplement-first-snapshot-sequence-not-one',t=>{for(const e of t.events){e.seq+=10;if(e.statement!==undefined)e.statement+=10;if(e.commitResponse)e.commitResponse.request+=10;}});

// Freeze all expectations, raw inputs, implementation, build and mutations before
// invoking any production API. Acceptance never rewrites this plan after output.
const build=load('dist/build-manifest.json');
const frozen={schema:1,kind:'independent-pre-execution-expectations',actualDatabaseExecution:false,
  stage:'diagnostic-only SQL proof; no automatic SQL analysis coverage',
  implementation:binding('verification/v3/tools/dislock_sql_proof_audit.mjs'),
  build,sourceSha256:sourceFingerprint(root),
  inputs:Object.fromEntries(Object.keys(expected).map(name=>[name,{...expected[name],...binding(`${evidence}/${name}/capture.json`)}])),
  mutations:cases.map(({name,base})=>({name,base,expected:'must-not-grant-complete-fixed-SQL-waiver'})),
  supplementalPremises:{originalMutationCount:59,addedMutationCount:5,authorization:'Root requires a complete contiguous seq1 snapshot window, explicit exclusive writers and no input gaps before complete SQL source verification. First failure and original audit implementation retained.'},
  unchangedMainReportExpectation:'All seven original main reports stay inconclusive with null projected history until explicit SQL coverage integration.',
  limitations:'Checks semantic coherence of supplied observations; does not authenticate a database or reject a fully coherent fabricated alternative history.'};
const planBinding=retain('frozen-expectations.json',frozen);
const receipt={schema:1,stage:frozen.stage,actualDatabaseExecution:false,passed:false,plan:planBinding,build,
  originals:[],mutations:[],checks:[],failures:[]};
function check(name,fn){try{fn();receipt.checks.push({name,passed:true});}catch(error){const message=String(error.message).replaceAll(root,'<workspace>');receipt.checks.push({name,passed:false,error:message});receipt.failures.push({name,error:message});}}
try{
  assert.equal(build.sourceSha256,frozen.sourceSha256,'Current source does not match frozen compiled snapshot');
  for(const [file,key]of[['core.mjs','coreSha256'],['capture-core.mjs','captureCoreSha256']])assert.equal(binding('dist/'+file).sha256,build[key]);
  assert.equal(binding('dist/sdk.mjs').sha256,binding('cmd/sdk.mjs').sha256);
  const sdk=await import(pathToFileURL(resolve(root,'dist/sdk.mjs')).href);
  const facts=t=>t.events.filter(e=>['read','write','condition'].includes(e.kind)).map(e=>e.seq).sort((a,b)=>a-b);
  const statements=t=>t.events.filter(e=>e.kind==='statement').map(e=>e.seq).sort((a,b)=>a-b);
  const full=(t,p)=>p.verifiedProfiles.length===1&&JSON.stringify(p.verifiedStatements)===JSON.stringify(statements(t))&&JSON.stringify(p.verifiedFacts)===JSON.stringify(facts(t))&&p.gaps.length===0;
  for(const [name,expectation]of Object.entries(expected)){
    const t=inputs[name],proof=sdk.inspectDislockCaptureV3(t),normal=sdk.normalizeCaptureV3(t),main=sdk.analyzeV3(t);
    const result={name,expectation,proof,mainStatus:main.status,normalStatus:normal.status};receipt.originals.push(result);
    check(name+':diagnostic-boundary',()=>{assert.equal(proof.algorithm,'dislock-f9946f0-sql-proof-1');assert.equal(proof.analysisCoverageAccepted,false);});
    check(name+':frozen-diagnostic-expectation',()=>{assert.equal(full(t,proof),expectation.diagnostic==='all-fixed-sql-verified');if(expectation.diagnostic==='all-fixed-sql-verified')assert.deepEqual(proof.verifiedProfiles,[JSON.stringify(['dislock-f9946f0-v3/1',profile(t).schema,profile(t).table])]);});
    check(name+':no-premature-analysis-exemption',()=>{assert.equal(main.status,'inconclusive');assert.equal(normal.history,null);assert.equal(main.coverage.complete,false);});
  }
  for(const {name,base,mutate}of cases){
    const t=copy(inputs[base]);mutate(t);const inputHash=hash(JSON.stringify(t));
    const proof=sdk.inspectDislockCaptureV3(t),normal=sdk.normalizeCaptureV3(t),main=sdk.analyzeV3(t);
    receipt.mutations.push({name,base,inputSha256:inputHash,proof,mainStatus:main.status,normalStatus:normal.status});
    check(name,()=>{assert.equal(proof.analysisCoverageAccepted,false);assert.equal(full(t,proof),false,'Tamper granted complete fixed-SQL proof');assert.notEqual(main.status,'consistent');assert.notEqual(main.status,'violation');assert.equal(normal.history,null);});
  }
  check('frozen-build-and-inputs-stayed-unchanged',()=>{assert.equal(sourceFingerprint(root),frozen.sourceSha256);assert.deepEqual(load('dist/build-manifest.json'),build);for(const [name,b]of Object.entries(frozen.inputs))assert.equal(binding(`${evidence}/${name}/capture.json`).sha256,b.sha256);});
}catch(error){receipt.failures.push({name:'audit-execution',error:String(error.message).replaceAll(root,'<workspace>')});}
receipt.passed=receipt.failures.length===0;
const result=retain('receipt.json',receipt);
console.log(JSON.stringify({passed:receipt.passed,originals:receipt.originals.length,mutations:receipt.mutations.length,checks:receipt.checks.length,failures:receipt.failures,receipt:result}));
process.exitCode=receipt.passed?0:1;
