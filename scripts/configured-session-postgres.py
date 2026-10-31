"""Prepare or execute an explicit configured same-connection diagnostic attempt.

Planning is the default. Database execution requires --execute and credentials
from an explicitly named environment variable, never a saved connection file.
No database server or business table is created by this controller.
"""
from __future__ import annotations
import argparse, ctypes, hashlib, json, os, re, shutil, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'integrations/python'))
from moontxnwitness_capture.configured_sql import SQLCaptureConfig, ConfiguredSQLParser
from moontxnwitness_capture.configured_source import SourceInstallPolicy, identifier
from moontxnwitness_capture.configured_session import (augmented_source_config,
    install_and_capture_initial_reads, canonical, read_text, write_new)


def unique(pairs):
    value={}
    for key,item in pairs:
        if key in value:raise ValueError('Duplicate input key')
        value[key]=item
    return value


def structured(text):
    return json.loads(text,object_pairs_hook=unique,parse_constant=lambda _ : (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def available_memory():
    if os.name=='nt':
        class Memory(ctypes.Structure):
            _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong),('total',ctypes.c_ulonglong),('available',ctypes.c_ulonglong),('pageTotal',ctypes.c_ulonglong),('pageAvailable',ctypes.c_ulonglong),('virtualTotal',ctypes.c_ulonglong),('virtualAvailable',ctypes.c_ulonglong),('extended',ctypes.c_ulonglong)]
        memory=Memory();memory.length=ctypes.sizeof(memory)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):raise OSError('Cannot read physical memory guard')
        return memory.available
    info=Path('/proc/meminfo')
    if info.is_file():
        for line in info.read_text().splitlines():
            if line.startswith('MemAvailable:'):return int(line.split()[1])*1024
    return os.sysconf('SC_AVPHYS_PAGES')*os.sysconf('SC_PAGE_SIZE')


