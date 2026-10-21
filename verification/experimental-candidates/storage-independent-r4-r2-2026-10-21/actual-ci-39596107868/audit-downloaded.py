"""Static independent review of real two-platform fault artifacts, not a scenario rerun."""
from pathlib import Path
import hashlib
import json
import zipfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
checks=[]
def sha(raw):return hashlib.sha256(raw).hexdigest()
def binding(path):
    h=hashlib.sha256();n=0
    with path.open('rb') as stream:
        while block:=stream.read(65536):n+=len(block);h.update(block)
    return {'bytes':n,'sha256':h.hexdigest()}
def load(path):return json.loads(path.read_bytes())
def check(name,value):
    checks.append({'name':name,'passed':bool(value)})
    if not value:raise AssertionError(name)

result={'schema':1,'kind':'independent-storage-r4-probe-r2-downloaded-actual-review','run':39596107868,
        'workflowCommit':'6760b862d1966ba15553d5ff9e437fe110b747f7','passed':False,'complete':False,
        'checks':checks,'actualOriginalFaultRunPreserved':39594130622,'originalSetupFailureRunPreserved':39593224692,
        'originalR3FailuresChanged':False,'oldR3Fault':'inapplicable-not-executed, never counted as pass',
        'postCommitNativeAllDiagnosticIOFail':'unexecuted separate boundary; not a data-sync waiver',
        'localFilesystemScenarioExecuted':False,'localNativeLockExecuted':False,
        'localNodeCompileDatabasePerformanceExecuted':False,'stableReleaseAccepted':False,'platforms':[]}
