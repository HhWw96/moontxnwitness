"""Produce frozen Python point projections and reuse r3 descriptors; executes no DB."""
from pathlib import Path
import argparse
import hashlib
import importlib.metadata
import json
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
cli = argparse.ArgumentParser(description=__doc__)
cli.add_argument('--projection-root', default=str(ROOT))
cli.add_argument('--dependency-root')
cli.add_argument('--recorded-receipt')
cli.add_argument('--output', required=True)
args = cli.parse_args()
frozen = Path(args.projection_root).resolve()
dependency = Path(args.dependency_root).resolve() if args.dependency_root else None
frozen_files = [frozen/'integrations/python/moontxnwitness_capture/configured_point_projection_v2.py',
                frozen/'docs/configured-point-projection-v2.md']
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
before = {str(path):digest(path) for path in frozen_files}
recorded_path = Path(args.recorded_receipt).resolve() if args.recorded_receipt else None
recorded_bytes = recorded_path.read_bytes() if recorded_path else None
recorded = json.loads(recorded_bytes) if recorded_bytes else {'records': []}
if recorded_path:
    assert recorded['passed'] and recorded['actualDatabaseExecution']
sys.dont_write_bytecode = True
sys.path[:0] = [str(frozen/'integrations/python')] + ([str(dependency)] if dependency else [])
from moontxnwitness_capture.configured_sql_v2 import (
    ColumnConfig, PrimaryKeyConfigV2, TableConfigV2, SQLCaptureConfigV2, ConfiguredSQLParserV2, TEXT_COMPARISON,
)
from moontxnwitness_capture.configured_point_projection_v2 import PointProjectionOptionsV2, build_point_projection
import moontxnwitness_capture.configured_point_projection_v2 as implementation
assert Path(implementation.__file__).resolve() == frozen_files[0]
assert importlib.metadata.version('sqlglot') == '30.26.0'
canonical = lambda value: json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
q = lambda name:'"'+name.replace('"','""')+'"'
text = lambda name:ColumnConfig(name,'text',TEXT_COMPARISON)
tables = (
    TableConfigV2('ledger','accounts',PrimaryKeyConfigV2('account_no','int64'),(ColumnConfig('balance','int64'),ColumnConfig('active','bool'),text('label'))),
    TableConfigV2('App-X','Customer.Space',PrimaryKeyConfigV2('User ID','text',TEXT_COMPARISON),(ColumnConfig('quota','int64'),ColumnConfig('live','bool'),text('zone'))),
    TableConfigV2('业务','成员',PrimaryKeyConfigV2('用户编号','uuid'),(text('电子邮件'),ColumnConfig('启用','bool'))),
)
configs = [SQLCaptureConfigV2(table) for table in tables]
approved = lambda config:PointProjectionOptionsV2(config,star_contract='preinstallation-business-schema/v1',business_star_columns=tuple(c.name for c in config.table.columns))
cases = []
for record in recorded['records']:
    config = configs[record['layout']]
    options = approved(config)
    descriptor = record['projection']
    cases.append({'name':'recorded-'+str(record['layout'])+'-'+record['case'],'origin':'recorded-r3-descriptor',
        'configText':canonical(config.to_dict()),'source':record['originalSql'],
        'typedParametersText':canonical(descriptor['originalParameters']),'independentOptionsText':canonical(options.to_dict()),
        'descriptorText':canonical(descriptor)})


def add(name,config,source,parameters,options=None):
    options = options or approved(config)
    plan = ConfiguredSQLParserV2(config).recognize(source)
    result = build_point_projection(plan,parameters,options)
    descriptor = result.to_dict()
    cases.append({'name':name,'origin':'actual-frozen-Python-construction',
        'configText':canonical(config.to_dict()),'source':source,
        'typedParametersText':canonical(descriptor['originalParameters']),'independentOptionsText':canonical(options.to_dict()),
        'descriptorText':canonical(descriptor)})


base = configs[0]
if not recorded_path:
    add('offline-reference-update',base,'UPDATE ledger.accounts SET balance=%s WHERE account_no=%s RETURNING *',(23,7))
    add('offline-select-star',base,'SELECT * FROM ledger.accounts WHERE account_no=%s',(7,))
    add('offline-delete-returning',base,'DELETE FROM ledger.accounts WHERE account_no=%s RETURNING account_no AS "Business Key"',(7,))
add('named-repeated-dict-order',base,'UPDATE ledger.accounts SET label=%(Name)s,balance=%(same)s WHERE account_no=%(same)s',{'same':12,'Name':'100% raw %(same)s'})
add('literal-int64-maximum',base,'UPDATE ledger.accounts SET label=%s,balance=%s WHERE account_no=9223372036854775807',['"; DROP TABLE never; -- %s',-(2**63)])
explicit = 'SELECT label AS title,active AS enabled,account_no AS pk,balance AS amount FROM ledger.accounts WHERE account_no=7'
for name,params in [('none',None),('tuple',()),('list',[]),('dict',{})]:
    add('empty-container-'+name,base,explicit,params,PointProjectionOptionsV2(base))
