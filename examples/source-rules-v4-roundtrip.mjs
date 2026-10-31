// Offline examples for the independent point-category and raw-source namespaces.
import assert from 'node:assert/strict';
import {classifyRelationV4,inspectCaptureAnomaliesV4,inspectInternalConsistencyV4,
  makeRelationClassificationCapsuleV4,makeCaptureAnomaliesCapsuleV4,
  makeInternalConsistencyCapsuleV4,replayRelationCapsuleV4} from '../dist/sdk.mjs';
const stamp=events=>events.map((e,i)=>({seq:i+1,time:i,...e}));
const begin=tx=>({kind:'begin',tx,connection:'example-'+tx}),end=tx=>[{kind:'commit_request',tx},{kind:'commit_ok',tx}];
const relation={traceSchema:3,dataModel:'relation-set-v1',relationSchema:{items:{primaryKey:'id',columns:{id:'int64',value:'text'}}},clockDomain:'offline-source-rules',scope:{exclusiveWriters:true,completeSnapshotTables:['items']},gaps:[],events:stamp([{kind:'snapshot',consistent:true,initial:{items:[{key:'1',version:'v0',values:{value:'same'}}]}},begin('R'),{kind:'row_read',tx:'R',relation:'items',predicate:[{column:'id',op:'eq',value:'1'}],rows:[{key:'1',version:'v0',values:{value:'same'}}],complete:true},...end('R')])};
const capture={traceSchema:3,dataModel:'point-register-v1',clockDomain:'offline-source-rules',scope:{exclusiveWriters:true},gaps:[],events:stamp([{kind:'snapshot',initial:{x:'x0'},consistent:true},begin('W'),{kind:'write',tx:'W',key:'x',version:'w1',predecessor:'x0'},{kind:'rollback_ok',tx:'W'},begin('R'),{kind:'read',tx:'R',key:'x',version:'w1'},...end('R')])};
const internal={...capture,events:stamp([{kind:'snapshot',initial:{x:'x0'},consistent:true},begin('R'),{kind:'write',tx:'R',key:'x',version:'r1',predecessor:'x0'},{kind:'read',tx:'R',key:'x',version:'x0'},...end('R')])};
const results=[];
for(const [name,source,run,make]of [['relation',relation,classifyRelationV4,makeRelationClassificationCapsuleV4],['capture',capture,inspectCaptureAnomaliesV4,makeCaptureAnomaliesCapsuleV4],['internal',internal,inspectInternalConsistencyV4,makeInternalConsistencyCapsuleV4]]){
  const report=run(source),replay=replayRelationCapsuleV4(make(source));assert.equal(replay.valid,true);
  results.push({name,status:report.judgment?.status??report.status,replayValid:replay.valid,acceptsIsolationModels:report.judgment?.acceptsIsolationModels??report.scope.acceptsIsolationModels});
}
console.log(JSON.stringify(results,null,2));
