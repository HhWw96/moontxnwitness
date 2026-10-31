import assert from 'node:assert/strict';
import {normalizeProductMetadataOnly} from './report-transport-normalization.mjs';
export function originalSixControls(){
// Independent adversarial controls: no normalization of business values, spaces,
// ordering, edges, exit codes, repeated metadata-like text or Unicode escaping.
function synthetic(version){const report={schemaVersion:1,tool:'MoonTxnWitness',version,status:'consistent',findings:[{message:'0.3.1 0.3.2 \\"version\\":\\"0.3.1\\"'}],edges:[],businessVersion:'0.3.1',businessHeader:'MoonTxnWitness v0.3.1\n'};return JSON.stringify({report,output:JSON.stringify(report)+'\n',exitCode:0});}
const reference=synthetic('0.3.1'),normalize=(raw,version='0.3.1')=>normalizeProductMetadataOnly(raw,{entry:'run_json',format:'json',version});
assert.equal(normalize(reference),normalize(synthetic('0.3.2'),'0.3.2'));
let negativeControls=0;
for(const mutation of [
 text=>text.replace('"status":"consistent"','"status": "consistent"'),
 text=>text.replace('"edges":[]','"edges":[{"proof":"extra"}]'),
 text=>text.replace('"exitCode":0','"exitCode":1'),
 text=>text.replace('"businessVersion":"0.3.1"','"businessVersion":"0.3.2"'),
 text=>text.replace('"businessHeader":"MoonTxnWitness v0.3.1','"businessHeader":"MoonTxnWitness v0.3.2'),
 text=>text.replace('"status":"consistent","findings":','"findings":'),
]){let rejected=false;try{rejected=normalize(mutation(reference))!==normalize(reference);}catch{rejected=true;}assert(rejected);negativeControls++;}
return {passed:true,negativeControls};
}
