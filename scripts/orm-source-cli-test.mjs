import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdirSync, mkdtempSync, readFileSync, writeFileSync, existsSync} from 'node:fs';
import {resolve} from 'node:path';
import {spawnSync} from 'node:child_process';
import {inspectOrmSourceV3, normalizeCaptureV3} from '../dist/sdk.mjs';
import {orm_sql_source2_v3_proof_json} from '../dist/capture-core.mjs';
import {root} from './moon.mjs';
import {writeVerifiedJson} from './performance-evidence.mjs';

export function runOrmSourceCliTests() {
  const bundle=resolve(root,'verification/experimental-candidates/orm-source2-r3-2026-10-21');
  const tracePath=resolve(bundle,'fixtures/diagnostic-trace.json');
  const sourcePath=resolve(bundle,'fixtures/source-observations.jsonl');
  const traceText=readFileSync(tracePath,'utf8'),sourceJournalText=readFileSync(sourcePath,'utf8');
  const sha=x=>createHash('sha256').update(x).digest('hex');
  assert.equal(sha(traceText),'3ee5a826c5d80cc6b753b35456c0921c62b867312fb56e43aae233f311c9f97a');
  assert.equal(sha(sourceJournalText),'88cbaaee15e5e0faf403b2a91ce4ace53d4e2ddf656a06b1f15cf979fbf7a3ec');
  const envelope={schema:2,profile:'fastapi-users-sqlalchemy-7.0.0-pg18/1',traceText,sourceJournalText};
  const parent=resolve(root,'artifacts/test-work');mkdirSync(parent,{recursive:true});
  const work=mkdtempSync(resolve(parent,'orm-source-'));
  const checks=[];
  const test=(name,fn)=>{fn();checks.push(name);};
  const localProof=r=>{
    assert.equal(r.schema,2);assert.equal(r.algorithm,'v3-orm-source-proof-2');
    assert.equal(r.analysisCoverageAccepted,false);assert.equal(r.history,null);
    for(const key of ['verifiedStatements','verifiedFacts','verifiedProfiles'])assert.deepEqual(r[key],[]);
  };
  const run=(args,status,input)=>{
    const p=spawnSync(process.execPath,[resolve(root,'dist/moontxnwitness.mjs'),'inspect-orm-source-v3',...args],
      {cwd:root,input,encoding:'utf8',timeout:30000,maxBuffer:4*1024*1024,windowsHide:true});
    assert.ifError(p.error);assert.equal(p.status,status,p.stderr+'\n'+p.stdout);return p;
  };
  let original;
  test('SDK returns the complete raw local proof without granting global coverage',()=>{
    original=inspectOrmSourceV3(envelope);localProof(original);
    assert.equal(original.controlProfileComplete,true);assert.equal(original.provenStatements.length,21);
    assert.equal(original.provenFacts.length,21);assert.equal(original.verifiedControlQueries.length,121);
    assert.equal(original.observedEffects.length,8);
    assert.deepEqual(original,JSON.parse(orm_sql_source2_v3_proof_json(JSON.stringify(envelope))));
  });
  test('string envelope keeps exact original trace and source byte bindings',()=>{
    const r=inspectOrmSourceV3(JSON.stringify(envelope));assert.deepEqual(r,original);
    assert.equal(r.traceSha256,sha(traceText));assert.equal(r.sourceJournalSha256,sha(sourceJournalText));
  });
  test('SDK does not replace a caller schema or unknown profile',()=>{
    for(const changed of [{...envelope,schema:1},{...envelope,profile:'unreviewed'}]){
      const r=inspectOrmSourceV3(changed);localProof(r);assert.equal(r.controlProfileComplete,false);
      assert.deepEqual(r.provenFacts,[]);
    }
  });
  test('SDK enforces UTF8 bytes before entering the MoonBit parser',()=>{
    assert.throws(()=>inspectOrmSourceV3('界'.repeat(Math.floor(64*1024*1024/3)+1)),RangeError);
  });
  test('calling the diagnostic never enables default capture normalization',()=>{
    const r=normalizeCaptureV3(traceText);assert.equal(r.history,null);assert.equal(r.status,'inconclusive');
  });
  test('CLI returns the same partial report with diagnostic exit status',()=>{
    assert.deepEqual(JSON.parse(run([tracePath,sourcePath],0).stdout),original);
  });
  test('CLI supports one original trace on stdin',()=>{
    assert.deepEqual(JSON.parse(run(['-',sourcePath],0,traceText).stdout),original);
  });
  test('CLI supports one original source journal on stdin',()=>{
    assert.deepEqual(JSON.parse(run([tracePath,'-'],0,sourceJournalText).stdout),original);
  });
  test('CLI saves only a new report and refuses overwrite',()=>{
    const out=resolve(work,'proof.json');run([tracePath,sourcePath,'--output',out],0);
    const bytes=readFileSync(out);assert.deepEqual(JSON.parse(bytes),original);
    run([tracePath,sourcePath,'--output',out],2);assert.deepEqual(readFileSync(out),bytes);
    run([tracePath,sourcePath,'--output',tracePath],2);assert.equal(sha(readFileSync(tracePath)),sha(traceText));
  });
  test('CLI rejects invalid UTF8 without creating a report',()=>{
    const path=resolve(work,'invalid-utf8.json'),out=resolve(work,'never.json');writeFileSync(path,Buffer.from([255]));
    run([path,sourcePath,'--output',out],2);assert.equal(existsSync(out),false);
  });
  test('CLI malformed source fails local proof and keeps global refusal',()=>{
    const path=resolve(work,'invalid-source.jsonl');writeFileSync(path,'{}\n');
    const r=JSON.parse(run([tracePath,path],2).stdout);localProof(r);
    assert.equal(r.controlProfileComplete,false);assert.deepEqual(r.provenStatements,[]);
  });
  test('CLI rejects ambiguous stdin and unsupported options',()=>{
    run(['-','-'],2,'{}');run([tracePath,sourcePath,'--history',resolve(work,'never-history.json')],2);
    assert.equal(existsSync(resolve(work,'never-history.json')),false);
  });
  const receipt={schema:1,kind:'integrated-orm-source-sdk-cli',passed:true,checks:checks.length,names:checks,
    inputSha256:sha(traceText),sourceSha256:sha(sourceJournalText),
    actualDatabaseExecution:false,analysisCoverageAccepted:false,fullApplicationAccepted:false};
  const name='verification/v3/orm-source-sdk-cli-'+new Date().toISOString().replace(/[:.]/g,'-')+'.json';
  writeVerifiedJson(resolve(root,name),receipt);
  return {...receipt,receipt:name};
}
