"""Offline SQL recognition across three configurations; no database access."""
from pathlib import Path
import argparse
import json
import sys

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--dependency-root')
args=parser.parse_args()
sys.dont_write_bytecode=True
sys.path.insert(0,str(root/'integrations/python'))
if args.dependency_root:sys.path.insert(0,str(Path(args.dependency_root).resolve()))
from moontxnwitness_capture.configured_sql import ColumnConfig,TableConfig,SQLCaptureConfig,ConfiguredSQLParser,TEXT_COMPARISON


def column(name,kind):
    return ColumnConfig(name,kind,TEXT_COMPARISON if kind=='text' else None)


tables=(TableConfig('finance','balances','account_no',(column('account_no','int64'),column('amount','int64'))),
    TableConfig('app','flags','feature_key',(column('feature_key','text'),column('enabled','bool'),column('caption','text'))),
    TableConfig('Archive.Space','Asset-Items','Asset ID',(column('Asset ID','text'),column('units','int64'),column('active','bool'),column('region','text'),column('note','text'))))
recognizer=ConfiguredSQLParser(SQLCaptureConfig(tables))
quoted=lambda value:'"'+value.replace('"','""')+'"'
results=[]
for table in tables:
    sql='SELECT * FROM '+quoted(table.schema)+'.'+quoted(table.table)+' WHERE '+quoted(table.primary_key)+'=%s'
    plan=recognizer.recognize(sql)
    key=72 if table.columns[0].type=='int64' else 'key-72'
    bindings=plan.bind((key,))
    results.append({'originalSql':plan.original_sql,'schema':plan.table.schema,'table':plan.table.table,
        'primaryKey':plan.table.primary_key,'columns':len(plan.projections),'binds':len(bindings),
        'configSha256':plan.config_sha256,'captureFactsProduced':plan.to_dict()['captureFactsProduced'],
        'databaseSyntaxValidated':plan.to_dict()['databaseSyntaxValidated'],'moonbitProjectionVerified':False})
print(json.dumps({'parserContract':'sqlglot-30.26-postgres-single-table/v1','examples':results},ensure_ascii=False,indent=2))
