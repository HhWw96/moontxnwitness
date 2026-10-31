// Host contracts only: the spy records original strings; no Moon core executes.
import assert from 'node:assert/strict';
import {createSQLCandidateV1,SQL_CANDIDATE_V1_LIMITS} from '../cmd/sql-candidate-host-v1.mjs';
import {createSQLFetchV1,SQL_FETCH_V1_LIMITS} from '../cmd/sql-fetch-host-v1.mjs';
let calls=[];const names=['normalize_configured_sql_v1_json','verify_configured_sql_v1_json','normalize_sql_config_v1_json','compare_c_text_v1','verify_configured_fetch_v1_json'];
const spy=Object.fromEntries(names.map(name=>[name,(...args)=>{calls.push({name,args});return name==='compare_c_text_v1'?0:JSON.stringify({valid:false,sourceFactsProduced:false,args});}]));
const candidate=createSQLCandidateV1(spy),fetch=createSQLFetchV1(spy),results=[];
function check(name,fn){calls=[];fn();results.push({name,passed:true});}
check('factories are immutable and retain synchronous named functions',()=>{assert(Object.isFrozen(candidate));assert(Object.isFrozen(fetch));for(const fn of [...Object.values(candidate),...Object.values(fetch)])assert.notEqual(fn.constructor.name,'AsyncFunction');});
check('missing compiled entries fail explicitly',()=>{assert.throws(()=>createSQLCandidateV1({}),TypeError);assert.throws(()=>createSQLFetchV1({}),TypeError);});
check('fixed host limits remain unchanged',()=>{assert.equal(SQL_CANDIDATE_V1_LIMITS.sqlBytes,1048576);assert.equal(SQL_FETCH_V1_LIMITS.reportBytes,33554432);});
check('raw config text is not reparsed or normalized',()=>{candidate.normalizeSQLConfigV1(' {"version":"business"} ');assert.deepEqual(calls[0].args,[' {"version":"business"} ']);});
check('unsafe int64 parameter text is passed unchanged',()=>{candidate.normalizeSQLCandidateV1('{}','SELECT id FROM t','[9223372036854775807]',' {"maxChecks":0} ');assert.deepEqual(calls[0].args,['{}','SELECT id FROM t','[9223372036854775807]',' {"maxChecks":0} ']);});
check('materialized safe parameters use original JSON serialization',()=>{candidate.normalizeSQLCandidateV1({},'SELECT id FROM t',[17,true,'月'],{});assert.equal(calls[0].args[2],'[17,true,"月"]');});
check('unsafe host numbers cannot be rounded into parameters',()=>{assert.throws(()=>candidate.normalizeSQLCandidateV1({},'SELECT id FROM t',[9007199254740992]),TypeError);assert.equal(calls.length,0);});
check('float and null parameter members remain rejected',()=>{for(const v of [[1.5],[null]])assert.throws(()=>candidate.normalizeSQLCandidateV1({},'SELECT id FROM t',v),TypeError);assert.equal(calls.length,0);});
check('unknown or excessive independent options do not call the core',()=>{for(const o of [{trust:true},{maxChecks:1000001},{maxTokens:-1}])assert.throws(()=>candidate.normalizeSQLCandidateV1({},'SELECT id FROM t',[],o),TypeError);assert.equal(calls.length,0);});
check('zero caller budgets are retained',()=>{candidate.normalizeSQLCandidateV1({},'SELECT id FROM t',[],{maxChecks:0,maxTokens:0,maxSqlBytes:0});assert.equal(calls[0].args[3],'{"maxChecks":0,"maxTokens":0,"maxSqlBytes":0}');});
check('verify keeps invalid host input a diagnostic failure',()=>{const r=candidate.verifySQLCandidateV1({},'SELECT id FROM t',[9007199254740992],{});assert.equal(r.valid,false);assert.equal(r.captureFactsProduced,false);assert.equal(calls.length,0);});
check('malformed Unicode is not rewritten to replacement characters',()=>{assert.throws(()=>candidate.normalizeSQLCandidateV1({},'\ud800',[]),TypeError);assert.equal(calls.length,0);});
check('SQL byte limit remains inclusive',()=>{candidate.normalizeSQLCandidateV1({},'x'.repeat(1048576),[]);assert.equal(calls.length,1);assert.throws(()=>candidate.normalizeSQLCandidateV1({},'x'.repeat(1048577),[]),TypeError);assert.equal(calls.length,1);});
check('C comparator receives original strings and remains synchronous',()=>{assert.equal(candidate.compareConfiguredCTextV1('é','e\u0301'),0);assert.deepEqual(calls[0].args,['é','e\u0301']);});
check('fetch preserves five independent original text inputs',()=>{fetch.verifyConfiguredFetchV1(' {} ',' {"parametersJson":"[9223372036854775807]"} ',' {} ',' [] ',' {"maxChecks":0} ');assert.deepEqual(calls[0].args,[' {} ',' {"parametersJson":"[9223372036854775807]"} ',' {} ',' [] ',' {"maxChecks":0} ']);});
check('fetch rejects unsafe materialized numbers before dispatch',()=>{const r=fetch.verifyConfiguredFetchV1({}, {id:9007199254740992},{},[]);assert.equal(r.valid,false);assert.equal(calls.length,0);});
check('fetch rejects cyclic structured input without invoking the core',()=>{const v={};v.self=v;assert.equal(fetch.verifyConfiguredFetchV1({},v,{},[]).valid,false);assert.equal(calls.length,0);});
check('fetch nesting and exotic objects are not silently accepted',()=>{assert.equal(fetch.verifyConfiguredFetchV1({},new Date(),{},[]).valid,false);let v={};for(let i=0;i<65;i++)v={child:v};assert.equal(fetch.verifyConfiguredFetchV1({},v,{},[]).valid,false);assert.equal(calls.length,0);});
console.log(JSON.stringify({format:'shared-core-host-contract/v1',passed:true,checks:results.length,results,actualMoonCoreExecuted:false,actualDatabaseExecution:false,formalPerformanceMeasurement:false}));
