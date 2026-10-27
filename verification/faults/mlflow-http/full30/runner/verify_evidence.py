"""Offline integrity and predicate replay; never authenticates a server or database."""
from pathlib import Path
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from protocol import COMMITS,ROUTE,LOG_FILES,classify,digest,encoded,file_digest,read_log,request_body,workload,relative_file,read_json,artifact_bindings,fixed_behavior,strict_json

def verify(directory,manifest):
    directory=Path(directory)
    try:
        receipt=read_json(directory/'receipt.json');case=receipt['workload'];label=receipt['label']
        if receipt.get('schema')!=2 or receipt.get('format')!='moontxnwitness-mlflow-http-run/v2' or receipt.get('evidenceAlgorithm')!='original-http-evidence-2':raise ValueError('Unsupported original HTTP evidence revision')
        if receipt['commit']!=COMMITS[label] or manifest['commits'][label]!=COMMITS[label]:raise ValueError('Wrong upstream commit')
        if case!=workload(case['seed'],case['keys'],tuple(case['workers'])) or receipt['workloadSha256']!=digest(encoded(case)):raise ValueError('Altered original request subsequence')
        table=[{k:r[k] for k in ('path','bytes','sha256')} for r in manifest['sources'][label]['files']]
        expected={'commit':COMMITS[label],'files':len(table),'fileTableSha256':digest(encoded(table)),'businessSourceModified':False}
        if receipt['sourceBefore']!=expected or receipt['sourceAfter']!=expected:raise ValueError('Frozen source binding differs')
        if receipt['artifactBindings']!=artifact_bindings(directory):raise ValueError('Required original artifact closure differs')
        if set(receipt['logs'])!=set(LOG_FILES):raise ValueError('Required observation log binding missing')
        observations={}
        for name,filename in LOG_FILES.items():
            row=receipt['logs'][name];path=relative_file(directory,filename);maximum=2*1024*1024 if name=='calls' else 32*1024*1024
            if set(row)!={'sealed','records','bytes','sha256'} or row['sealed'] is not True or type(row['bytes']) is not int or not 0<row['bytes']<=maximum or path.stat().st_size!=row['bytes'] or file_digest(path)!=row['sha256']:raise ValueError('Altered/unsealed log')
            observations[name]=read_log(path,maximum)
            if type(row['records']) is not int or row['records']!=len(observations[name]):raise ValueError('Observation record count differs')
        http,sql,calls,schedule=(observations[name] for name in ('http','sql','calls','schedule'))
        route=read_json(directory/'native-route.json');rows=read_json(directory/'final-rows.json');final_http=read_json(directory/'final-native-http-run.json')
        if route['route']!=ROUTE or route['handlerModule']!='mlflow.server.handlers' or route['handlerSource']!='mlflow/server/handlers.py' or route['storeModule']!='mlflow.store.tracking.sqlalchemy_store' or route['storeClass']!='SqlAlchemyStore' or route['nativeApplication']!='mlflow.server:app' or route['actualTCPAddress']!='127.0.0.1' or type(route['port']) is not int or not 1<=route['port']<=65535 or route['upstreamASTExtractedOrPatched'] is not False:raise ValueError('Original native HTTP path or actual port not bound')
        if final_http['run']['info']['run_id']!=route['runId']:raise ValueError('Final native run identity differs')
        modules=receipt['runtimeModules'];seen=set();source_files={r['path']:r['sha256'] for r in table}
        for module in modules:
            if module['module'] in seen or not (module['module']=='mlflow' or module['module'].startswith('mlflow.')) or source_files.get(module['file'])!=module['sha256']:raise ValueError('Imported module differs from frozen source')
            module_path=module['module'].replace('.','/')
            candidates=[path for path in (module_path+'.py',module_path+'/__init__.py') if path in source_files]
            if len(candidates)!=1 or module['file']!=candidates[0]:raise ValueError('Native module name is not bound to its unique frozen import path')
            seen.add(module['module'])
        if not {'mlflow.server.handlers','mlflow.store.tracking.sqlalchemy_store'}.issubset(seen):raise ValueError('Native source modules not observed')
        for worker in case['workers']:
            requests=[r for r in http if r.get('kind')=='request' and r.get('worker')==worker and r.get('path')==ROUTE]
            if len(requests)!=1:raise ValueError('Request repeated or omitted')
            req=requests[0];raw=req['bodyUtf8'].encode()
            if req['method']!='POST' or digest(raw)!=req['bodySha256'] or raw!=encoded(request_body(case,worker,route['runId'])) or req['clientRetries']!=0:raise ValueError('Request does not reproduce frozen workload')
            for module,function in [('mlflow.server.handlers','_log_batch'),('mlflow.store.tracking.sqlalchemy_store','log_batch'),('mlflow.store.tracking.sqlalchemy_store','_update_latest_metrics_if_necessary')]:
                source=module.replace('.','/')+'.py'
                if not any(r.get('worker')==worker and r.get('module')==module and r.get('function')==function and r.get('source')==source for r in calls):raise ValueError('Native call chain not observed')
        for row in http:
            if row.get('kind')=='response' and digest(row['bodyUtf8'].encode())!=row['bodySha256']:raise ValueError('Response bytes differ')
        final_path='/api/2.0/mlflow/runs/get?run_id='+route['runId']
        final_requests=[r for r in http if r.get('kind')=='request' and r.get('path')==final_path]
        if len(final_requests)!=1 or final_requests[0].get('method')!='GET' or final_requests[0].get('worker') is not None or final_requests[0].get('bodyUtf8')!='' or final_requests[0].get('bodySha256')!=digest(b'') or final_requests[0].get('clientRetries')!=0:raise ValueError('Final native GET request is missing, repeated or changed')
        final_responses=[r for r in http if r.get('kind')=='response' and r.get('path')==final_path]
        if len(final_responses)!=1 or final_responses[0].get('worker') is not None or final_responses[0]['status']!=200 or strict_json(final_responses[0]['bodyUtf8'])!=final_http:raise ValueError('Final native HTTP delivery is missing, repeated or differs from retained native result')
        if not any(row.get('kind')=='release' for row in schedule) and receipt['metadata']['controllerComplete']:raise ValueError('Missing scheduler decision')
        result=classify(case,receipt['metadata'],http,sql,rows)
        fixed=bool(result['executionComplete'] and fixed_behavior(case,http,rows,final_http)) if label=='fixed' else None
        passed=result['faultPredicate'] if label=='before' else fixed
        if result!=receipt['result'] or receipt['passed'] is not passed or receipt['fixedBehaviorChecked'] is not fixed or receipt['isolationViolationClaim'] is not False or receipt['G2Claim'] is not False:raise ValueError('Fault result, fixed behavior or unsupported model claim changed')
        if receipt['metadata']['caseError'] is not None and result['executionComplete']:raise ValueError('Failed execution cannot be complete')
        if receipt['actualHttpExecution'] is not True or receipt['actualDatabaseExecution'] is not True or receipt['nativeCallChainObserved'] is not True or receipt['sourceCollectionDiagnosticOnly'] is not True or receipt['serverOrDatabaseAuthenticityCertified'] is not False or receipt['upstreamLockOrderOrRetrySemanticsRewritten'] is not False:raise ValueError('Actual execution scope differs')
        return {'valid':True,'label':label,'commit':COMMITS[label],'workloadSha256':receipt['workloadSha256'],'result':result,'passed':passed,'fixedBehaviorChecked':fixed,'receiptSha256':file_digest(directory/'receipt.json'),'scope':'Integrity and predicate replay of retained original observations; does not authenticate a server or collector'}
    except Exception as error:return {'valid':False,'reason':type(error).__name__+': '+str(error),'scope':'No DB/HTTP was executed by this verifier'}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path);parser.add_argument('--manifest',type=Path,default=Path(__file__).with_name('upstream-manifest.json'));args=parser.parse_args();result=verify(args.directory,read_json(args.manifest,16*1024*1024));print(json.dumps(result));return 0 if result['valid'] else 2
if __name__=='__main__':raise SystemExit(main())
