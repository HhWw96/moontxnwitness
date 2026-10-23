"""Controlled PostgreSQL full diagnostic capture cost A/B/C (never B/A as C/A).

Creates fresh owned fixture schemas and retains data/evidence. No execution
occurs on import. Formal protocol requires an exclusive, otherwise idle host.
"""
from __future__ import annotations
import argparse
import array
import dataclasses
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import statistics
import struct
import subprocess
import sys
import shutil
import threading
import time
import traceback
import uuid

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'integrations/python'))
from moontxnwitness_capture._provenance import install,qualified,identifier
from moontxnwitness_capture.instrumentation import Instrumentation
from moontxnwitness_capture.source_sink import GroupedSourceSink

WORKLOADS={
 'serial':{'keys':4096,'connections':1,'crud':False,'hot':False},
 'parallel':{'keys':4096,'connections':4,'crud':False,'hot':False},
 'hot':{'keys':32,'connections':8,'crud':False,'hot':True},
 'crud':{'keys':4096,'connections':4,'crud':True,'hot':False},
}
ORDERS=(('A','B','C'),('B','C','A'),('C','A','B'))
GENERATOR='python-random-point-capture-cost/v1'
STORAGE_RESERVE_BYTES=512*1024*1024


def runtime_sources():
    package=ROOT/'integrations/python/moontxnwitness_capture'
    return [Path(__file__).resolve(),Path(__file__).with_name('cell_archive.py'),
            *sorted(path for path in package.glob('*.py') if not path.name.startswith('test_'))]


def operation(randomizer,spec):
    if spec['hot']:
        key=randomizer.randrange(4) if randomizer.random()<.9 else 4+randomizer.randrange(spec['keys']-4)
    else:
        key=randomizer.randrange(spec['keys'])
    action=randomizer.randrange(4) if spec['crud'] else 0
    return {'key':'key-'+str(key),'action':action,'missing':'missing-'+str(randomizer.randrange(32))}


def nearest_rank(values,fraction):
    if not values:return None
    return sorted(values)[max(0,int(__import__('math').ceil(len(values)*fraction))-1)]


def peak_rss():
    if os.name=='nt':
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD),
                      ('PeakWorkingSetSize',ctypes.c_size_t),('WorkingSetSize',ctypes.c_size_t),
                      ('QuotaPeakPagedPoolUsage',ctypes.c_size_t),('QuotaPagedPoolUsage',ctypes.c_size_t),
                      ('QuotaPeakNonPagedPoolUsage',ctypes.c_size_t),('QuotaNonPagedPoolUsage',ctypes.c_size_t),
                      ('PagefileUsage',ctypes.c_size_t),('PeakPagefileUsage',ctypes.c_size_t)]
        counters=Counters();counters.cb=ctypes.sizeof(counters)
        get_process=ctypes.windll.kernel32.GetCurrentProcess
        get_process.restype=wintypes.HANDLE
        ok=ctypes.windll.psapi.GetProcessMemoryInfo(get_process(),ctypes.byref(counters),counters.cb)
        return int(counters.PeakWorkingSetSize) if ok else None
    import resource
    value=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform=='darwin' else value*1024)


def connect_factory(psycopg):
    defaults={'connect_timeout':5,'options':'-c statement_timeout=15000 -c lock_timeout=10000'}
    if os.environ.get('MTW_PG_CONNECTION_FILE'):
        kwargs=json.loads(Path(os.environ['MTW_PG_CONNECTION_FILE']).read_text(encoding='utf8'))
        return lambda **extra:psycopg.connect(**(defaults|kwargs|extra))
    if os.environ.get('MTW_PG_DSN'):
        return lambda **extra:psycopg.connect(os.environ['MTW_PG_DSN'],**(defaults|extra))
    return None


def write_json(path,value):
    with Path(path).open('x',encoding='utf8',newline='\n') as file:
        json.dump(value,file,indent=2,ensure_ascii=False);file.write('\n')


def _begin_warmup(connections_ready,start,shared,seconds,timeout):
    """Wait for native connections/wrappers, then issue the full warmup window."""
    connections_ready.wait(timeout=timeout)
    began=time.monotonic()
    shared['warmDeadline']=began+seconds
    start.set()
    return began


