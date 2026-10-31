import {readFileSync} from 'node:fs';
import {reduceRelationCategoryV4,makeRelationCategoryReductionCapsuleV4,replayRelationCategoryReductionCapsuleV4} from '../dist/sdk.mjs';
const source=readFileSync(new URL('./relation-category-reduction.json',import.meta.url),'utf8');
const options={category:'G2-item'};
const reduced=reduceRelationCategoryV4(source,options);
const capsule=makeRelationCategoryReductionCapsuleV4(source,options);
const replay=replayRelationCategoryReductionCapsuleV4(capsule,options);
console.log(JSON.stringify({category:reduced.preserveCategory,status:reduced.status,oneMinimal:reduced.oneMinimal,
  removedTransactions:reduced.removedTransactions,retainedTransactions:[...new Set(reduced.history.events.filter(e=>e.tx).map(e=>e.tx))],
  originalEventSequence:reduced.originalEventSequence,replay},null,2));
if(replay.valid!==true||reduced.oneMinimal!==true)process.exitCode=1;
