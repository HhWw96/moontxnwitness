"""One owned native MLflow Flask service, real TCP HTTP requests and actual PG evidence.
Optional dependencies import only after explicit --execute-real-http. No upstream code patch.
"""
from __future__ import annotations
import argparse,contextvars,http.client,inspect,json,os,re,sys,threading,time,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from diagnostics import RunDiagnostics
from protocol import COMMITS,ROUTE,Log,check_sources,classify,digest,encoded,file_digest,is_lock,new_directory,request_body,save_new,artifact_bindings,fixed_behavior
WORKER=contextvars.ContextVar('mlflow_http_worker',default=None)

class Schedule:
    def __init__(self,workers,log,timeout=15):
        self.state={w:{'pending':0,'done':0,'pid':None} for w in workers};self.lock=threading.RLock()
        self.barrier=threading.Barrier(len(workers));self.release=threading.Event();self.error=None
        self.timeout=timeout;self.log=log
    def before(self,worker,pid):
        with self.lock:
            self.state[worker]['pid']=pid;self.state[worker]['pending']+=1;first=self.state[worker]['pending']==1
        if first:
            self.log.append({'kind':'first-lock-pending','worker':worker,'pid':pid})
            try:self.barrier.wait(self.timeout)
            except threading.BrokenBarrierError:self.error='first-lock-entry-barrier-timeout';self.release.set()
    def after(self,worker):
        with self.lock:self.state[worker]['done']+=1;first=self.state[worker]['done']==1
        if first:
            self.log.append({'kind':'first-lock-returned','worker':worker})
            if not self.release.wait(self.timeout):self.error='first-lock-release-timeout';self.release.set()
    def snapshot(self):
        with self.lock:return {k:dict(v) for k,v in self.state.items()}
    @staticmethod
    def decide(state,waits,finished):
        if all(v['done']>=1 for v in state.values()):return 'all-first-locks-returned'
        done={v['pid'] for v in state.values() if v['done']>=1}
        for pid,kind,event,blockers in waits:
            if kind=='Lock' and any(pid==v['pid'] and v['done']==0 and v['pending']>=1 for v in state.values()) and done.intersection(blockers):return 'first-lock-returned-and-other-observed-blocked-by-it'
        if finished:return 'all-http-requests-completed'
        return None

def native_modules(root):
    rows=[]
    for name,module in sorted(sys.modules.items()):
        if name=='mlflow' or name.startswith('mlflow.'):
            path=getattr(module,'__file__',None)
            if path:
                p=Path(path).resolve();relative=p.relative_to(root).as_posix()
                rows.append({'module':name,'file':relative,'sha256':file_digest(p)})
    return rows

def run_with_diagnostics(args):
    if not args.execute_real_http:raise ValueError('Explicit --execute-real-http is required')
    output=new_directory(args.output)
    with RunDiagnostics(output.parent) as diagnostics:
        return run(args,output,diagnostics)

