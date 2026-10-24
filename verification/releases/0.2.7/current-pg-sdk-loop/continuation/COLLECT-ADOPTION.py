from pathlib import Path
import hashlib,json
FIRST=Path(r'D:\CodexScratch\MoonTxnWitness-v027-current-pg-sdk-loop-20261024-ai')
HERE=Path(__file__).resolve().parent
ROOT=Path(r'D:\CodexScratch\MoonTxnWitness-release-20261023')
def bind(path):
 raw=path.read_bytes();return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def load(path):return json.loads(path.read_bytes())
def write(name,value):
 with(HERE/name).open('x',encoding='utf8',newline='\n')as f:f.write(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
def verify_files(root,receipt):
 for row in receipt['files']:assert bind(root/row['file'])=={k:row[k]for k in ('bytes','sha256')}
a=load(FIRST/'first-run/results/receipt.json');b=load(HERE/'continuation-first/results/receipt.json');plan=load(FIRST/'PLAN.json')
assert a['passed']is False and b['passed']is True and a['sdkTopLevelCalls']==101 and b['sdkTopLevelCalls']==25
assert a['inputsBeforeAfterUnchanged']and a['runtimeBeforeAfterUnchanged']and b['inputsBeforeAfterUnchanged']and b['runtimeBeforeAfterUnchanged']
verify_files(FIRST/'first-run/results',a);verify_files(HERE/'continuation-first/results',b)
assert len([x for x in a['cases']if x['passed']])==8 and len(b['cases'])==2
entries={x['case']:x for x in plan['inputs']};accepted=[];tamper_count=0
for case in a['cases']:
 name=case['case'];root=(FIRST/'first-run/results')if case['passed']else(HERE/'continuation-first/results');selected=case if case['passed']else next(x for x in b['cases']if x['case']==name)
 assert selected['passed'];directory=root/name;source=(directory/'source.original.json').read_text(encoding='utf8');envelope=json.loads(source);report=load(directory/'report.json');capsule=load(directory/'capsule.json');replay=load(directory/'replay.json');verified=load(directory/'verify.json');normalized=load(directory/'generic-normalization.json')
 assert bind(directory/'source.original.json')==entries[name]['binding'];assert normalized['coverage']['complete']is False
 assert verified['valid']is True and replay['valid']is True and replay['envelopeText']==source and replay['report']==report
 assert capsule['envelopeText']==source and json.loads(capsule['reportText'])==report and capsule['reportSha256']==hashlib.sha256(capsule['reportText'].encode('utf8')).hexdigest()
 assert report['engine']['version']=='0.2.7'and report['engine']['coreSha256']==plan['buildManifest']['coreSha256']and report['scope']['sourceClosedReductionAvailable']is False
 assert report['analysisCoverageAccepted']is(entries[name]['expectedProjection']=='supported')
 assert report['status']==(entries[name]['expectedSerialStatus']if entries[name]['expectedProjection']=='supported'else'inconclusive')
 for path in directory.glob('tampered-*.verification.json'):assert load(path)['valid']is False;tamper_count+=1
 for path in directory.glob('tampered-*.replay.json'):assert load(path)['valid']is False;tamper_count+=1
 # Core JSONs contain only their original JSON value types; reproduce stored JS pretty form.
 core=(json.dumps(report['result'],indent=2,ensure_ascii=False,separators=(',',': '))+'\n').encode('utf8')
 assert {'bytes':len(core),'sha256':hashlib.sha256(core).hexdigest()}==entries[name]['originalCoreProjectionBinding']
 accepted.append({'case':name,'finalStatus':report['status'],'mappingAccepted':report['analysisCoverageAccepted'],'completedIn':'first101'if case['passed']else'continuation25','source':bind(directory/'source.original.json'),'report':bind(directory/'report.json'),'capsule':bind(directory/'capsule.json'),'genericDiagnosticCoverageComplete':False,'profileOriginalDiagnosticCoveragePresent':report['result']['originalDiagnosticCoverage']is not None,'originalCoreProjectionByteIdentical':True,'verifyPassed':True,'replayPassed':True,'tamperRejections':7,'sourceClosedReductionAvailable':False})
assert len(accepted)==10 and sum(x['mappingAccepted']for x in accepted)==7 and tamper_count==70
first_projection=[]
for name,entry in entries.items():
 report=load(FIRST/'first-run/results'/name/'report.json');raw=(json.dumps(report['result'],indent=2,ensure_ascii=False,separators=(',',': '))+'\n').encode('utf8');assert {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}==entry['originalCoreProjectionBinding'];first_projection.append(name)
failed_first=[x for x in a['checks']if not x['passed']];assert len(failed_first)==2
resources=[load(FIRST/'first-run/RESOURCES-FIRST.json'),load(HERE/'continuation-first/RESOURCES-FIRST.json')];assert all(x['passed']and x['minimumPhysicalBytes']==1073741824 and x['nodeHeapMiB']==384 for x in resources)
aggregate={'format':'moontxnwitness-current027-pg-sdk-loop-aggregate/v1','status':'passed-after-retained-harness-scope-fix','passed':True,'sourceCommit':plan['sourceCommit'],'currentBuildManifest':plan['buildManifest'],'sourceOriginalPGRun':40095757205,'originalArtifactSha256':plan['artifactSha256'],'executionHistory':{'first':{'sdkTopLevelCalls':101,'completedCases':8,'harnessInterruptedCases':2,'passed':False,'processReceipt':bind(FIRST/'first-run/PROCESS-FIRST.json'),'sdkReceipt':bind(FIRST/'first-run/results/receipt.json')},'continuation':{'sdkTopLevelCalls':25,'completedPreviouslyInterruptedCases':2,'passed':True,'processReceipt':bind(HERE/'continuation-first/PROCESS-FIRST.json'),'sdkReceipt':bind(HERE/'continuation-first/results/receipt.json')},'totalActualSdkTopLevelCalls':126,'cleanFirstPass121Claimed':False,'firstHarnesErrorsPreserved':failed_first,'firstTenCoreResultsAllMatchedOriginalCI':first_projection},'uniqueCompletedCases':10,'supportedMappings':7,'expectedInconclusiveGuards':3,'uniqueCaseChecksCompleted':80,'actualTamperRejections':70,'cases':accepted,'all127OriginalInputFilesVerifiedBeforeAfterEachProcess':True,'all102ActualRuntimeFilesVerifiedBeforeAfterEachProcess':True,'originalGenericGapsPreserved':True,'nullEarlyProfileCoverageKeptNull':True,'originalObservationBytesRetainedInAllTenCapsules':True,'newDatabaseExecutedHere':False,'sourceClosedReductionClaimed':False,'performanceMeasured':False,'serverAuthenticityCertified':False,'packageOrPublicReleaseAccepted':False,'independentReviewPending':True}
write('AGGREGATE.json',aggregate)
rows=[];base='verification/releases/0.2.7/current-pg-sdk-loop/'
def copyrow(path,target):
 p=ROOT/target;assert not p.exists();rows.append({'source':str(path),'destination':target,**bind(path),'action':'create-exact-new-file'})
for name in ['verify-current-pg-sdk-loop.mjs','PLAN.json','run_once.py']:copyrow(FIRST/name,base+'first/'+name)
for path in sorted((FIRST/'first-run').rglob('*')):
 if path.is_file():copyrow(path,base+'first/first-run/'+path.relative_to(FIRST/'first-run').as_posix())
for name in ['verify-current-pg-sdk-loop.mjs','PLAN.json','run_once.py','HARNESS-FIX.json','HARNESS-FIX.diff','COLLECT-ADOPTION.py']:copyrow(HERE/name,base+'continuation/'+name)
for path in sorted((HERE/'continuation-first').rglob('*')):
 if path.is_file():copyrow(path,base+'continuation/continuation-first/'+path.relative_to(HERE/'continuation-first').as_posix())
copyrow(HERE/'AGGREGATE.json',base+'aggregate.json')
assert len({x['destination'].lower()for x in rows})==len(rows)
write('COPY-PLAN.private.json',{'format':'current027-pg-sdk-loop-exact-copy-plan/v1','status':'UNAPPLIED-INDEPENDENT-REVIEW-PENDING','rawFilesOnly':True,'retainFirstFailedExecution':True,'noRegeneratedReports':True,'sourceArtifactsUnchanged':True,'totalFiles':len(rows),'totalBytes':sum(x['bytes']for x in rows),'rows':rows,'noOverwrite':True,'copyApplied':False})
write('HANDOFF.json',{'format':'current027-pg-sdk-loop-handoff/v1','status':'local-complete-independent-review-pending','aggregate':bind(HERE/'AGGREGATE.json'),'copyPlan':bind(HERE/'COPY-PLAN.private.json'),'fileCount':len(rows),'bytes':sum(x['bytes']for x in rows),'sourceRuntime':'Actual current027 PG-CI102-file closure, not root026 dist','originalPGInputs':'Current hosted10 packets from run40095757205; all127 source/log/projection files unchanged','firstRunnerAndFailedLogsRetained':True,'harnessFix':bind(HERE/'HARNESS-FIX.json'),'sdkTopLevelCalls':{'first':101,'continuation':25,'total':126},'uniqueCaseClosure':{'passed':10,'supported':7,'explicitInconclusive':3,'tamperRejections':70},'sourceClosedReductionClaimed':False,'newDatabaseExecutedHere':False,'noNetworkOrServices':True,'actualSourcesOrMainModified':False,'publicSourceInstructions':'The .mjs script takes externally SHA-pinned PLAN, exact102-file runtime, original127-file input root, and a new output root. Node heap384MiB and available RAM>=1GiB are mandatory. Continuation script intentionally runs only the original two interrupted cases; first script is retained unmodified with its original harness assertion.','next':'Independent review must verify original first failure and fix without changing expected facts; root may apply exact copy plan after review. This is SDK evidence, not package/fresh consumer or public-release acceptance.'})
print(json.dumps({'aggregate':bind(HERE/'AGGREGATE.json'),'copyPlan':bind(HERE/'COPY-PLAN.private.json'),'handoff':bind(HERE/'HANDOFF.json'),'rawFiles':len(rows),'rawBytes':sum(x['bytes']for x in rows),'tenComplete':True,'tamperRejections':70,'actualSdkCalls':126,'firstFailureRetained':True}))