def run_cell(config,output,connect):
    spec=WORKLOADS[config['workload']];mode=config['mode']
    schema='mtw_provenance_cost_'+uuid.uuid4().hex[:16]
    table=qualified(schema,'items')
    capture=sources=provenance=None
    connections_ready=threading.Barrier(spec['connections']+1)
    warm_ready=threading.Barrier(spec['connections']+1)
    start=threading.Event();measure=threading.Event();stop=threading.Event()
    lock=threading.Lock();active=[];results=[]
    shared={'warmDeadline':0,'measureDeadline':0,'measureStart':0}
    monitor_stop=threading.Event();monitor_thread=None
    blocking={'samples':0,'lockWaitSamples':0,'minimumFreeBytes':shutil.disk_usage(output).free}
    receipt={'schema':1,'status':'started','actualDatabaseExecution':False,'fullCaptureComparison':True,
             'captureScope':'raw automatic diagnostics plus controlled provenance; no complete model/ORM proof',
             'configuration':config,'fixtureSchema':schema,'workloadSpec':spec,'generator':GENERATOR,
             'formalProtocolCompleted':False,'allAttemptsRetained':True}
    setup=None;failed=[]
    try:
        setup=connect(autocommit=True)
        receipt.update(actualDatabaseExecution=True,server=setup.execute('SELECT version()').fetchone()[0])
        if not 180000<=setup.info.server_version<190000:raise ValueError('PostgreSQL 18 is required')
        receipt['databaseSettings']=dict(setup.execute("SELECT name,setting FROM pg_settings WHERE name IN ('synchronous_commit','fsync','full_page_writes','shared_buffers','max_connections')").fetchall())
        setup.execute('CREATE SCHEMA '+identifier(schema))
        setup.execute('CREATE TABLE '+table+'(id text PRIMARY KEY,value integer NOT NULL)')
        setup.cursor().executemany('INSERT INTO '+table+' VALUES(%s,%s)',[('key-'+str(i),0) for i in range(spec['keys'])])
        if mode!='A':
            provenance=install(setup,schema=schema,table='items',mode=config['profile'],
                               missing_keys=tuple('missing-'+str(i) for i in range(32)))
        if mode=='C':
            capture=Instrumentation(output/'capture',max_lifecycle_bytes=512*1024*1024,
                                    max_lifecycle_records=2000000,
                                    journal_options={'max_total_bytes':1024**3})
            sources=GroupedSourceSink(output/'sources.jsonl',max_total_bytes=1024**3,max_records=1000000)
            for key,value in provenance.initial.items():
                result=sources.append({'kind':'source-batch','phase':'initial','observation':value.as_dict()})
                if not result.accepted:raise RuntimeError('Initial source budget exhausted')

        def one(connection,randomizer,worker,ordinal,measured):
            op=operation(randomizer,spec);key=op['key']
            began=time.perf_counter_ns();success=False;state=None;rowcount=0
            try:
                if provenance is None:
                    connection.execute('SELECT value FROM '+table+' WHERE id=%s',(key,)).fetchone()
                    absent=connection.execute('SELECT value FROM '+table+' WHERE id=%s',(op['missing'],)).fetchone()
                    if absent is not None:raise AssertionError('Declared missing key unexpectedly exists')
                else:
                    value=provenance.observe(connection,key);absent=provenance.observe(connection,op['missing'])
                    if absent.exists:raise AssertionError('Declared missing key unexpectedly exists')
                    if sources is not None:
                        for item in [value,absent]:
                            result=sources.append({'kind':'source-batch','phase':'read','worker':worker,'attempt':ordinal,
                                                   'tx':connection._tx,'observation':item.as_dict()})
                            if not result.accepted:raise RuntimeError('Source record budget exhausted')
                if not spec['crud']:
                    cursor=connection.execute('UPDATE '+table+' SET value=value+1 WHERE id=%s RETURNING value',(key,))
                    if cursor.fetchone() is None:raise AssertionError('Fixed key disappeared')
                    rowcount=1
                elif op['action']==0:
                    cursor=connection.execute('UPDATE '+table+' SET value=1 WHERE id=%s',(key,));rowcount=cursor.rowcount
                elif op['action']==1:
                    cursor=connection.execute('DELETE FROM '+table+' WHERE id=%s',(key,));rowcount=cursor.rowcount
                elif op['action']==2:
                    cursor=connection.execute('INSERT INTO '+table+'(id,value) VALUES(%s,0)',(key,));rowcount=cursor.rowcount
                connection.commit();success=True
            except Exception as error:
                state=getattr(error,'sqlstate',None)
                try:connection.rollback()
                except Exception:pass
                # Retain registered contention attempts for the full timed
                # protocol. Any such SQL failure still disqualifies this cell
                # from strict performance evidence; it is never a hidden retry.
                # Unexpected collector/runtime failures also stop the protocol.
                if state not in ('23505','40001','40P01','55P03'):
                    with lock:failed.append({'worker':worker,'errorClass':type(error).__name__,'sqlstate':state})
                    stop.set()
            return op,success,state,time.perf_counter_ns()-began,rowcount

        def worker(number):
            raw=connection=None;attempts=commits=errors=0;updates={};warm_updates={}
            warm_attempts=warm_commits=warm_errors=0;warm_sqlstates={}
            thread_result={'worker':number,'attempts':0,'commits':0,'failures':0}
            try:
                raw=connect();connection=capture.wrap(raw) if capture is not None else raw
                with lock:active.append(raw)
                connections_ready.wait(timeout=config['drainSeconds'])
                start.wait()
                rng=random.Random(config['seed']+1000000+number)
                ordinal=0
                while time.monotonic()<shared['warmDeadline'] and not stop.is_set():
                    op,ok,state,elapsed,count=one(connection,rng,number,ordinal,False);ordinal+=1
                    warm_attempts+=1;warm_commits+=int(ok);warm_errors+=int(not ok)
                    if not ok:warm_sqlstates[state or '<unavailable>']=warm_sqlstates.get(state or '<unavailable>',0)+1
                    if ok and not spec['crud']:warm_updates[op['key']]=warm_updates.get(op['key'],0)+1
                warm_ready.wait(timeout=config['drainSeconds'])
                measure.wait()
                rng=random.Random(config['seed']+number)
                with (output/('attempts-'+str(number)+'.jsonl')).open('xb') as log:
                    while time.monotonic()<shared['measureDeadline'] and not stop.is_set():
                        if attempts>=config['maxAttemptsPerWorker']:
                            failed.append({'worker':number,'errorClass':'AttemptBudgetExhausted','sqlstate':None});stop.set();break
                        op,ok,state,elapsed,count=one(connection,rng,number,attempts,True)
                        line={'ordinal':attempts,'committed':ok,'sqlstate':state,'latencyNs':elapsed,
                              'key':op['key'],'action':op['action'],'rowcount':count}
                        log.write((json.dumps(line,separators=(',',':'))+'\n').encode())
                        attempts+=1;commits+=int(ok);errors+=int(not ok)
                        if ok and not spec['crud']:updates[op['key']]=updates.get(op['key'],0)+1
                    log.flush();os.fsync(log.fileno())
                thread_result.update(attempts=attempts,commits=commits,failures=errors,
                                     committedIncrements=updates,warmupIncrements=warm_updates,
                                     warmupAttempts=warm_attempts,warmupCommits=warm_commits,
                                     warmupFailures=warm_errors,warmupSqlstateCounts=warm_sqlstates)
            except BaseException as error:
                with lock:failed.append({'worker':number,'errorClass':type(error).__name__,'sqlstate':getattr(error,'sqlstate',None)})
                stop.set()
                try:connections_ready.abort()
                except Exception:pass
                try:warm_ready.abort()
                except Exception:pass
            finally:
                thread_result.update(warmupAttempts=warm_attempts,warmupCommits=warm_commits,
                                     warmupFailures=warm_errors,warmupSqlstateCounts=warm_sqlstates)
                closing_connection=connection if connection is not None else raw
                if closing_connection is not None:
                    try:closing_connection.close()
                    except Exception:pass
                with lock:results.append(thread_result)


        def monitor_locks():
            connection=None
            try:
                connection=connect(autocommit=True)
                # Capacity protection also runs during warmup. It never archives
                # or deletes a live log, and every A/B/C cell pays this sampler.
                while not measure.wait(.1) and not monitor_stop.is_set():
                    free=shutil.disk_usage(output).free
                    blocking['minimumFreeBytes']=min(free,blocking['minimumFreeBytes'])
                    if free<config.get('storageReserveBytes',STORAGE_RESERVE_BYTES):
                        with lock:failed.append({'errorClass':'StorageReserveReached','sqlstate':None})
                        stop.set();return
                pids=[raw.info.backend_pid for raw in active]
                with (output/'blocking-samples.jsonl').open('xb') as log:
                    while not monitor_stop.is_set():
                        free=shutil.disk_usage(output).free
                        blocking['minimumFreeBytes']=min(free,blocking['minimumFreeBytes'])
                        if free<config.get('storageReserveBytes',STORAGE_RESERVE_BYTES):
                            with lock:failed.append({'errorClass':'StorageReserveReached','sqlstate':None})
                            stop.set();break
                        rows=connection.execute('SELECT pid,wait_event_type,wait_event,pg_blocking_pids(pid) FROM pg_stat_activity WHERE pid=ANY(%s)',(pids,)).fetchall()
                        blocking['samples']+=1
                        blocking['lockWaitSamples']+=sum(row[1]=='Lock' for row in rows)
                        item={'monotonicNs':str(time.monotonic_ns()),'rows':rows,'volumeFreeBytes':free}
                        log.write((json.dumps(item,separators=(',',':'))+'\n').encode())
                        monitor_stop.wait(.1)
                    log.flush();os.fsync(log.fileno())
            except BaseException as error:
                with lock:failed.append({'errorClass':'BlockingMonitor'+type(error).__name__,'sqlstate':getattr(error,'sqlstate',None)})
            finally:
                if connection is not None:connection.close()

        monitor_thread=threading.Thread(target=monitor_locks,daemon=True);monitor_thread.start()
        threads=[threading.Thread(target=worker,args=(n,),daemon=True) for n in range(spec['connections'])]
        for thread in threads:thread.start()
        receipt['warmupStartMonotonicSeconds']=_begin_warmup(connections_ready,start,shared,config['warmupSeconds'],config['drainSeconds'])
        receipt['warmupStartedAfterConnectionsReady']=True
        warm_ready.wait(timeout=config['warmupSeconds']+config['drainSeconds'])
        if capture is not None: capture.flush(); sources.flush()
        wal_before=setup.execute('SELECT pg_current_wal_insert_lsn()::text').fetchone()[0]
        stats_before=setup.execute('SELECT deadlocks,xact_commit,xact_rollback FROM pg_stat_database WHERE datname=current_database()').fetchone()
        cpu_before=time.process_time_ns();began=time.perf_counter_ns()
        shared['measureStart']=began
        shared['measureDeadline']=time.monotonic()+config['durationSeconds'];measure.set()
        deadline=time.monotonic()+config['durationSeconds']+config['drainSeconds']
        for thread in threads:thread.join(max(0,deadline-time.monotonic()))
        if any(thread.is_alive() for thread in threads):
            stop.set()
            for connection in active:
                try:connection.cancel()
                except Exception:pass
            for thread in threads:thread.join(2)
            raise TimeoutError('Workers exceeded the bounded drain time')
        workers_done=time.perf_counter_ns()
        monitor_stop.set();monitor_thread.join(5)
        if monitor_thread.is_alive():failed.append({'errorClass':'BlockingMonitorTimeout','sqlstate':None})
        if mode=='C':
            # Stream final actual committed audit rows, never load a full ledger.
            query='SELECT token::text,key,action,present,predecessor::text,old_value,new_value FROM '+provenance.names.object('audit')
            cursor=setup.cursor();cursor.execute(query)
            while True:
                rows=cursor.fetchmany(128)
                if not rows:break
                result=sources.append({'kind':'source-batch','phase':'actual-final-audit','rows':rows})
                if not result.accepted:raise RuntimeError('Final source audit budget exhausted')
            cursor.close()
            receipt['sourceStorage']=sources.close()
            capture_status=capture.close()
            if not capture_status.valid:
                failed.append({'errorClass':'CaptureJournalInvalid','sqlstate':None})
            receipt['captureGaps']=list(capture.gaps)
            allowed={'initialization_unproven','diagnostic_instrumentation_only','statement_failed'}
            if any(gap['code'] not in allowed for gap in capture.gaps):
                failed.append({'errorClass':'CaptureCoverageOrStorageGap','sqlstate':None})
            if not receipt['sourceStorage']['storageSealed']:
                failed.append({'errorClass':'SourceStorageIncomplete','sqlstate':None})
            raw_status=json.loads((capture.output/'instrumentation.json').read_text(encoding='utf8'))
            if not raw_status['lifecycle']['sealed']:
                failed.append({'errorClass':'LifecycleStorageIncomplete','sqlstate':None})
        persisted=time.perf_counter_ns();cpu_after=time.process_time_ns()
        rss=peak_rss()
        wal_after=setup.execute('SELECT pg_current_wal_insert_lsn()::text').fetchone()[0]
        wal_delta=int(setup.execute('SELECT pg_wal_lsn_diff(%s::pg_lsn,%s::pg_lsn)',(wal_after,wal_before)).fetchone()[0])
        stats_after=setup.execute('SELECT deadlocks,xact_commit,xact_rollback FROM pg_stat_database WHERE datname=current_database()').fetchone()
        receipt['databaseCounterDelta']={'deadlocks':stats_after[0]-stats_before[0],'xactCommit':stats_after[1]-stats_before[1],'xactRollback':stats_after[2]-stats_before[2],'scope':'database-global asynchronous counters; not inferred exact target transaction counts'}
        receipt['blockingSamples']=blocking
        final=dict(setup.execute('SELECT id,value FROM '+table+' ORDER BY id').fetchall())
        if not spec['crud']:
            expected={'key-'+str(i):0 for i in range(spec['keys'])}
            for result in results:
                for counts in [result.get('warmupIncrements',{}),result.get('committedIncrements',{})]:
                    for key,count in counts.items():expected[key]+=count
            if final!=expected:failed.append({'errorClass':'IndependentFinalValueMismatch','sqlstate':None})
        elif any(not key.startswith('key-') or not 0<=int(key[4:])<spec['keys'] or value not in (0,1) for key,value in final.items()):
            failed.append({'errorClass':'CrudFinalInvariantMismatch','sqlstate':None})
        latencies=[];committed_latencies=[];attempt_count=commits=0;sqlstates={};warm_sqlstates={}
        for path in sorted(output.glob('attempts-*.jsonl')):
            with path.open('r',encoding='utf8') as file:
                for line in file:
                    item=json.loads(line);attempt_count+=1;latencies.append(item['latencyNs'])
                    if item['committed']:commits+=1;committed_latencies.append(item['latencyNs'])
                    else:
                        state=item['sqlstate'] or '<unavailable>'
                        sqlstates[state]=sqlstates.get(state,0)+1
        for worker_result in results:
            for state,count in worker_result.get('warmupSqlstateCounts',{}).items():
                warm_sqlstates[state]=warm_sqlstates.get(state,0)+count
        if attempt_count!=sum(x['attempts'] for x in results):
            failed.append({'errorClass':'AttemptLogCountMismatch','sqlstate':None})
        wall=persisted-began
        receipt.update(status='failed' if failed else 'smoke-passed' if config['quick'] else 'passed',
                       formalProtocolCompleted=not config['quick'] and not failed,
                       attempts=attempt_count,commits=commits,failures=attempt_count-commits,
                       sqlstateCounts=sqlstates,warmupAttempts=sum(x.get('warmupAttempts',0) for x in results),
                       warmupCommits=sum(x.get('warmupCommits',0) for x in results),
                       warmupFailures=sum(x.get('warmupFailures',0) for x in results),warmupSqlstateCounts=warm_sqlstates,
                       endToEndWallNs=wall,workerDrainNs=max(0,workers_done-began-int(config['durationSeconds']*1e9)),
                       persistenceTailNs=persisted-workers_done,endToEndCommittedTps=commits*1e9/wall,
                       allAttemptP50Ns=statistics.median(latencies) if latencies else None,
                       allAttemptP95Ns=nearest_rank(latencies,.95),
                       committedP95Ns=nearest_rank(committed_latencies,.95),cpuProcessNs=cpu_after-cpu_before,
                       processPeakRssBytes=rss,walDeltaBytes=wal_delta,
                       finalBusinessSha256=hashlib.sha256(json.dumps(final,sort_keys=True).encode()).hexdigest(),
                       protocolFailures=failed,workers=results,
                       captureBudgetExhausted=any(x.get('errorClass') in ('RuntimeError','CaptureCoverageOrStorageGap','SourceStorageIncomplete') for x in failed),
                       scope='One child process per cell; throughput includes drain and durable capture tail; SQLSTATE failures all retained',
                       sourceSemanticsCertified=False,serverCpuMeasured=False,
                       locks='Actual SQL errors and server lock/deadlock counters; no invented lock-wait duration')
        receipt['eligibilityReasons']=target_eligibility_reasons(receipt)
        receipt['eligibleForTargets']=not receipt['eligibilityReasons']
        return receipt
    except BaseException as error:
        receipt.update(status='failed',formalProtocolCompleted=False,errorClass=type(error).__name__,
                       protocolFailures=list(failed),
                       sqlstate=getattr(error,'sqlstate',None),frames=[{'file':Path(f.filename).name,'line':f.lineno} for f in traceback.extract_tb(error.__traceback__)])
        return receipt
    finally:
        stop.set();start.set();measure.set();monitor_stop.set()
        if monitor_thread is not None:monitor_thread.join(2)
        try:connections_ready.abort()
        except Exception:pass
        try:warm_ready.abort()
        except Exception:pass
        if capture is not None:
            try:capture.close()
            except Exception:pass
        if sources is not None:
            try:sources.close()
            except Exception:pass
        if setup is not None: setup.close()