def reserve(path):
    if available_memory()<1024*1024*1024:
        raise RuntimeError('Execution needs at least 1GiB available physical memory')
    if shutil.disk_usage(path).free<1024*1024*1024:
        raise RuntimeError('Execution needs at least 1GiB free on the selected output drive')
    if os.name=='nt' and shutil.disk_usage('C:/').free<128*1024*1024:
        raise RuntimeError('Execution needs at least 128MiB free on C:')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',required=True);p.add_argument('--policy',required=True)
    p.add_argument('--queries',required=True);p.add_argument('--output',required=True)
    p.add_argument('--execute',action='store_true');p.add_argument('--dsn-env')
    p.add_argument('--dependency-root',help='Existing explicitly trusted SQLGlot 30.26.0 target; never installed or downloaded');p.add_argument('--owner-role');p.add_argument('--runtime');p.add_argument('--runtime-sha256');p.add_argument('--node',default='node')
    a=p.parse_args()
    if a.dependency_root:
        dependency=Path(a.dependency_root).resolve()
        if not dependency.is_dir():raise ValueError('Existing explicit optional dependency directory required')
        sys.path.insert(0,str(dependency))
    config=SQLCaptureConfig.from_json(read_text(a.config,262144))
    raw_policy=structured(read_text(a.policy,8192));allowed={'namespace','writers','maxInitialRows','maxLogBytes'}
    if type(raw_policy)is not dict or set(raw_policy)!=allowed or type(raw_policy['writers'])is not list:raise ValueError('Exact explicit source policy fields and writer array required')
    policy=SourceInstallPolicy(raw_policy['namespace'],tuple(raw_policy['writers']),raw_policy['maxInitialRows'],raw_policy['maxLogBytes'])
    rows=structured(read_text(a.queries,1048576))
    if type(rows)is not list or not 1<=len(rows)<=128 or any(type(r)is not dict or set(r)!={'sql','parameters'}for r in rows):raise ValueError('1..128 original SQL/parameter requests required')
    capture=augmented_source_config(config);parser=ConfiguredSQLParser(capture)
    queries=tuple((r['sql'],r['parameters'])for r in rows)
    for sql,params in queries:
        plan=parser.recognize(sql)
        if plan.operation!='select':raise ValueError('Explicit initial-read controller accepts supported SELECT only')
        plan.bind(params)
    plan={'format':'configured-session-execution-plan/v1','databaseExecutionRequested':a.execute,
          'configSha256':config.sha256,'tables':[{'schema':t.schema,'table':t.table,'columns':len(t.columns),'model':t.model}for t in config.tables],
          'queryCount':len(queries),'originalSQLRewritten':False,'sourceFactsProduced':False,'writerWindowVerified':False,
          'sourceAuthenticated':False,'serverInstanceIdentityAuthenticated':False,'isolationModelChecked':False,'isolationAnalysisReady':False,
          'remaining':['complete writer window','post-initial effective sources','authenticated observer/server','model-fact projection']}
    if not a.execute:
        print(canonical(plan));return 0
    if not a.dsn_env or not os.environ.get(a.dsn_env):raise ValueError('Explicit nonempty --dsn-env required; credentials are never written')
    if not a.runtime or not a.runtime_sha256:raise ValueError('Caller-pinned consolidated diagnostic runtime required')
    runtime_text=read_text(a.runtime,16*1024*1024)
    if not re.fullmatch('[0-9a-f]{64}',a.runtime_sha256) or hashlib.sha256(runtime_text.encode('utf-8')).hexdigest()!=a.runtime_sha256:
        raise ValueError('Caller-pinned runtime bytes differ before database execution')
    if re.search(r'(?m)^\s*import\b',runtime_text):raise ValueError('Self-contained compiled diagnostic bridge required')
    out=Path(a.output).resolve()
    if out.exists():raise ValueError('Each owned attempt requires a fresh output directory')
    out.parent.mkdir(parents=True,exist_ok=True);reserve(out.parent)
    import psycopg
    stage='connect';actual_queries=False
    try:
        with psycopg.connect(os.environ[a.dsn_env],autocommit=True)as connection:
            if a.owner_role:connection.execute('SET ROLE '+identifier(a.owner_role))
            stage='installation-and-original-initial-reads'
            bundle=install_and_capture_initial_reads(connection,out,config,policy,queries,opt_in=True)
            actual_queries=True
        stage='independent-diagnostic-replay';reserve(out)
        report=out/'diagnosis.json'
        completed=subprocess.run([a.node,str(ROOT/'scripts/diagnose-configured-session-v4.mjs'),
           '--runtime',str(Path(a.runtime).resolve()),'--runtime-sha256',a.runtime_sha256,
           '--input',str(bundle),'--output',str(report)],check=False,text=True,capture_output=True,
           timeout=120,env={key:value for key,value in os.environ.items()if key!=a.dsn_env},creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        write_new(out/'verification-stdout.txt',completed.stdout);write_new(out/'verification-stderr.txt',completed.stderr)
        receipt={**plan,'actualDatabaseExecution':True,'diagnosticProcessExit':completed.returncode,
          'runtimeSha256':a.runtime_sha256,'bundleSha256':hashlib.sha256(Path(bundle).read_bytes()).hexdigest(),
          'diagnosisSha256':hashlib.sha256(report.read_bytes()).hexdigest()if report.exists()else None,
          'sameEpochScope':'same caller-owned physical connection after confirmed installation COMMIT, no authentication/window assertion'}
        write_new(out/'execution-receipt.json',canonical(receipt)+'\n');print(canonical(receipt));return completed.returncode
    except BaseException as error:
        # Never store a DSN, exception message or credential-bearing command.
        # The installer preserves its separate commit/rollback receipt. An
        # interrupted attempt is not retried and cannot claim successful reads.
        failure={**plan,'actualDatabaseExecution':True if actual_queries else None,'databaseConnectionAttempted':True,
          'allRequestedInitialReadsCompleted':actual_queries,'completed':False,
          'failedStage':stage,'errorClass':type(error).__name__,'retryPerformed':False,
          'sourceInstallationOutcome':'inspect retained installation/receipt.json before any retry'}
        if out.is_dir() and not (out/'execution-failure.json').exists():
            try:write_new(out/'execution-failure.json',canonical(failure)+'\n')
            except OSError:pass
        print(canonical(failure),file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
