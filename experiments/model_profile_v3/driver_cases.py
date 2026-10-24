"""Actual business SQL through a scoped driver factory; no handwritten history.

One owned fresh schema per case. This is protocol validation, not a production
integration or formal performance run. The business code never publishes model
facts; its raw statements/results are independently projected afterward.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import threading
import traceback
import uuid
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'integrations/python'))
from moontxnwitness_capture.profiles.model_sql import ModelScope
from moontxnwitness_capture.profiles.model_profile import install_model_profile

CASES=('list-values','list-rollback','list-write-skew','list-unknown-sql',
       'relation-crud','relation-predicate','relation-rollback','relation-write-skew','relation-zero-write','relation-partial-fetch')


def run(connect,output,name):
    model='append-list-v1' if name.startswith('list-') else 'relation-set-v1'
    scope=ModelScope('model_'+uuid.uuid4().hex[:16],model,('x','y') if model=='append-list-v1' else (1,2,3,4),
        () if model=='append-list-v1' else ((('active','eq'),('balance','ge')),(('region','eq'),)))
    initial=() if model=='append-list-v1' else ((1,10,True,'east'),(2,20,True,'east'))
    setup=connect(autocommit=True);observer,control=install_model_profile(setup,scope,output,initial=initial)
    factory=observer.psycopg_factory(connect)
    t=scope.target;actors=[];checks=[]
    def actor():
        c=factory();actors.append(c);return c
    def check(condition,label):
        if not condition:raise AssertionError(label)
        checks.append(label)
    read='SELECT items FROM '+t+' WHERE key=%s'
    append='UPDATE '+t+' SET items=items || %s::jsonb WHERE key=%s RETURNING items'
    row_read='SELECT id,balance,active,region FROM '+t+' WHERE id=%s'
    update='UPDATE '+t+' SET balance=%s,active=%s,region=%s WHERE id=%s RETURNING id,balance,active,region'
    try:
        if name=='list-values':
            c=actor()
            for identity in ('one','two'):
                values=c.execute(append,(json.dumps([{'id':identity,'value':'same'}]),'x')).fetchone()[0]
                check(values[-1]=={'id':identity,'value':'same'},'same business value keeps '+identity)
            check(c.execute(read,('x',)).fetchall()==[([{'id':'one','value':'same'},{'id':'two','value':'same'}],)],'original full list delivery')
            c.commit()
        elif name=='list-rollback':
            c=actor();c.execute(append,(json.dumps([{'id':'aborted','value':'v'}]),'x')).fetchall();c.rollback()
            d=actor();check(d.execute(read,('x',)).fetchall()==[([],)],'rolled-back append is absent');d.commit()
        elif name in ('list-write-skew','relation-write-skew'):
            a,b=actor(),actor()
            # Isolation is a connection option, not a semantic fixture fact.
            import psycopg
            a.isolation_level=b.isolation_level=psycopg.IsolationLevel.REPEATABLE_READ
            if model=='append-list-v1':
                check(a.execute(read,('x',)).fetchone()==([],),'A observes empty x')
                check(b.execute(read,('y',)).fetchone()==([],),'B observes empty y')
                a.execute(append,(json.dumps([{'id':'a','value':'v'}]),'y')).fetchall()
                b.execute(append,(json.dumps([{'id':'b','value':'v'}]),'x')).fetchall()
            else:
                predicate='SELECT id,balance,active,region FROM '+t+' WHERE "active"=%s AND "balance">=%s ORDER BY id'
                check(len(a.execute(predicate,(True,0)).fetchall())==2,'A complete active set')
                check(len(b.execute(predicate,(True,0)).fetchall())==2,'B complete active set')
                a.execute(update,(10,False,'east',1)).fetchall()
                b.execute(update,(20,False,'east',2)).fetchall()
            a.commit();b.commit();checks.append('both genuine Repeatable Read commits acknowledged')
        elif name=='list-unknown-sql':
            c=actor();check(c.execute('SELECT 42').fetchone()==(42,),'unsupported original SQL still executes');c.commit()
        elif name=='relation-crud':
            c=actor();check(c.execute(row_read,(3,)).fetchall()==[],'complete negative point SELECT')
            inserted=c.execute('INSERT INTO '+t+'(id,balance,active,region) VALUES(%s,%s,%s,%s) RETURNING id,balance,active,region',(3,-7,False,'😀')).fetchone()
            check(inserted==(3,-7,False,'😀'),'insert original four columns')
            check(c.execute(update,(9,True,'west',3)).fetchone()==(3,9,True,'west'),'update original four columns')
            check(c.execute('DELETE FROM '+t+' WHERE id=%s RETURNING id,balance,active,region',(3,)).fetchone()==(3,9,True,'west'),'delete original old image')
            check(c.execute(row_read,(3,)).fetchall()==[],'complete point SELECT after delete');c.commit()
        elif name=='relation-predicate':
            c=actor();q='SELECT id,balance,active,region FROM '+t+' WHERE "active"=%s AND "balance">=%s ORDER BY id'
            cur=c.execute(q,(True,0));check(len(cur.description)==4,'hidden metadata not business description')
            check(cur.fetchone()==(1,10,True,'east'),'first real fetch delivery');check(cur.fetchall()==[(2,20,True,'east')],'remaining real delivery')
            q='SELECT id,balance,active,region FROM '+t+' WHERE "region" COLLATE "C"=%s ORDER BY id'
            check(c.execute(q,('absent',)).fetchall()==[],'complete empty AND SELECT');c.commit()
        elif name=='relation-rollback':
            c=actor();c.execute(update,(99,False,'west',1)).fetchall();c.rollback()
            d=actor();check(d.execute(row_read,(1,)).fetchone()==(1,10,True,'east'),'rolled-back row version not committed');d.commit()
        elif name=='relation-zero-write':
            c=actor();check(c.execute(update,(99,False,'west',4)).fetchall()==[],'zero write delivered without fabricated read');c.commit()
        elif name=='relation-partial-fetch':
            c=actor();q='SELECT id,balance,active,region FROM '+t+' WHERE "active"=%s AND "balance">=%s ORDER BY id'
            check(c.execute(q,(True,0)).fetchone()==(1,10,True,'east'),'one delivered row only');c.commit()
        else:raise ValueError('Unknown predeclared case')
        for connection in actors:connection.close()
        observer.finalize(control)
        exported=observer.export_profile(output/'profile-source.json')
        return {'case':name,'status':'producer-passed','actualDatabaseExecution':True,'formalPerformanceMeasurement':False,
            'model':model,'checks':checks,'sourceEnvelope':exported,'analysisCoverageAccepted':False,
            'expectedProjection':'inconclusive' if name in ('list-unknown-sql','relation-zero-write','relation-partial-fetch') else 'supported',
            'expectedSerialStatus':'violation' if name.endswith('write-skew') else 'consistent'}
    finally:
        for connection in actors:
            try:connection.close()
            except Exception:pass
        if not observer._closed:
            try:observer.close()
            except Exception:pass
        setup.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--connection-file',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--case',choices=CASES,action='append');args=parser.parse_args()
    output=Path(args.output).resolve();output.mkdir(parents=True,exist_ok=False)
    config=json.loads(Path(args.connection_file).read_bytes());import psycopg
    if psycopg.__version__!='3.3.6':raise ValueError('Pinned psycopg3.3.6 required')
    def connect(**kwargs):return psycopg.connect(**config,connect_timeout=5,options='-c statement_timeout=10000 -c lock_timeout=5000',**kwargs)
    files=[Path(__file__),*sorted((ROOT/'integrations/python/moontxnwitness_capture').rglob('*.py'))]
    bindings=lambda:{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    before=bindings();results=[];code=0
    for name in args.case or CASES:
        path=output/name
        try:result=run(connect,path,name)
        except BaseException as error:
            code=1;result={'case':name,'status':'failed','errorClass':type(error).__name__,'actualDatabaseExecution':True}
            (output/(name+'-failure.txt')).write_text(traceback.format_exc(),encoding='utf8')
        results.append(result)
    after=bindings();receipt={'kind':'actual-model-driver-profile','status':'passed' if code==0 and before==after else 'failed',
        'actualDatabaseExecution':True,'formalPerformanceMeasurement':False,'sourceBefore':before,'sourceAfter':after,'sourceUnchanged':before==after,'cases':results}
    (output/'database-receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'status':receipt['status'],'cases':len(results)},ensure_ascii=False));return code if before==after else 1


if __name__=='__main__':raise SystemExit(main())