for name,params in [('tuple',(7,)),('list',[7])]:
    add('positional-container-'+name,base,'SELECT * FROM ledger.accounts WHERE account_no=%s',params)
identifier = uuid.UUID('A8098C1A-F86E-11DA-BD1A-00112444BE1E')
target = q(tables[2].schema)+'.'+q(tables[2].table)
for cast in ['%s','%s::UUID','CAST(%s AS UUID)']:
    for name,value in [('object',identifier),('upper',str(identifier).upper()),('hex',identifier.hex.upper())]:
        add('uuid-'+cast+'-'+name,configs[2],'SELECT * FROM '+target+' WHERE '+q(tables[2].primary_key)+'='+cast,[value])
collision = SQLCaptureConfigV2(TableConfigV2('s','__mtw_v2_old',PrimaryKeyConfigV2('k','int64'),
    (ColumnConfig('__mtw_v2_new','int64'),ColumnConfig('__mtw_v2_old_0','int64'))))
add('alias-collisions-old-new-hidden',collision,'UPDATE s.__mtw_v2_old SET __mtw_v2_new=%s WHERE k=%s RETURNING k AS __mtw_v2_old_version',(1,2))
add('alias-collisions-read-version',base,'SELECT account_no AS __mtw_v2_old,balance AS __mtw_v2_new,active AS __mtw_v2_read_version,label AS label FROM ledger.accounts WHERE account_no=%s',(7,))
percent = SQLCaptureConfigV2(TableConfigV2('s%','t%s',PrimaryKeyConfigV2('k','int64'),(ColumnConfig('v%"','int64'),)))
add('identifier-percent-double-escape',percent,'SELECT * FROM "s%"."t%s" WHERE k=7',None,PointProjectionOptionsV2(percent,version_column='version%"',star_contract='preinstallation-business-schema/v1',business_star_columns=tuple(c.name for c in percent.table.columns)))
symbol = SQLCaptureConfigV2(TableConfigV2('s','t',PrimaryKeyConfigV2('k*','text',TEXT_COMPARISON),(ColumnConfig('v','bool'),)))
add('quoted-star-comment-literal-not-wildcard',symbol,'SELECT /* * */ "k*",v FROM s.t WHERE "k*"=\'*\'',None,PointProjectionOptionsV2(symbol))
add('literal-percent-value-not-interpolated',configs[1],'DELETE FROM "App-X"."Customer.Space" WHERE "User ID"=\'100% raw%s\' RETURNING "User ID"',None,PointProjectionOptionsV2(configs[1]))
add('explicit-C-text-identity',configs[1],'SELECT * FROM "App-X"."Customer.Space" WHERE "User ID" COLLATE "C"=%s',('键🙂',))
add('custom-int64-version-column',base,'DELETE FROM ledger.accounts WHERE account_no=%s',(7,),PointProjectionOptionsV2(base,version_column='version_identity'))
add('original-returning-order-aliases',base,'UPDATE ledger.accounts SET balance=%s WHERE account_no=%s RETURNING label AS title,balance AS amount',(5,7))

after = {str(path):digest(path) for path in frozen_files}
assert after == before and (recorded_path is None or recorded_path.read_bytes() == recorded_bytes)
drivers = sorted(name for name in sys.modules if name=='psycopg' or name.startswith('psycopg.') or name=='sqlalchemy' or name.startswith('sqlalchemy.'))
assert not drivers
output = Path(args.output).resolve()
output.parent.mkdir(parents=True,exist_ok=True)
receipt = {'format':'point-projection-v2-real-Python-cross-inputs/v1','cases':cases,
    'recordedDescriptorCases':len(recorded['records']),'actualPythonConstructionCases':len(cases)-len(recorded['records']),
    'recordedReceipt':str(recorded_path) if recorded_path else None,'recordedReceiptSha256':hashlib.sha256(recorded_bytes).hexdigest() if recorded_bytes else None,
    'frozenSourceBeforeSha256':before,'frozenSourceAfterSha256':after,'frozenFilesUnchanged':True,'originalReceiptUnchanged':True,
    'sqlglotVersion':importlib.metadata.version('sqlglot'),'databaseDriverOrOrmModulesLoaded':drivers,
    'actualDatabaseExecution':False,'descriptorRecomputationOnly':True,'sourceFactsProduced':False,'completeWindow':False,'modelCoverageAccepted':False,
    'producerSha256':digest(Path(__file__))}
output.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'cases':len(cases),'recordedDescriptors':receipt['recordedDescriptorCases'],'freshPythonConstructions':receipt['actualPythonConstructionCases'],'output':str(output)}))
