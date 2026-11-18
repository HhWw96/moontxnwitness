// Independent compiled MoonBit reconstruction versus frozen Python descriptors.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {pathToFileURL} from 'node:url';
import {parseArgs} from 'node:util';
import {createHash} from 'node:crypto';
const {values}=parseArgs({options:{core:{type:'string'},inputs:{type:'string'},output:{type:'string'}}});
for(const name of ['core','inputs','output'])assert(values[name],`--${name} is required`);
const core=resolve(values.core),input=resolve(values.inputs),output=resolve(values.output),sha=data=>createHash('sha256').update(data).digest('hex');
mkdirSync(dirname(output),{recursive:true});
const snapshot=resolve(dirname(output),'point-projection-v2-core.mjs');writeFileSync(snapshot,readFileSync(core));
const api=await import(pathToFileURL(snapshot).href),fixture=JSON.parse(readFileSync(input,'utf8')),rows=[],reports=[];
function difference(a,b,path=''){if(JSON.stringify(a)===JSON.stringify(b))return null;if(a===null||b===null||typeof a!=='object'||typeof b!=='object')return {path,expected:a,actual:b};for(const key of new Set([...Object.keys(a),...Object.keys(b)])){const next=difference(a[key],b[key],path+'/'+key);if(next)return next;}return null;}
function parsed(c){return {config:JSON.parse(c.configText),source:c.source,typed:JSON.parse(c.typedParametersText),options:JSON.parse(c.independentOptionsText),descriptor:JSON.parse(c.descriptorText)};}
function run(v,budget={}){return JSON.parse(api.verify_point_projection_v2_json(JSON.stringify(v.config),v.source,JSON.stringify(v.typed),JSON.stringify(v.options),JSON.stringify(v.descriptor),JSON.stringify(budget)));}
function noFacts(report){for(const name of ['databaseExecuted','databaseSyntaxValidated','sourceAuthenticated','captureFactsProduced','sourceFactsProduced','completeWindow','modelCoverageAccepted','moonbitProjectionVerified','commitVerified'])assert.equal(report[name],false,name);}
function check(name,kind,fn){try{fn();rows.push({name,kind,passed:true});}catch(error){rows.push({name,kind,passed:false,error:error.stack});}}
for(const c of fixture.cases)check(c.name,c.origin,()=>{
 const v=parsed(c),report=run(v);
 if(report.status!=='matched')throw Error(JSON.stringify({status:report.status,gaps:report.gaps,difference:difference(v.descriptor,report.expectedDescriptor)}));
 assert.equal(report.valid,true);assert.deepEqual(report.expectedDescriptor,v.descriptor);assert.deepEqual(report.originalTypedParameters,v.typed);noFacts(report);
 for(const flag of ['databaseExecuted','databaseSyntaxValidated','sourceAuthenticated','captureFactsProduced','sourceFactsProduced','completeWindow','modelCoverageAccepted','moonbitProjectionVerified','returningIsPredicateRead','writeImagesAreSelectFacts','producesDeletionVersion'])assert.equal(report.expectedDescriptor[flag],false);
 reports.push({name:c.name,projectedSqlSha256:report.expectedDescriptor.projectedSqlSha256,checks:report.execution.checks});
});
const find=name=>{const c=fixture.cases.find(c=>c.name===name);assert(c,name);return c;};
const base=find(fixture.recordedReceipt?'recorded-0-update-8':'offline-reference-update'),star=find(fixture.recordedReceipt?'recorded-0-select-star':'offline-select-star'),uuid=find('uuid-%s-object'),named=find('named-repeated-dict-order');
function fault(name,c,change,status='mismatch',budget={}){check(name,'synthetic-tamper',()=>{const v=parsed(c);change(v);const report=run(v,budget);assert.equal(report.status,status,JSON.stringify(report.gaps));assert.equal(report.valid,false);noFacts(report);});}
fault('projected-SQL-tamper',base,v=>v.descriptor.projectedSql+=' ');
fault('original-SQL-tamper',base,v=>v.source+=' -- original changed');
fault('original-SQL-extra-condition',base,v=>v.source=v.source.replace(' WHERE ',' WHERE active=true AND '),'unknown');
fault('valid-typed-binding-tamper',base,v=>v.typed.items[0].decimal='24');
fault('dict-original-order-preserved',named,v=>v.typed.items.reverse());
fault('UUID-object-not-string',uuid,v=>v.typed.items[0].pythonType='str');
fault('UUID-object-upper-observation-invalid',uuid,v=>v.typed.items[0].value=v.typed.items[0].value.toUpperCase(),'invalid');
fault('UUID-string-original-spelling-preserved',find('uuid-%s-upper'),v=>v.typed.items[0].value=v.typed.items[0].value.replaceAll('-',''));
fault('OLD-NEW-aliases-swapped',base,v=>{const a=v.descriptor.returningAliases;[a.old,a.new]=[a.new,a.old];});
fault('OLD-NEW-hidden-order-swapped',base,v=>v.descriptor.hiddenResults.reverse());
fault('hidden-native-index-tamper',base,v=>v.descriptor.hiddenResults[0].columns[0].nativeIndex++);
fault('business-output-order-tamper',base,v=>v.descriptor.businessResult.columns.reverse());
fault('native-column-count-tamper',base,v=>v.descriptor.nativeColumnCount++);
fault('write-image-not-read-fact',base,v=>v.descriptor.hiddenResults[0].role='positive-read-version-candidate');
fault('fixed-int64-hidden-version',base,v=>v.descriptor.hiddenResults[0].version.type='uuid');
fault('deletion-does-not-mint-version',find(fixture.recordedReceipt?'recorded-0-delete-returning':'offline-delete-returning'),v=>v.descriptor.producesDeletionVersion=true);
fault('embedded-options-not-authority',base,v=>v.descriptor.independentOptions.versionColumn='other_version');
fault('caller-version-options-control',base,v=>v.options.versionColumn='other_version');
fault('dual-config-must-agree',base,v=>v.options.config.table.table='different','invalid');
fault('independent-version-type-int64-only',base,v=>v.options.versionType='uuid','invalid');
fault('version-cannot-collide-with-business',base,v=>v.options.versionColumn='balance','invalid');
fault('star-default-refusal',star,v=>{v.options.starContract=null;v.options.businessStarColumns=null;},'unknown');
fault('star-order-independent-policy',star,v=>v.options.businessStarColumns.reverse(),'invalid');
fault('star-proof-obligation-required',star,v=>v.descriptor.requiredProofs.pop());
fault('star-installation-not-self-authorized',star,v=>v.descriptor.businessStarView.installationVerified=true);
fault('star-current-native-equivalence-unproved',star,v=>v.descriptor.businessStarView.equivalentToCurrentNativeStar=true);
fault('projected-position-map-tamper',named,v=>v.descriptor.parameterMap[0].projectedIndex++);
fault('raw-map-cannot-use-normalized-UUID-atom',uuid,v=>v.descriptor.parameterMap[0].value.pythonType='str');
fault('typed-input-UUID-is-normalized-string',uuid,v=>v.descriptor.typedInputBindings[0].value.pythonType='uuid.UUID');
for(const flag of ['databaseExecuted','databaseSyntaxValidated','sourceAuthenticated','captureFactsProduced','sourceFactsProduced','completeWindow','modelCoverageAccepted','moonbitProjectionVerified'])fault('no-self-authorization-'+flag,base,v=>v.descriptor[flag]=true);
fault('own-caller-check-budget',base,()=>{},'unknown',{maxChecks:0});
fault('independent-grammar-budget',base,()=>{},'unknown',{grammarOptions:{maxChecks:0}});
fault('independent-projected-SQL-byte-budget',base,v=>v.options.maxProjectedSqlBytes=1,'unknown');
fault('independent-descriptor-byte-budget',base,v=>v.options.maxDescriptorBytes=1,'unknown');
fault('typed-dict-duplicate-key-invalid',named,v=>v.typed.items.push(structuredClone(v.typed.items[0])),'invalid');
fault('typed-container-invalid',base,v=>v.typed.container='iterator','invalid');
const originalUnchanged=fixture.recordedReceipt===null||sha(readFileSync(fixture.recordedReceipt))===fixture.recordedReceiptSha256;
const frozenUnchanged=Object.entries(fixture.frozenSourceBeforeSha256).every(([name,value])=>sha(readFileSync(name))===value);
const root=resolve(import.meta.dirname,'..'),sources=['src/point_projection_config_v2.mbt','src/point_projection_v2.mbt','src/api_point_projection_v2.mbt','src/point_projection_v2_wbtest.mbt','src/sql_projection_v2_bridge/bridge.mbt','scripts/point-projection-v2-cross-inputs.py','scripts/point-projection-v2-cross-test.mjs','docs/point-projection-verifier-v2.md'];
const result={format:'point-projection-v2-independent-cross-validation/v1',passed:originalUnchanged&&frozenUnchanged&&rows.every(row=>row.passed),testsRun:rows.length,failed:rows.filter(row=>!row.passed).length,recordedDescriptors:fixture.recordedDescriptorCases,freshPythonConstructions:fixture.actualPythonConstructionCases,syntheticTamperCases:rows.length-fixture.cases.length,originalReceiptUnchanged:originalUnchanged,frozenProjectionFilesUnchanged:frozenUnchanged,recordedReceiptSha256:fixture.recordedReceiptSha256,coreSha256:sha(readFileSync(core)),inputsSha256:sha(readFileSync(input)),sourceSha256:Object.fromEntries(sources.map(name=>[name,sha(readFileSync(resolve(root,name)))])),actualDatabaseExecution:false,actualDriverWrapperExecuted:false,sourceFactsProduced:false,completeWindow:false,modelCoverageAccepted:false,commitVerified:false,publicReleasePerformed:false,scope:'independent projection descriptor reproduction only; recorded descriptors do not authorize execution, source installation, lifecycle, complete writer windows or model history',results:rows,matchedDescriptorReports:reports};
writeFileSync(output,JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify({passed:result.passed,tests:result.testsRun,failed:result.failed,recordedDescriptors:result.recordedDescriptors,freshPythonConstructions:result.freshPythonConstructions,syntheticTamperCases:result.syntheticTamperCases,output}));
if(!result.passed){for(const row of rows.filter(row=>!row.passed))console.error(row.name,row.error);process.exitCode=1;}