def plan(args):
    warmup=.1 if args.quick else 15
    duration=.3 if args.quick else 60
    drain=5 if args.quick else 30
    names=list(WORKLOADS) if args.workload=='all' else [args.workload]
    cells=[]
    for name in names:
        for batch,order in enumerate(ORDERS):
            for mode in order:
                cells.append({'workload':name,'batch':batch,'mode':mode,'profile':args.profile,
                              'seed':args.seed+batch*10000,'warmupSeconds':warmup,
                              'durationSeconds':duration,'drainSeconds':drain,
                              'maxAttemptsPerWorker':100000,'storageReserveBytes':STORAGE_RESERVE_BYTES,'quick':args.quick})
    return {'schema':1,'generator':GENERATOR,'profile':args.profile,'seed':args.seed,
            'orders':[list(x) for x in ORDERS],'workloads':WORKLOADS,'cells':cells,
            'performanceTargets':{'fullCaptureThroughputCOverAAtLeast':.90,'fullCaptureP95COverAAtMost':1.15},
            'retentionPolicy':'post-child verified archive then release only own new cell files' if getattr(args,'archive_cells',False) else 'retain all raw cell files',
            'maximumCellsThisInvocation':getattr(args,'max_cells',None),
            'throughputDefinition':'commits/(issue window + transaction drain + durable source/capture tail)',
            'formalPerformanceMeasurement':not args.quick,'sourceSemanticsCertified':False}


