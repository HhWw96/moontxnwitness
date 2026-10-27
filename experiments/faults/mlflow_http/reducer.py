"""Bounded deletion-only reduction of a real HTTP fault.
The predicate is supplied by the evidence-checked runner; this module never
turns a timeout, incomplete observation or a model anomaly into a deadlock.
"""
from __future__ import annotations
import argparse,copy,json,shutil,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from protocol import workload,encoded,digest,new_directory,save_new,three_repetitions,MAX_CHECKS,PREDICATE

def _units(case):
    return [('key',k) for k in case['keys']]+[('request',w) for w in case['workers']]

def _delete(case,units):
    remove=set(units)
    workers=[w for w in case['workers'] if ('request',w) not in remove]
    if not workers:return None
    keys=[k for k in case['keys'] if ('key',k) not in remove]
    return workload(case['seed'],keys,workers)

def reduce_case(original,output,evaluate,*,max_checks=MAX_CHECKS,max_evidence_bytes=1024**3,min_free_bytes=64*1024**2):
    """Each check, including baseline/final, makes three fresh oracle calls.
    oneMinimal means every legal remaining key/request single deletion was
    observed not to reproduce in three complete trials after the last removal.
    Unknowns and budget exhaustion prevent that declaration.
    """
    if type(max_checks) is not int or not 2<=max_checks<=MAX_CHECKS:raise ValueError('Candidate checks must be 2..256 including baseline/final')
    if type(max_evidence_bytes) is not int or not 1024<=max_evidence_bytes<=4*1024**3:raise ValueError('Evidence budget outside supported range')
    if type(min_free_bytes) is not int or min_free_bytes<0:raise ValueError('Invalid free-space reserve')
    if original!=workload(original['seed'],original['keys'],original['workers']):raise ValueError('Input must be an unchanged preregistered request subsequence')
    root=new_directory(output);original=copy.deepcopy(original);current=copy.deepcopy(original)
    save_new(root/'original-case.json',original)
    rows=[];trials=0;accounted=0;storage_gap=False
    singles=set();unknown_singles=set()
    def disk_used():
        return sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
    def check(case,phase,removed=()):
        nonlocal trials,accounted,storage_gap
        if len(rows)>=max_checks:raise ValueError('Internal candidate budget violation')
        name=f'check-{len(rows):03d}';folder=new_directory(root/name)
        save_new(folder/'candidate.json',case)
        results=[];bindings=[]
        for i in range(3):
            trialdir=folder/f'trial-{i}'
            complete=disk_used()<max_evidence_bytes and shutil.disk_usage(root).free>=min_free_bytes
            if not complete:
                storage_gap=True;record={'result':{'executionComplete':False,'faultPredicate':False,'predicateDisposition':'unknown'},'resourceGap':'evidence-or-free-space-budget','realChildCommandExecuted':False}
            else:
                try:
                    candidate=copy.deepcopy(case)
                    trials+=1
                    record=evaluate(candidate,trialdir)
                    if candidate!=case:record={'result':{'executionComplete':False,'faultPredicate':False,'predicateDisposition':'unknown'},'resourceGap':'oracle-mutated-input','realChildCommandExecuted':False}
                    if not isinstance(record,dict):raise TypeError('Invalid oracle record')
                    if len(encoded(record))>2*1024**2:raise ValueError('Oracle return exceeds 2 MiB')
                except Exception as error:
                    record={'result':{'executionComplete':False,'faultPredicate':False,'predicateDisposition':'unknown'},'oracleErrorType':type(error).__name__,'realChildCommandExecuted':False}
            trialdir.mkdir(exist_ok=True)
            binding=save_new(trialdir/'reducer-oracle-return.json',record)
            value=record.get('result',{})
            valid=(type(value.get('executionComplete')) is bool and type(value.get('faultPredicate')) is bool
                and value.get('predicateDisposition')==('reproduced' if value.get('executionComplete') and value.get('faultPredicate')
                    else 'not-reproduced' if value.get('executionComplete') else 'unknown'))
            if not valid:value={'executionComplete':False,'faultPredicate':False,'predicateDisposition':'unknown'}
            results.append(value);bindings.append({'path':name+f'/trial-{i}/reducer-oracle-return.json','bytes':binding['bytes'],'sha256':binding['sha256']})
        disposition=three_repetitions(results)
        row={'ordinal':len(rows),'phase':phase,'caseSha256':digest(encoded(case)),'removed':[list(u) for u in removed],
             'keys':len(case['keys']),'requests':len(case['workers']),'disposition':disposition,'trials':bindings}
        save_new(folder/'CHECK.json',row);rows.append(row);accounted=disk_used()
        if accounted>=max_evidence_bytes:storage_gap=True
        return disposition
    baseline=check(current,'baseline')
    status='original-inconclusive' if baseline=='unknown' else 'original-not-reproduced'
    final=None
    if baseline=='reproduced':
        status='retained-original';granularity=2
        while len(rows)<max_checks-1 and not storage_gap:
            units=_units(current);n=len(units)
            if n<1:break
            granularity=min(granularity,n);chunk=(n+granularity-1)//granularity;accepted=False
            for start in range(0,n,chunk):
                removed=units[start:start+chunk];candidate=_delete(current,removed)
                if candidate is None:continue
                if len(rows)>=max_checks-1 or storage_gap:break
                result=check(candidate,'deletion',removed)
                if len(removed)==1:
                    if result=='not-reproduced':singles.add(removed[0])
                    elif result=='unknown':unknown_singles.add(removed[0])
                if result=='reproduced':
                    current=candidate;status='reduced';singles.clear();unknown_singles.clear();accepted=True
                    granularity=max(2,granularity-1);break
            if accepted:continue
            if granularity>=n:break
            granularity=min(n,granularity*2)
        # One fresh group is reserved for final revalidation, never supplied by a cache.
        final=check(current,'final')
        if final!='reproduced':status='final-inconclusive' if final=='unknown' else 'final-not-reproduced'
    save_new(root/'final-case.json',current)
    legal=[u for u in _units(current) if _delete(current,[u]) is not None]
    one_minimal=(baseline==final=='reproduced' and not storage_gap and all(u in singles for u in legal) and not unknown_singles)
    report={'format':'moontxnwitness-mlflow-http-reduction/v1','predicate':PREDICATE,'status':status,
        'originalCaseSha256':digest(encoded(original)),'finalCaseSha256':digest(encoded(current)),
        'originalKeys':len(original['keys']),'finalKeys':len(current['keys']),
        'originalRequests':len(original['workers']),'finalRequests':len(current['workers']),
        'maxCandidateChecks':max_checks,'candidateChecks':len(rows),'repetitionsPerCandidate':3,'oracleCallsAttempted':trials,
        'budgetIncludesBaselineAndFinal':True,'cacheUsed':False,'checks':rows,
        'maxEvidenceBytes':max_evidence_bytes,'evidenceBudgetCheckedBetweenTrials':True,'observedEvidenceBytesBeforeSummary':accounted,'storageGap':storage_gap,
        'oneMinimal':one_minimal,'minimalityUnit':'one original metric key (all request occurrences), or one original HTTP request',
        'completeSingleDeletions':len(set(legal)&singles),'requiredSingleDeletions':len(legal),'unknownSingleDeletions':len(unknown_singles),
        'finalVerifiedReproduced':final=='reproduced','actualDatabaseExecutionCertifiedByReducer':False,
        'isolationViolationClaim':False,'G2Claim':False,'sourceFactsModified':False}
    save_new(root/'REDUCTION.json',report)
    return report

def main():
    p=argparse.ArgumentParser();p.add_argument('--execute-real-http',action='store_true')
    for name in ('case-file','connection-file','upstream-parent','project-root','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--python',type=Path,default=Path(sys.executable));p.add_argument('--manifest',type=Path,default=Path(__file__).with_name('upstream-manifest.json'));p.add_argument('--max-checks',type=int,default=MAX_CHECKS)
    args=p.parse_args()
    if not args.execute_real_http:raise ValueError('Explicit real execution flag required')
    from campaign import execute_one
    case=json.loads(args.case_file.read_bytes())
    def evaluate(candidate,output):
        return execute_one(candidate,'before',output,python=args.python,connection_file=args.connection_file,
            upstream_parent=args.upstream_parent,project_root=args.project_root,manifest_path=args.manifest)
    report=reduce_case(case,args.output,evaluate,max_checks=args.max_checks)
    print(json.dumps({'status':report['status'],'candidateChecks':report['candidateChecks'],'oneMinimal':report['oneMinimal'],'finalVerifiedReproduced':report['finalVerifiedReproduced']}))
    return 0 if report['finalVerifiedReproduced'] else 1
if __name__=='__main__':raise SystemExit(main())
