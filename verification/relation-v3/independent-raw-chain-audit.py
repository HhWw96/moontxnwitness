"""Independent stdlib-only audit of retained fixed-SQL relational observations.

Does not import the producer, trust its success booleans, open a database, build,
or modify any original receipt. Output is a new verification file.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'verification/relation-v3/postgres-2026-10-21/database'
SHA=lambda raw:hashlib.sha256(raw).hexdigest()
LOAD=lambda path:json.loads(path.read_bytes())


def main():
    result={'schema':1,'kind':'independent-relational-raw-chain-audit','passed':False,'complete':False,
            'localDatabaseExecution':False,'localBuild':False,'fullAutomaticSqlCapture':False,
            'implementationSha256':SHA(Path(__file__).read_bytes()),'cases':[]}
    try:
        db=LOAD(BASE/'database-receipt.json')
        assert len(db['scenarios'])==160 and len({c['name'] for c in db['scenarios']})==8
        assert db['roundsPerScenario']==20
        assert db['sourceBindings']==db['sourceBindingsAfter']
        for name,b in db['sourceBindings'].items():
            raw=(ROOT/'experiments/relation_v3'/name).read_bytes()
            assert SHA(raw)==b['sha256'] and len(raw)==b['bytes']
        plan=(ROOT/'experiments/relation_v3/plan.json').read_bytes()
        assert SHA(plan)==db['plan']['sha256']
        for c in db['scenarios']:
            d=BASE/c['path']
            for b in c['artifacts']:
                raw=(d/b['path']).read_bytes();assert SHA(raw)==b['sha256'] and len(raw)==b['bytes']
            trace,metadata,facts=LOAD(d/'trace.json'),LOAD(d/'installation.json'),LOAD(d/'actual-effects.json')
            raw=[json.loads(line) for line in (d/'raw-sql.jsonl').read_bytes().splitlines()]
            assert [int(x['rawSeq']) for x in raw]==list(range(1,len(raw)+1))
            byseq={int(x['rawSeq']):x for x in raw}
            target='"'+metadata['controlledSchema']+'"."accounts"'
            snapshot=byseq[metadata['snapshotBinding']['response']]
            image=lambda r:{'key':r[0],'version':r[4],'values':{'balance':r[1],'active':r[2],'region':r[3]}}
            assert [image(r) for r in snapshot['rows']]==trace['events'][0]['initial']['accounts']
            commits=[r for r in raw if r['kind']=='response' and r.get('tx') is None and r['commandTag']=='COMMIT']
            first_worker=min(int(r['rawSeq']) for r in raw if r.get('tx') is not None)
            assert any(int(snapshot['rawSeq'])<int(r['rawSeq'])<first_worker for r in commits)
            bs={b['event']:b for b in LOAD(d/'semantic-bindings.json')['bindings']}
            writes,marks,outcomes={}, {},{}
            complete_reads,affected_rows=0,0
            for e in trace['events']:
                kind,tx=e['kind'],e.get('tx')
                if kind in ('snapshot','commit_request'):continue
                if kind=='rollback_ok' and 'commitResponse' in e and 'sqlstate' in e['commitResponse']:
                    p=e['commitResponse'];assert p['sqlstate']==p['diagnosticSqlstate'] and p['sqlstate'] in ('40001','40P01') and p['transactionStatus']=='IDLE'
                    errors=[r for r in raw if r['kind']=='error' and r.get('tx')==tx and r.get('sqlstate')==p['sqlstate'] and r.get('diagnosticSqlstate')==p['sqlstate'] and r.get('hasServerResult') and r.get('transactionStatus')=='IDLE' and byseq[int(r['request'])]['sql']=='COMMIT']
                    assert len(errors)==1;outcomes[tx]='aborted';continue
                b=bs[e['seq']];request,response=byseq[b['source']['request']],byseq[b['source']['response']]
                assert request['kind']=='request' and response['kind']=='response' and int(response['request'])==int(request['rawSeq'])
                assert request['tx']==response['tx']==tx
                if kind=='begin':
                    assert request['sql'] in ('BEGIN ISOLATION LEVEL REPEATABLE READ','BEGIN ISOLATION LEVEL SERIALIZABLE') and response['transactionStatus']=='INTRANS'
                    writes[tx],marks[tx]=[],[]
                elif kind=='row_read':
                    ops={'eq':'=','lt':'<','le':'<=','gt':'>','ge':'>='};types=trace['relationSchema']['accounts']['columns']
                    clauses=['"'+p['column']+'"'+(' COLLATE "C"' if types[p['column']]=='text' else '')+ops[p['op']]+'%s' for p in e['predicate']]
                    assert request['sql']=='SELECT id,balance,active,region,version FROM '+target+(' WHERE '+' AND '.join(clauses) if clauses else '')
                    assert request['parameters']==([p['value'] for p in e['predicate']] or None)
                    assert e['complete'] and [image(r) for r in response['rows']]==e['rows']
                    assert int(response['rowcount'])==len(e['rows']) and len(response['columns'])==5
                    complete_reads+=1
                elif kind=='row_write':
                    assert len(response['rows'])==int(response['rowcount'])==1
                    r=response['rows'][0];assert r[0]==e['key']
                    assert response['commandTag'] in ('INSERT 0 1','UPDATE 1','DELETE 1')
                    assert request['sql'].startswith(e['action'].upper()+' ')
                    if e['action']=='delete':assert r[1:]==[e['version'],e['predecessor']] and e['values'] is None
                    else:assert r[4:]==[e['version'],e['predecessor']] and {'balance':r[1],'active':r[2],'region':r[3]}==e['values']
                    writes[tx].append(e);affected_rows+=1
                elif kind=='savepoint':
                    assert request['sql']=='SAVEPOINT "'+e['name']+'"';marks[tx].append((e['instance'],len(writes[tx]),e['name']))
                elif kind in ('rollback_to','release'):
                    at=next(i for i,s in enumerate(marks[tx]) if s[0]==e['instance']);mark=marks[tx][at]
                    assert request['sql']==('ROLLBACK TO SAVEPOINT ' if kind=='rollback_to' else 'RELEASE SAVEPOINT ')+'"'+mark[2]+'"'
                    if kind=='rollback_to':writes[tx]=writes[tx][:mark[1]];marks[tx]=marks[tx][:at+1]
                    else:marks[tx]=marks[tx][:at]
                elif kind=='commit_ok':assert request['sql']=='COMMIT' and response['commandTag']=='COMMIT' and response['transactionStatus']=='IDLE';outcomes[tx]='committed'
                elif kind=='rollback_ok':
                    assert request['sql'] in ('ROLLBACK','COMMIT') and response['commandTag']=='ROLLBACK' and response['transactionStatus']=='IDLE';outcomes[tx]='aborted'
                else:raise AssertionError('Unsupported terminal event '+kind)
            active=[e for tx,es in writes.items() if outcomes.get(tx)=='committed' for e in es]
            actual={r[0]:{'key':r[1],'predecessor':r[2],'action':r[3].lower(),'values':r[6]} for r in facts['effectLedger']}
            assert len(actual)==len(facts['effectLedger'])
            expected={e['version']:{k:e[k] for k in ('key','predecessor','action','values')} for e in active}
            assert actual==expected
            for name,source in facts['sources'].items():
                response=byseq[source['response']];assert int(response['request'])==source['request']
                if name=='effects':assert response['rows']==facts['effectLedger']
                elif name=='state':assert response['rows']==facts['state']
                elif name=='final':assert [image(r) for r in response['rows']]==facts['finalRows']
            assert {r[0]:r[1] for r in facts['state'] if r[2]}=={r['key']:r['version'] for r in facts['finalRows']}
            if c['name']=='serializable-abort-retry':
                assert len([tx for tx,o in outcomes.items() if o=='aborted'])==1
                retries=[e for e in trace['events'] if e['kind']=='begin' and '-retry-' in e['tx']];assert len(retries)==1 and outcomes[retries[0]['tx']]=='committed'
                assert any(r['kind']=='error' and r.get('sqlstate') in ('40001','40P01') and r.get('hasServerResult') for r in raw)
            if c['name']=='delete-reinsert':
                es=[e for e in trace['events'] if e['kind']=='row_write'];assert es[0]['action']=='delete' and es[1]['action']=='insert' and es[1]['predecessor']==es[0]['version']
            result['cases'].append({'name':c['name'],'round':c['round'],'passed':True,'completeQueryReads':complete_reads,'affectedRows':affected_rows,'committedEffects':len(active)})
        result['complete']=True;result['passed']=len(result['cases'])==160
    except Exception as error:result['errorClass']=type(error).__name__;result['error']=str(error).replace(str(ROOT),'<workspace>')
    stamp=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H-%M-%S-%fZ');p=ROOT/'verification/relation-v3'/('raw-chain-independent-'+stamp+'.json')
    data=(json.dumps(result,indent=2)+'\n').encode();p.open('xb').write(data)
    print(json.dumps({'passed':result['passed'],'complete':result['complete'],'cases':len(result['cases']),'receipt':p.relative_to(ROOT).as_posix(),'sha256':SHA(data),'error':result.get('error')}))
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