def target_eligibility_reasons(cell):
    """Strict qualification is separate from successfully completing timing."""
    reasons=[]
    if not cell.get('formalProtocolCompleted'):reasons.append('formal_protocol_incomplete')
    if cell.get('captureBudgetExhausted'):reasons.append('capture_budget_exhausted')
    if cell.get('protocolFailures'):reasons.append('protocol_failures')
    failures=cell.get('failures')
    if type(failures) is not int or failures<0:reasons.append('failure_count_unavailable_or_invalid')
    elif failures:reasons.append('failed_measured_attempts')
    warm=cell.get('warmupFailures',0)
    if type(warm) is not int or warm<0:reasons.append('warmup_failure_count_invalid')
    elif warm:reasons.append('failed_warmup_attempts')
    for field in ('sqlstateCounts','warmupSqlstateCounts'):
        counts=cell.get(field,{})
        if type(counts) is not dict or any(type(v) is not int or v<0 for v in counts.values()):
            reasons.append(field+'_invalid')
        elif any(counts.values()):reasons.append(field+'_nonzero')
    for field in ('endToEndCommittedTps','allAttemptP95Ns'):
        value=cell.get(field)
        if not _finite_nonnegative(value) or value<=0:
            reasons.append(field+'_unavailable_or_nonpositive')
    return reasons