def run(args,output,diagnostics):
    try:
        import psycopg
        from psycopg import sql
        import sqlalchemy as sa
        from sqlalchemy import event
        from sqlalchemy.pool import Pool
        from sqlalchemy.engine import Engine
        from werkzeug.serving import ThreadedWSGIServer,WSGIRequestHandler
    except ImportError as error:
        save_new(output/'receipt.json',{'status':'not-executed','actualDatabaseExecution':False,'actualHttpExecution':False,'missingDependency':error.name});return 3
    if sa.__version__!='2.0.55' or psycopg.__version__!='3.3.6':raise ValueError('Frozen SQLAlchemy/psycopg versions required')
    manifest=json.loads(args.manifest.read_bytes());case=json.loads(args.case_file.read_bytes())
    from protocol import workload
    if case!=workload(case['seed'],case['keys'],tuple(case['workers'])):raise ValueError('Case must be an original preregistered request subsequence')
    upstream=args.upstream_root.resolve();source_before=diagnostics.call('source-before',lambda:check_sources(args.label,upstream,manifest))
    diagnostics.mark('source-before-verified')
    save_new(output/'STARTED.json',{'label':args.label,'commit':COMMITS[args.label],'caseSha256':digest(encoded(case)),'sourceBinding':source_before,'actualExecutionNotCompleted':True})
    private=json.loads(args.connection_file.read_text(encoding='utf-8'))
    if not isinstance(private,dict) or not private.get('dbname'):raise ValueError('Explicit dedicated PostgreSQL connection object required')
    private.setdefault('connect_timeout',5)
    schema='mtw_mlhttp_'+uuid.uuid4().hex[:20]
    with psycopg.connect(**private,autocommit=True) as probe:
        if not 180000<=probe.info.server_version<190000:raise ValueError('PostgreSQL 18 required')
        server_version=probe.info.parameter_status('server_version')
        probe.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    params=dict(private);params['options']=(params.get('options','')+' -c search_path='+schema+' -c statement_timeout=25000 -c lock_timeout=20000 -c deadlock_timeout=100').strip()
    query={k:str(v) for k,v in params.items() if k not in ('user','password','host','port','dbname')}
    uri=sa.URL.create('postgresql+psycopg',username=params.get('user'),password=params.get('password'),host=params.get('host','127.0.0.1'),port=int(params.get('port',5432)),database=params['dbname'],query=query).render_as_string(hide_password=False)
    os.environ.update({'_MLFLOW_SERVER_FILE_STORE':uri,'_MLFLOW_SERVER_REGISTRY_STORE':uri,'_MLFLOW_SERVER_ARTIFACT_ROOT':(output/'artifacts').as_uri(),'MLFLOW_TRACKING_URI':uri,'MLFLOW_ENABLE_WORKSPACES':'false','MLFLOW_SERVER_ENABLE_JOB_EXECUTION':'false','MLFLOW_ENABLE_TELEMETRY':'false','PYTHONDONTWRITEBYTECODE':'1'})
    sys.path.insert(0,str(args.project_root/'integrations/python'))
    from moontxnwitness_capture.instrumentation import Instrumentation,DiagnosticConnection
    from moontxnwitness_capture.journal_v3 import JournalReader
    observer=Instrumentation(output/'capture',max_lifecycle_bytes=32*1024*1024,max_lifecycle_records=200000)
    observer.gap('original_http_execution_fault_only','Raw native service SQL and errors; no verified relation/history mapping or model violation claim.')
    sql_log=Log(output/'sql.jsonl');http_log=Log(output/'http.jsonl');control_log=Log(output/'schedule.jsonl');call_log=Log(output/'native-calls.jsonl',max_bytes=2*1024*1024)
    schedule=Schedule(case['workers'],control_log);engines=set();listeners=[];results={};call_seen=set();call_lock=threading.Lock()
    def request_worker():return WORKER.get()
    def record(phase,conn,statement=None,parameters=None,**extra):
        driver=conn.connection.dbapi_connection
        sql_log.append({'phase':phase,'worker':request_worker(),'pid':getattr(getattr(driver,'info',None),'backend_pid',None),'txId':getattr(driver,'_tx',None),'sql':statement,'targetLock':is_lock(statement),'parameters':observer.encode(parameters),**extra})
    def checkout(dbapi,record,proxy):
        native=getattr(dbapi,'_raw',dbapi)
        if isinstance(native,psycopg.Connection) and native.info.dbname==params['dbname']:
            wrapped=observer.wrap(dbapi);record.dbapi_connection=wrapped;proxy.dbapi_connection=wrapped
            observer.note('pool-checkout',connection=getattr(wrapped,'_identity',None),initialNativeDialectSetupOutsideObservation=True)
    def before(conn,cursor,statement,parameters,context,many):
        if conn.dialect.name!='postgresql':return
        engines.add(conn.engine);record('before',conn,statement,parameters,executemany=bool(many))
        w=request_worker()
        if w in schedule.state and is_lock(statement):schedule.before(w,conn.connection.dbapi_connection.info.backend_pid)
    def after(conn,cursor,statement,parameters,context,many):
        if conn.dialect.name!='postgresql':return
        record('after',conn,statement,rowcount=cursor.rowcount,executemany=bool(many))
        if request_worker() in schedule.state and is_lock(statement):schedule.after(request_worker())
    def failure(context):
        error=context.original_exception;record('error',context.connection,context.statement,context.parameters,sqlstate=getattr(error,'sqlstate',None),diagSqlstate=getattr(getattr(error,'diag',None),'sqlstate',None),nativePgResult=isinstance(error,psycopg.Error) and getattr(error,'pgresult',None) is not None,exceptionModule=type(error).__module__,driverClass=type(error).__name__)
    def profile(frame,what,arg):
        if what!='call' or request_worker() not in case['workers']:return
        module=frame.f_globals.get('__name__');name=frame.f_code.co_name
        if (module=='mlflow.server.handlers' and name=='_log_batch') or (module=='mlflow.store.tracking.sqlalchemy_store' and name in ('log_batch','_log_metrics','_log_metrics_once','_update_latest_metrics_if_necessary')):
            with call_lock:
                key=(request_worker(),module,name)
                if key not in call_seen:
                    call_seen.add(key);call_log.append({'kind':'native-call','worker':key[0],'module':module,'function':name,'source':Path(frame.f_code.co_filename).resolve().relative_to(upstream).as_posix()})
    for target,name,callback in [(Pool,'checkout',checkout),(Engine,'before_cursor_execute',before),(Engine,'after_cursor_execute',after),(Engine,'handle_error',failure)]:event.listen(target,name,callback);listeners.append((target,name,callback))
    server=None;server_thread=None;threads=[];controller_complete=False;final_rows=[];final_http={};native_route=False;runtime_modules=[];case_error=None;cleanup_complete=False;threads_alive=[];cleanup_errors=[]
    try:
        sys.path.insert(0,str(upstream))
        import mlflow
        from mlflow.server import app,handlers
        if mlflow.__version__!=manifest['sources'][args.label]['version']:raise ValueError('Imported source version differs')
        endpoint=next(r.endpoint for r in app.url_map.iter_rules() if r.rule==ROUTE and 'POST' in r.methods)
        handler=inspect.unwrap(app.view_functions[endpoint])
        native_route=(handler.__name__=='_log_batch' and Path(inspect.getsourcefile(handler)).resolve()==upstream/'mlflow/server/handlers.py')
        if not native_route:raise ValueError('Native original HTTP log_batch route not proved')
        @app.before_request
        def identify():
            from flask import request,g
            g.mtw_token=WORKER.set(request.headers.get('X-MTW-Worker'))
        @app.teardown_request
        def clear(error):
            from flask import g
            token=getattr(g,'mtw_token',None)
            if token is not None:WORKER.reset(token)
        class Quiet(WSGIRequestHandler):
            def log_request(self,code='-',size='-'):pass
        class OwnedHTTPServer(ThreadedWSGIServer):
            # Track before start, including request workers the native server marks daemon.
            def __init__(self,*values,**options):
                self.owned_requests=[];self.owned_lock=threading.RLock();super().__init__(*values,**options)
            def process_request(self,request,address):
                thread=threading.Thread(target=self.process_request_thread,args=(request,address),name='original-http-request',daemon=True)
                with self.owned_lock:self.owned_requests.append(thread)
                thread.start()
            def request_threads(self):
                with self.owned_lock:return list(self.owned_requests)
        previous_profile=threading.getprofile();threading.setprofile(profile)
        server=OwnedHTTPServer('127.0.0.1',0,app,handler=Quiet)
        port=server.server_port;server_thread=threading.Thread(target=server.serve_forever,name='original-mlflow-http',daemon=True);server_thread.start()
        def call(path,body=None,worker=None):
            raw=b'' if body is None else encoded(body);method='GET' if body is None else 'POST'
            http_log.append({'kind':'request','worker':worker,'method':method,'path':path,'bodyUtf8':raw.decode(),'bodySha256':digest(raw),'clientRetries':0})
            client=http.client.HTTPConnection('127.0.0.1',port,timeout=55);started=time.monotonic_ns()
            try:
                client.request(method,path,body=raw if body is not None else None,headers={'Content-Type':'application/json','X-MTW-Worker':worker or 'setup'})
                response=client.getresponse();data=response.read(2*1024*1024+1)
                if len(data)>2*1024*1024:raise ValueError('Actual HTTP response exceeded budget')
                http_log.append({'kind':'response','worker':worker,'path':path,'status':response.status,'bodyUtf8':data.decode('utf8'),'bodySha256':digest(data),'elapsedNs':time.monotonic_ns()-started})
                return response.status,json.loads(data or b'{}')
            except Exception as error:
                http_log.append({'kind':'transport-error','worker':worker,'path':path,'class':type(error).__name__});raise
            finally:client.close()
        status,value=call('/api/2.0/mlflow/experiments/create',{'name':'mtw-http-'+uuid.uuid4().hex})
        if status!=200:raise ValueError('Native experiment initialization failed')
        status,value=call('/api/2.0/mlflow/runs/create',{'experiment_id':value['experiment_id'],'start_time':case['seed']*10,'tags':[]})
        if status!=200:raise ValueError('Native run initialization failed')
        run_id=value['run']['info']['run_id']
        initial={'run_id':run_id,'metrics':[{'key':k,'value':0.0,'timestamp':0,'step':0} for k in case['keys']],'params':[],'tags':[]}
        status,_=call(ROUTE,initial,'prime')
        if status!=200:raise ValueError('Native metric priming failed')
        if type(handlers._tracking_store).__module__!='mlflow.store.tracking.sqlalchemy_store':raise ValueError('Native full SQLAlchemy store not used')
        save_new(output/'native-route.json',{'nativeApplication':'mlflow.server:app','route':ROUTE,'endpoint':endpoint,'handlerModule':handler.__module__,'handlerSource':'mlflow/server/handlers.py','registeredRules':len(list(app.url_map.iter_rules())),'storeClass':type(handlers._tracking_store).__name__,'storeModule':type(handlers._tracking_store).__module__,'runId':run_id,'actualTCPAddress':'127.0.0.1','port':port,'upstreamASTExtractedOrPatched':False})
        def request(w):
            try:results[w]=call(ROUTE,request_body(case,w,run_id),w)[0]
            except Exception:results[w]=None
        for w in case['workers']:
            thread=threading.Thread(target=request,args=(w,),name='http-client-'+w,daemon=True);threads.append(thread);thread.start()
        deadline=time.monotonic()+18
        with psycopg.connect(**private,autocommit=True) as monitor:
            while time.monotonic()<deadline:
                state=schedule.snapshot();pids=[s['pid'] for s in state.values() if s['pid']]
                waits=monitor.execute('SELECT pid,wait_event_type,wait_event,pg_blocking_pids(pid) FROM pg_stat_activity WHERE pid=ANY(%s)',(pids,)).fetchall() if pids else []
                reason=Schedule.decide(state,waits,len(results)==len(case['workers']))
                if reason:
                    control_log.append({'kind':'release','reason':reason,'state':state,'actualPgWaits':[list(r) for r in waits]});controller_complete=True;break
                if schedule.error:break
                time.sleep(.01)
        schedule.release.set()
        for thread in threads:thread.join(60)
        if any(t.is_alive() for t in threads):raise TimeoutError('HTTP clients still alive; no complete result')
        status,value=call('/api/2.0/mlflow/runs/get?run_id='+run_id)
        if status!=200:raise ValueError('Native final run read failed')
        final_http=value;save_new(output/'final-native-http-run.json',value)
        with psycopg.connect(**private,autocommit=True) as monitor:
            final_rows=monitor.execute(sql.SQL('SELECT key,value,step,timestamp FROM {}.latest_metrics WHERE run_uuid=%s ORDER BY key').format(sql.Identifier(schema)),(run_id,)).fetchall()
        if {m['key'] for m in value['run']['data'].get('metrics',[])}!=set(case['keys']):raise ValueError('Native HTTP latest metric set differs from captured request keys')
        runtime_modules=native_modules(upstream)
        expected={r['path']:r['sha256'] for r in manifest['sources'][args.label]['files']}
        if any(m['file'] not in expected or expected[m['file']]!=m['sha256'] for m in runtime_modules):raise ValueError('An imported MLflow module is outside frozen original bytes')
    except BaseException as error:case_error=type(error).__name__
    finally:
        schedule.release.set()
        def cleanup(action):
            try:return action()
            except Exception as error:cleanup_errors.append(type(error).__name__)
        for thread in threads:cleanup(lambda thread=thread:thread.join(2))
        if server is not None:
            if server_thread is not None and server_thread.is_alive():cleanup(server.shutdown)
            cleanup(server.server_close)
        owned=threads+([server_thread] if server_thread is not None else [])+(server.request_threads() if server is not None else [])
        deadline=time.monotonic()+10
        for thread in owned:cleanup(lambda thread=thread:thread.join(max(0,deadline-time.monotonic())))
        threads_alive=[thread.name for thread in owned if thread.is_alive()]
        cleanup_complete=bool(server is not None and server.socket.fileno()==-1 and not threads_alive and not cleanup_errors)
        threading.setprofile(locals().get('previous_profile'))
        for engine in engines:cleanup(engine.dispose)
        for target,name,callback in reversed(listeners):cleanup(lambda target=target,name=name,callback=callback:event.remove(target,name,callback))
        cleanup(lambda:diagnostics.call('observer-close',lambda:observer.close(source_closed=False)));cleanup(lambda:diagnostics.call('diagnostic-export',lambda:observer.export_diagnostic(output/'capture.json')))
        logs={}
        for name,log in [('sql',sql_log),('http',http_log),('schedule',control_log),('calls',call_log)]:
            value=cleanup(log.close)
            logs[name]=value if value is not None else {'sealed':False,'records':log.count,'bytes':log.path.stat().st_size,'sha256':file_digest(log.path)}
        if cleanup_errors:cleanup_complete=False;case_error=case_error or 'owned-resource-cleanup-failed'
        os.environ.pop('_MLFLOW_SERVER_FILE_STORE',None);os.environ.pop('_MLFLOW_SERVER_REGISTRY_STORE',None);os.environ.pop('MLFLOW_TRACKING_URI',None)
    source_after=diagnostics.call('source-after',lambda:check_sources(args.label,upstream,manifest))
    from protocol import read_log
    try:http_rows=read_log(output/'http.jsonl');sql_rows=read_log(output/'sql.jsonl');calls=read_log(output/'native-calls.jsonl')
    except Exception as error:http_rows=[];sql_rows=[];calls=[];case_error=case_error or 'unsealed-'+type(error).__name__
    chain=all(any(r.get('worker')==w and r.get('module')==m and r.get('function')==f for r in calls) for w in case['workers'] for m,f in [('mlflow.server.handlers','_log_batch'),('mlflow.store.tracking.sqlalchemy_store','log_batch'),('mlflow.store.tracking.sqlalchemy_store','_update_latest_metrics_if_necessary')])
    diagnostics.mark('journal-metadata-verify-start')
    meta={'actualHttpExecution':server is not None,'actualDatabaseExecution':True,'nativeRouteVerified':native_route and chain,'sourceUnchanged':source_before==source_after,'collectionComplete':all(v['sealed'] for v in logs.values()) and JournalReader(observer.journal.path).verify().valid,'controllerComplete':controller_complete and schedule.error is None,'threadsStillAlive':threads_alive,'serviceStopped':cleanup_complete,'caseError':case_error}
    diagnostics.mark('journal-metadata-verify-done')
    if case_error:meta['collectionComplete']=False
    result=classify(case,meta,http_rows,sql_rows,final_rows)
    fixed_ok=bool(result['executionComplete'] and fixed_behavior(case,http_rows,final_rows,final_http))
    receipt={'schema':2,'format':'moontxnwitness-mlflow-http-run/v2','evidenceAlgorithm':'original-http-evidence-2','label':args.label,'commit':COMMITS[args.label],'workload':case,'workloadSha256':digest(encoded(case)),'schemaRetained':schema,'serverVersion':server_version,'metadata':meta,'result':result,'sourceBefore':source_before,'sourceAfter':source_after,'runtimeModules':runtime_modules,'logs':logs,'nativeCallChainObserved':chain,'sourceCollectionDiagnosticOnly':True,'fixedBehaviorChecked':fixed_ok if args.label=='fixed' else None,'actualHttpExecution':meta['actualHttpExecution'],'actualDatabaseExecution':True,'passed':result['faultPredicate'] if args.label=='before' else fixed_ok,'isolationViolationClaim':False,'G2Claim':False,'serverOrDatabaseAuthenticityCertified':False,'versions':{'sqlalchemy':sa.__version__,'psycopg':psycopg.__version__},'controlledTimingOnly':True,'upstreamLockOrderOrRetrySemanticsRewritten':False}
    save_new(output/'final-rows.json',final_rows)
    try:receipt['artifactBindings']=artifact_bindings(output)
    except Exception as error:
        receipt['artifactBindings']=[];receipt['passed']=False;receipt['metadata']['collectionComplete']=False
        receipt['metadata']['caseError']=receipt['metadata']['caseError'] or 'artifact-closure-'+type(error).__name__
        receipt['result']=classify(case,receipt['metadata'],http_rows,sql_rows,final_rows)
        receipt['fixedBehaviorChecked']=False if args.label=='fixed' else None
    diagnostics.mark('before-final-receipt')
    save_new(output/'receipt.json',receipt)
    print(json.dumps({'passed':receipt['passed'],'label':args.label,'disposition':result['predicateDisposition'],'actualHttpExecution':meta['actualHttpExecution'],'nativeTargetDeadlocks':result['nativeTargetDeadlocks']}))
    return 0 if receipt['passed'] else 1

def main():
    p=argparse.ArgumentParser();p.add_argument('--execute-real-http',action='store_true');p.add_argument('--label',choices=COMMITS,required=True);p.add_argument('--upstream-root',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--project-root',type=Path,required=True);p.add_argument('--connection-file',type=Path,required=True);p.add_argument('--case-file',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    return run_with_diagnostics(p.parse_args())
if __name__=='__main__':raise SystemExit(main())