try:
    run=load(HERE/'run.json');jobs=load(HERE/'jobs.json')['jobs'];arts=load(HERE/'artifacts.json')['artifacts']
    check('Actual workflow and both jobs succeeded at fixed revision commit',run['head_sha']==result['workflowCommit'] and
          run['conclusion']=='success' and len(jobs)==2 and all(j['conclusion']=='success' for j in jobs))
    expected_events=load(ROOT/'artifacts/r4-independent-r2-draft/events-v1.json')
    for platform in ('ubuntu-24.04','windows-2022'):
        prefix='independent-storage-r4-'+platform;p=HERE/prefix;scenario=p/'scenario'
        metadata=next(a for a in arts if a['name']==prefix);zip_binding=binding(HERE/(prefix+'.zip'))
        check(platform+': actual ZIP digest and size matches GitHub API',metadata['digest']=='sha256:'+zip_binding['sha256'] and metadata['size_in_bytes']==zip_binding['bytes'])
        wrapper=load(p/'execution-receipt.json');actual=load(scenario/'independent-r4-receipt.json')
        check(platform+': actual complete two-case24 check execution',wrapper['passed'] and wrapper['exitCode']==0 and
              wrapper['actualReceiptBinding']==binding(scenario/'independent-r4-receipt.json') and actual['passed'] and actual['complete'] and
              len(actual['cases'])==2 and actual['checksCount']==24 and actual['independentProbeRevision']==2)
        check(platform+': frozen actual candidate and independent source bytes unchanged',actual['sourceBindingsBefore']==actual['sourceBindingsAfter'] and
              wrapper['sourceBindingsUnchanged'] and wrapper['independentBindingsUnchanged'] and
              actual['candidateIndexSha256']=='223e61bcb41b64f2d47f0d96e8c8e99e88a1a9c1fed856467a7b01a45c920124' and
              actual['sourceBindingsBefore']['candidate/managed.py']['sha256']=='290913bd62c125f850af1cbd6e11c4ca268ff49047f48fbc51fe7939961ebd8c' and
              actual['sourceBindingsBefore']['independent/counterexample.py']['sha256']=='2201e4a8fb11e3f734d37535246a23b86a1735123a3f14795382dbd4607b89ce' and
              actual['sourceBindingsBefore']['independent/contract-v1.json']['sha256']=='66e3b568335c8f85ba16b1ac245b8b3a25ff3a8e52d332b26320b5a4eed64670')
        platform_summary={'platform':platform,'artifact':zip_binding,'actualReceipt':binding(scenario/'independent-r4-receipt.json'),'cases':[],'checksPassed':24}
        for index,case in enumerate(actual['cases']):
            directory=scenario/('primary' if index==0 else 'primary-and-marker');label=platform+': '+case['name']
            check(label+': all actual checks completed and passed',case['passed'] and case['executionComplete'] and
                  len(case['checks'])==(11 if index==0 else 12) and all(x['passed'] for x in case['checks']))
            file_map=case['afterVerificationFiles']
            check(label+': every final raw file matches its recorded hash and bytes',all(binding(directory/name)==value for name,value in file_map.items()))
            intent=load(directory/'prepared-original-bytes/prune-intent.json');prepared=case['prepared'];owner=load(directory/'prepared-original-bytes/operation.lock')
            check(label+': original prepared intent/manifest/owner bytes retained',intent==prepared['intent'] and owner==prepared['owner'] and
                  load(directory/'prepared-original-bytes/manifest.json')==prepared['manifest'] and
                  prepared['manifest']['pending']==intent['plan'] and prepared['manifest']['generation']==intent['baseGeneration']+1 and
                  owner=={'kind':'archive-operation/1','nonce':intent['nonce'],'token':intent['operationToken']})
            raw_mutex=(directory/'prepared-original-bytes/coordination.lock').read_bytes()
            canonical=json.dumps({'kind':'archive-coordination/1','nonce':owner['nonce']},sort_keys=True,separators=(',',':')).encode()
            baseline=case['permanentMutexBefore']
            check(label+': actual permanent inode and full original canonical nonce bytes retained',raw_mutex==canonical and
                  baseline==case['permanentMutexAfter'] and
                  {k:baseline[k] for k in ('bytes','sha256')}==binding(directory/'store/coordination.lock')==binding(directory/'prepared-original-bytes/coordination.lock'))
            probes=[('prepared',prepared['permanentMutexProbe'])]+[('primary',x['nativeProbe']) for x in case['primaryFaults']]+[('secondary',x['nativeProbe']) for x in case['secondaryFaults']]
            for name,probe in probes:
                raw_record=load(directory/('native-probe-'+name+'.json'))
                check(label+': '+name+' complete native output saved before assertions',probe['recordBinding']==binding(directory/('native-probe-'+name+'.json')) and
                      raw_record=={k:v for k,v in probe.items() if k!='recordBinding'} and json.loads(probe['rawStdout'])==probe['stdout'])
                child=probe['stdout'];authority=probe['authorityBefore']
                check(label+': '+name+' holding handle full bytes and actual child native same-inode contention',
                      authority==probe['authorityAfter'] and {k:authority[k] for k in baseline}==baseline and authority['nonce']==owner['nonce'] and
                      probe['exitCode']==17 and child['phase']=='native-lock' and child['result']=='blocked' and not child['authorityBytesReadByProbe'] and
                      (child['device'],child['inode'])==(authority['device'],authority['inode']) and
                      child['nativeCallStage']==('msvcrt.LK_NBLCK/1' if platform=='windows-2022' else 'fcntl.LOCK_EX|LOCK_NB') and
                      child['errno']==(13 if platform=='windows-2022' else 11))
            check(label+': actual fault occurred only at final protected sync331 and marker357',len(case['primaryFaults'])==1 and
                  len(case['secondaryFaults'])==index and case['primaryFaults'][0]['callsite']=={'file':'managed.py','function':'_release_operation','line':331} and
                  all(x['callsite']=={'file':'managed.py','function':'_failure_marker','line':357} for x in case['secondaryFaults']) and
                  all(x['pending'] is None and x['completedPlan']==intent['plan'] and x['owner']==owner and not x['intentPresent']
                      for x in case['primaryFaults']+case['secondaryFaults']))
            check(label+': actual original persistent owner guard survives and fresh/live public verification refuses',
                  load(directory/'store/operation.lock')==owner==case['afterFailureOwner'] and
                  not case['sameInstanceVerify']['complete'] and not case['freshInstanceVerify']['complete'] and
                  case['actualRecoveryError']['isOSError'] and
                  case['actualRecoveryError']['message']=='Independent r4 actual protected final data-sync IO failure')
            marker=directory/'store/operation-failed.json'
            check(label+': second actual marker persistence fault does not remove owner',
                  not marker.exists() if index else marker.exists() and load(marker)==case['afterFailureMarker'])
            check(label+': actual original index/cache/fence/archive are unchanged',case['originalBindingsBefore']==case['originalBindingsAfter'] and
                  case['originalBindingsAfter']=={'sourceIndex':binding(directory/'journal/journal-index.json'),
                  'transactionCache':binding(directory/'journal/transactions.sqlite3'),'sourceFence':binding(directory/'journal/writer.lock'),
                  'originalArchive':binding(directory/'original-source.zip')})
            with zipfile.ZipFile(directory/'original-source.zip') as archive:
                original_index=json.loads(archive.read('journal-index.json'));all_events=[]
                assert sha(archive.read('journal-index.json'))==case['originalBindingsBefore']['sourceIndex']['sha256']
                for segment in original_index['segments']:
                    data=archive.read(segment['name']);assert sha(data)==segment['sha256'] and len(data)==segment['bytes']
                    all_events.extend(json.loads(line) for line in data.splitlines())
            check(label+': actual archive retains all18 frozen original events and seq',all_events==expected_events and [e['seq'] for e in all_events]==list(range(1,19)))
            platform_summary['cases'].append({'name':case['name'],'actualRawFilesVerified':len(file_map),'nativeProbes':len(probes),
                  'nativeStage':case['primaryFaults'][0]['nativeProbe']['stdout']['nativeCallStage'],
                  'errno':case['primaryFaults'][0]['nativeProbe']['stdout']['errno'],'actualChecks':len(case['checks']),'passed':True})
        result['platforms'].append(platform_summary)
    result.update(passed=True,complete=True,actualIndependentCases=4,actualSafetyChecks=48,
                  exactCandidateAndInputsUnchanged=True,oldR3NotCountedAsPass=True,
                  downloadReceipt=binding(HERE/'download-receipt.json'))
except Exception as error:
    result.update(errorClass=type(error).__name__,error=str(error).replace(str(ROOT),'<repository>'))
result['checksCount']=len(checks)
p=HERE/'independent-actual-audit.json'
p.open('x',encoding='utf-8',newline='\n').write(json.dumps(result,indent=2)+'\n')
print(json.dumps({'passed':result['passed'],'checks':len(checks),'receiptSha256':binding(p)['sha256']}))
raise SystemExit(0 if result['passed'] else 1)
