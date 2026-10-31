"""Offline configured installation plan. No connection, DDL execution or facts."""
from pathlib import Path
import json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/python'))
from moontxnwitness_capture.configured_sql import ColumnConfig,TableConfig,SQLCaptureConfig
from moontxnwitness_capture.configured_source import SourceInstallPolicy,installation_ddl

def c(name,kind):return ColumnConfig(name,kind,comparison='postgres-c-utf8-v1'if kind=='text'else None)
config=SQLCaptureConfig((
 TableConfig('ledger','accounts','account_no',(c('account_no','int64'),c('balance','int64'),c('active','bool'),c('label','text'))),
 TableConfig('Feature-X','Flag.Store','Feature Key',(c('Feature Key','text'),c('enabled','bool'))),
 TableConfig('业务','Object Space','Key',(c('Key','int64'),c('note','text'),c('score','int64'),c('flag','bool'),c('region','text'),c('revision','text')))),default_schema='ledger')
policy=SourceInstallPolicy('mtw_source_example',('application_login',))
statements=installation_ddl(config,policy)
result={'format':'configured-source-offline-plan/v1','configSha256':config.sha256,'tableColumnCounts':[len(t.columns)for t in config.tables],'statementCount':len(statements),'actualDatabaseExecution':False,'sourceFactsProduced':False,'writerWindowVerified':False,'moonbitCatalogVerified':False}
if sys.argv[1:]==['--show-ddl']:result['ddl']=list(statements)
elif sys.argv[1:]:raise SystemExit('Usage: configured-source-plan.py [--show-ddl]')
print(json.dumps(result,ensure_ascii=False,indent=2))
