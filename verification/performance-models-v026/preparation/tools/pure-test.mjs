// Pure harness helpers only. No SDK import, child worker, cost or database execution.
import assert from 'node:assert/strict';
import {stats,expectation} from './common.mjs';
let checks=0;function check(fn){fn();checks++;}
check(()=>assert.deepEqual(stats([5,1,3,2,4]),{count:5,median:3,p95:5,min:1,max:5}));
check(()=>assert.equal(stats(Array.from({length:30},(_,i)=>i)).p95,28));
check(()=>assert.equal(stats([0,0]).median,0));
for(const v of [[],[NaN],[Infinity],[-1],['1'],null])check(()=>assert.throws(()=>stats(v)));
const models=['a','b'],report={format:'moontxnwitness-isolation-model-report/v1',coreReportReplay:{valid:true},status:'inconclusive',result:{models:{a:{status:'checked-compatible'},b:{status:'inconclusive'}}}};
check(()=>expectation(report,{id:'pure',expected:{status:'inconclusive',noModelRefuted:true,models:{b:'inconclusive'}}},models));
check(()=>assert.throws(()=>expectation(report,{id:'pure',expected:{allModels:'checked-compatible'}},models)));
check(()=>assert.throws(()=>expectation({...report,result:{models:{a:{status:'checked-compatible'}}}},{id:'pure',expected:{}},models)));
console.log(JSON.stringify({passed:true,checks,pureHarnessOnly:true,formalExecuted:false,sdkImported:false}));