def _finite_nonnegative(value):
    if type(value) not in (int,float):return False
    try:return math.isfinite(value) and value>=0
    except (OverflowError,ValueError):return False


def _metric_ratio(value,baseline):
    if not _finite_nonnegative(value) or not _finite_nonnegative(baseline) or baseline==0:return None
    result=value/baseline
    return result if _finite_nonnegative(result) else None


def _geometric_metric(values):
    if not all(_finite_nonnegative(value) for value in values):return None
    if any(value==0 for value in values):return 0.0
    try:return math.exp(sum(math.log(value) for value in values)/len(values))
    except OverflowError:return None


def compare(cells):
    import math
    by={(x['configuration']['workload'],x['configuration']['batch'],x['configuration']['mode']):x for x in cells}
    output={}
    for name in sorted({key[0] for key in by}):
        pairs=[]
        for batch in range(3):
            values=[by.get((name,batch,mode)) for mode in ['A','B','C']]
            if any(v is None or v['status'] not in ('passed','smoke-passed') or v.get('captureBudgetExhausted') for v in values):
                output[name]={'status':'incomplete','eligibleForTargets':False};break
            a,b,c=values
            pairs.append({'batch':batch,'sourceThroughputBOverA':_metric_ratio(b.get('endToEndCommittedTps'),a.get('endToEndCommittedTps')),
                          'fullCaptureThroughputCOverA':_metric_ratio(c.get('endToEndCommittedTps'),a.get('endToEndCommittedTps')),
                          'fullCaptureP95COverA':_metric_ratio(c.get('allAttemptP95Ns'),a.get('allAttemptP95Ns'))})
        else:
            throughput=_geometric_metric([x['fullCaptureThroughputCOverA'] for x in pairs])
            p95=_geometric_metric([x['fullCaptureP95COverA'] for x in pairs])
            matching=[x for x in cells if x['configuration']['workload']==name]
            qualification=[{'batch':x['configuration']['batch'],'mode':x['configuration']['mode'],
                            'reasons':target_eligibility_reasons(x)} for x in matching]
            eligible=not any(x['reasons'] for x in qualification) and throughput is not None and p95 is not None
            output[name]={'status':'complete','pairedBatches':pairs,
                          'fullCaptureThroughputCOverA':throughput,'fullCaptureP95COverA':p95,
                          'cellQualification':qualification,
                          'eligibleForTargets':eligible,'performanceTargetsPassed':eligible and throughput>=.90 and p95<=1.15}
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    parser.add_argument('--profile',choices=['column','sidecar'],default='column')
    parser.add_argument('--workload',choices=['all',*WORKLOADS],default='all')
    parser.add_argument('--seed',type=int,default=20261023)
    parser.add_argument('--quick',action='store_true')
    parser.add_argument('--plan-only',action='store_true')
    parser.add_argument('--exclusive-host',action='store_true')
    parser.add_argument('--exclusive-cluster',action='store_true')
    parser.add_argument('--archive-cells',action='store_true',help='After each child exits, SHA-verify a lossless zip before releasing only its new cell raw files')
    parser.add_argument('--max-cells',type=int,help='Run only a prefix of the full preregistered plan; summary remains partial and ineligible')
    parser.add_argument('--worker-config')
    args=parser.parse_args()
    if args.max_cells is not None and not 1<=args.max_cells<=36:parser.error('--max-cells must be between 1 and 36')
    output=Path(args.output).resolve();output.mkdir(parents=True,exist_ok=False)
    if args.worker_config:
        config=json.loads(Path(args.worker_config).read_text(encoding='utf8'))
        try:import psycopg
        except ImportError:
            write_json(output/'receipt.json',{'status':'not-executed','actualDatabaseExecution':False,'reason':'optional psycopg is missing'});return 3
        connect=connect_factory(psycopg)
        if connect is None:
            write_json(output/'receipt.json',{'status':'not-executed','actualDatabaseExecution':False,'reason':'no owned database configured'});return 3
        source_files=runtime_sources()
        before={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
        result=run_cell(config,output,connect)
        after={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
        result['sourceBindings']=before;result['sourceUnchangedAfterCell']=before==after
        if before!=after:result['status']='failed';result['formalProtocolCompleted']=False
        result.update(python=platform.python_version(),platform=platform.platform(),driver=psycopg.__version__)
        write_json(output/'receipt.json',result);return 0 if result['status'] in ('passed','smoke-passed') else 1
    frozen=plan(args);write_json(output/'plan.json',frozen)
    if args.plan_only:
        write_json(output/'receipt.json',{'status':'not-executed','actualDatabaseExecution':False,'reason':'plan-only','cells':len(frozen['cells'])});return 0
    if not args.quick and not (args.exclusive_host and args.exclusive_cluster):
        write_json(output/'receipt.json',{'status':'not-executed','actualDatabaseExecution':False,'reason':'formal run requires explicit exclusive host and cluster assertions'});return 3
    results=[];archives=[];complete=True;stop_reason=None
    for i,config in enumerate(frozen['cells']):
        if args.max_cells is not None and i>=args.max_cells:
            complete=False;stop_reason='explicit partial preregistered prefix';break
        if shutil.disk_usage(output).free<STORAGE_RESERVE_BYTES:
            complete=False;stop_reason='storage reserve reached before next cell';break
        config_path=output/('cell-'+str(i)+'.config.json');write_json(config_path,config)
        command=[sys.executable,'-B',str(Path(__file__).resolve()),'--worker-config',str(config_path),'--output',str(output/('cell-'+str(i)))]
        with (output/('cell-'+str(i)+'.log')).open('xb') as log:
            try:
                child=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=120 if args.quick else 240)
            except subprocess.TimeoutExpired:
                complete=False
                write_json(output/('cell-'+str(i)+'-timeout.json'),{'status':'failed','formalProtocolCompleted':False,'reason':'bounded child deadline exceeded'})
                break
        receipt=output/('cell-'+str(i))/'receipt.json'
        if not receipt.is_file():complete=False;break
        value=json.loads(receipt.read_text(encoding='utf8'));results.append(value)
        if args.archive_cells:
            try:
                from cell_archive import archive_cell,release_cell
                cell=receipt.parent
                original_bytes=sum(p.stat().st_size for p in cell.rglob('*') if p.is_file())
                free=shutil.disk_usage(output).free
                if free<original_bytes+STORAGE_RESERVE_BYTES+16*1024*1024:
                    raise ValueError('No space for conservative full zip copy plus reserve; original raw cell retained')
                pointer=archive_cell(output,cell)
                archives.append(release_cell(output,cell,pointer))
            except Exception as error:
                complete=False;stop_reason='post-measurement retention failed: '+type(error).__name__
                write_json(output/('cell-'+str(i)+'-archive-failure.json'),{'status':'failed','reason':str(error),'originalRawRetainedUnlessExplicitPointerSaysReleased':True,'measurementHasEnded':True})
                break
        if child.returncode:complete=False;break
    comparison=compare(results) if results and all('configuration' in x for x in results) else {}
    summary={'schema':1,'status':'smoke-passed' if args.quick and complete else 'passed' if complete else 'partial' if stop_reason=='explicit partial preregistered prefix' else 'failed',
             'actualDatabaseExecution':any(x.get('actualDatabaseExecution') for x in results),
             'formalPerformanceMeasurement':not args.quick,'formalProtocolCompleted':not args.quick and complete,
             'completeCells':len(results),'plannedCells':len(frozen['cells']),
             'comparison':comparison,'stopReason':stop_reason,'cellArchives':archives,
             'performanceTargetsPassed':bool(complete and comparison and all(x.get('performanceTargetsPassed',False) for x in comparison.values())),
             'fullCaptureComparison':True,'onlySourceCostBOverA':False,'allFirstFailuresRetained':True,
             'measurementScope':'Current automatic diagnostic capture plus controlled provenance, not complete arbitrary SQL/ORM model coverage'}
    write_json(output/'receipt.json',summary)
    return 0 if complete else 2 if summary['status']=='partial' else 1


if __name__=='__main__':raise SystemExit(main())
