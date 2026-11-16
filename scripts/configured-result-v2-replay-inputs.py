"""Read an existing PG receipt into bounded V2 result replay fixtures; no DB imports."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
cli = argparse.ArgumentParser(description=__doc__)
cli.add_argument('--receipt', required=True)
cli.add_argument('--observer-source', required=True)
cli.add_argument('--output', required=True)
args = cli.parse_args()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'integrations/python'))
from moontxnwitness_capture.configured_sql_v2 import (
    ColumnConfig, PrimaryKeyConfigV2, TableConfigV2, SQLCaptureConfigV2, TEXT_COMPARISON,
)

sha = lambda data: hashlib.sha256(data).hexdigest()
canonical = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
source_path = Path(args.receipt).resolve()
source_bytes = source_path.read_bytes()
receipt = json.loads(source_bytes)
assert receipt['passed'] and receipt['actualDatabaseExecution']
assert not receipt['sourceFactsProduced'] and not receipt['modelCoverageAccepted']
observer = Path(args.observer_source).resolve()
observer_digest = sha(observer.read_bytes())
assert observer_digest == receipt['sourceSha256'][r'scripts\configured-point-projection-postgres.py']

# Independent fixture declarations; no config or budget is taken from a candidate.
text = lambda name: ColumnConfig(name, 'text', TEXT_COMPARISON)
configs = [
    SQLCaptureConfigV2(TableConfigV2('ledger','accounts',PrimaryKeyConfigV2('account_no','int64'),
        (ColumnConfig('balance','int64'),ColumnConfig('active','bool'),text('label')))),
    SQLCaptureConfigV2(TableConfigV2('App-X','Customer.Space',PrimaryKeyConfigV2('User ID','text',TEXT_COMPARISON),
        (ColumnConfig('quota','int64'),ColumnConfig('live','bool'),text('zone')))),
    SQLCaptureConfigV2(TableConfigV2('业务','成员',PrimaryKeyConfigV2('用户编号','uuid'),
        (text('电子邮件'),ColumnConfig('启用','bool')))),
]


def semantic_scalar(observed):
    kind = observed['pythonType']
    if kind in ('int','builtins.int'):
        value = int(observed['decimal'])
        assert str(value) == observed['decimal'] and -(2**63) <= value < 2**63
        return value
    if kind in ('str','builtins.str','uuid.UUID'):
        assert type(observed['value']) is str
        return observed['value']
    if kind in ('bool','builtins.bool'):
        assert type(observed['value']) is bool
        return observed['value']
    raise ValueError('Unsupported original Python parameter observation: ' + kind)


def semantic_parameters(observed):
    if observed['container'] in ('tuple','list'):
        return [semantic_scalar(item) for item in observed['items']]
    if observed['container'] == 'dict':
        return {key:semantic_scalar(value) for key,value in observed['items'].items()}
    raise ValueError('Unrecorded original parameter container')


cases = []
for index, record in enumerate(receipt['records']):
    assert record['passed'] and record['testTransactionOutcome'] == 'rolled-back'
    original = record['baselineNative']
    assert original['fieldCount'] == len(original['fields'])
    assert original['rowCount'] == len(original['rows'])
    actual_delivery = original['deliveryObservation']
    parameters = semantic_parameters(record['projection']['originalParameters'])
    config = configs[record['layout']]
    # Labels, note positions and digest references are fixture-derived, not lifecycle evidence.
    identity = {'connection':'fixture-connection-'+str(record['layout']), 'cursor':'fixture-cursor-'+str(index),
                'tx':'fixture-rolled-back-case-'+str(index), 'statementSeq':index+1}
    execution_note, native_note = index*3+1, index*3+2
    sql = record['originalSql']
    assert sql == record['projection']['originalSql']
    execution = {'format':'moontxnwitness-configured-execution/v2', **identity, 'executionNoteSeq':execution_note,
        'sql':sql, 'parameters':parameters, 'candidate':record['projection']['candidate'],
        'sqlRewritten':False, 'success':original['status'] in (1,2), 'decoderContract':'psycopg-default-text-scalars/v2'}
    count = original['commandTuples']
    assert count is None or type(count) is int
    native = {'format':'moontxnwitness-native-result/v2', **identity, 'executionNoteSeq':execution_note,
        'nativeNoteSeq':native_note, 'resultId':'fixture-result-'+str(index),
        'sqlSha256':sha(sql.encode('utf-8')), 'originalParametersSha256':sha(canonical(parameters).encode('utf-8')),
        'status':original['status'], 'clientEncodingBase64':original['clientEncodingBase64'],
        'commandStatusBase64':original['commandStatusBase64'],
        'commandTuples':{'pythonType':'builtins.NoneType' if count is None else 'builtins.int','value':None if count is None else str(count)},
        'fields':original['fields'], 'rows':original['rows']}
    deliveries = []
    rows = record['baselineBusinessRows']
    if rows is None:
        assert actual_delivery['method'] is None and actual_delivery['rowsContainerPythonType'] is None
        assert actual_delivery['rowPythonTypes'] == []
    else:
        assert actual_delivery['method'] == 'fetchall'
        assert len(actual_delivery['rowPythonTypes']) == len(rows)
        typed_rows = [{'pythonType':actual_delivery['rowPythonTypes'][i],'cells':row} for i,row in enumerate(rows)]
        deliveries.append({'format':'moontxnwitness-actual-delivery/v2', **identity, 'resultId':native['resultId'],
            'nativeNoteSeq':native_note, 'deliveryNoteSeq':index*3+3, 'start':0,
            'method':actual_delivery['method'], 'resultPythonType':actual_delivery['rowsContainerPythonType'],
            'requestedSize':actual_delivery['requestedSize'], 'effectiveSize':actual_delivery['effectiveSize'],
            'exhaustedObserved':actual_delivery['exhaustedObserved'], 'rows':typed_rows})
    cases.append({'name':str(record['layout'])+'-'+record['case'], 'layout':record['layout'],
        'configText':canonical(config.to_dict()), 'executionText':canonical(execution), 'nativeText':canonical(native),
        'deliveriesText':canonical(deliveries), 'originalParameterObservation':record['projection']['originalParameters'],
        'originalBaselineNative':original, 'originalBusinessRows':rows, 'originalTestOutcome':record['testTransactionOutcome']})

assert source_path.read_bytes() == source_bytes
driver_modules = sorted(name for name in sys.modules if name == 'psycopg' or name.startswith('psycopg.') or name == 'sqlalchemy' or name.startswith('sqlalchemy.'))
assert not driver_modules
out = Path(args.output).resolve()
out.parent.mkdir(parents=True,exist_ok=True)
output = {'format':'configured-result-v2-recorded-payload-replay-inputs/v1','cases':cases,
    'inputReceipt':str(source_path),'inputReceiptSha256':sha(source_bytes),'observerSourceSha256':observer_digest,
    'inputPostgresVersion':receipt['postgresVersion'],'inputActualDatabaseExecution':True,
    'actualDatabaseExecution':False,'driverWrapperOrLifecycleVerified':False,'sourceFactsProduced':False,
    'databaseDriverOrOrmModulesLoaded':driver_modules,
    'modelCoverageAccepted':False,'commitVerified':False,'originalReceiptUnchanged':True,
    'fixtureDerivedFields':['event labels and note sequences','start=0 from one actually observed fetchall','original SQL and semantic parameter JSON digest references','success from recorded native status','bounded decoder contract declaration'],
    'parameterSerializationRule':'Original Python container/scalar observations retained separately; UUID objects serialize to their recorded UUID text only for independent semantic JSON binding checks. No business args reconstructed or changed.',
    'scope':'Replay existing original-SQL native bytes and actual recorded collection/row/scalar delivery payload only; fixture event references do not authenticate the actual execution lifecycle.',
    'producerSha256':sha(Path(__file__).read_bytes())}
out.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'cases':len(cases),'inputReceiptSha256':output['inputReceiptSha256'],'output':str(out)}))
