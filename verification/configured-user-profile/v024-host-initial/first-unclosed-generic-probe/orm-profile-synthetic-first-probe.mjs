import {readFileSync,writeFileSync} from 'node:fs';
import {analyzeOrmProfileV3,reduceOrmProfileV3,makeOrmProfileReductionCapsuleV3,replayOrmProfileCapsuleV3} from './orm-profile-host-first/runtime/sdk.mjs';
const input=readFileSync('fixtures/orm-profile-v3/synthetic-nonrepeatable-first/profile-source.json','utf8');
const report=analyzeOrmProfileV3(input);
writeFileSync('artifacts/orm-profile-synthetic-first-report.json',JSON.stringify(report,null,2)+'\n',{flag:'wx'});
const reduction=reduceOrmProfileV3(input);
writeFileSync('artifacts/orm-profile-synthetic-first-reduction.json',JSON.stringify(reduction,null,2)+'\n',{flag:'wx'});
const capsule=makeOrmProfileReductionCapsuleV3(input);
writeFileSync('artifacts/orm-profile-synthetic-first-capsule.json',capsule,{flag:'wx'});
const replay=replayOrmProfileCapsuleV3(capsule);
console.log(JSON.stringify({sourceAccepted:report.analysisCoverageAccepted,status:report.status,gaps:report.result.mappingCoverage?.gaps,
  reducedStatus:reduction.status,before:report.result.history?.transactions.length,after:reduction.result.reduction?.reducedHistory.transactions.length,
  oneMinimal:reduction.result.reduction?.oneMinimal,finalReplay:reduction.result.finalReplay?.valid,capsuleReplay:replay.valid},null,2));
