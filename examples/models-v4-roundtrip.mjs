import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {classifyModelsV4,verifyModelsV4,makeModelsCapsuleV4,replayModelsCapsuleV4} from '../dist/sdk.mjs';
const cases=[['register','models-v4-register.json',{models:'elle-core',clients:[{id:'logical-client-A',transactions:['A']}],clientsComplete:true}],['list','models-v4-list.json',{models:['snapshot-isolation'],listProfile:'captured-list-prefix-state/v2'}]];
for(const [name,file,options] of cases){
  const source=readFileSync(new URL(file,import.meta.url),'utf8');
  const report=classifyModelsV4(source,options);
  assert.equal(report.status,'checked-compatible');
  assert.equal(verifyModelsV4(source,report,options).valid,true);
  assert.equal(replayModelsCapsuleV4(makeModelsCapsuleV4(source,options),options).valid,true);
  console.log(name+': '+report.models.length+' model result(s) and source-bound evidence verified');
}
