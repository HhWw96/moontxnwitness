"""Produce actual V2 Python candidates and typed input logs, without a database."""
from pathlib import Path
import argparse
import hashlib
import importlib.metadata
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
args_parser = argparse.ArgumentParser(description=__doc__)
args_parser.add_argument('--dependency-root')
args_parser.add_argument('--output', required=True)
args = args_parser.parse_args()
dependency = Path(args.dependency_root).resolve() if args.dependency_root else None
if dependency is not None and not dependency.is_dir(): args_parser.error('Existing dependency root required')
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT / 'integrations/python')] + ([str(dependency)] if dependency else [])
from moontxnwitness_capture.configured_sql_v2 import (
    ColumnConfig, PrimaryKeyConfigV2, TableConfigV2, SQLCaptureConfigV2,
    ConfiguredSQLParserV2, TEXT_COMPARISON,
)

canonical = lambda value: json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
sha = lambda text: hashlib.sha256(text.encode('utf-8')).hexdigest()
quote = lambda name: '"' + name.replace('"', '""') + '"'
column = lambda name, kind: ColumnConfig(name, kind, TEXT_COMPARISON if kind == 'text' else None)
tables = (
    TableConfigV2('ledger', 'accounts', PrimaryKeyConfigV2('account_no', 'int64'),
        (column('balance','int64'), column('active','bool'), column('label','text'))),
    TableConfigV2('App-X', 'Customer.Space', PrimaryKeyConfigV2('User ID', 'text', TEXT_COMPARISON),
        (column('quota','int64'), column('live','bool'), column('zone','text'), column('score','int64'), column('note','text'))),
    TableConfigV2('identity', 'members', PrimaryKeyConfigV2('member_uuid','uuid'),
        (column('email','text'), column('is_active','bool'))),
)
configs = [SQLCaptureConfigV2(table) for table in tables]
parsers = [ConfiguredSQLParserV2(config) for config in configs]
cases = []


def add(name, index, sql, parameters):
    plan = parsers[index].recognize(sql)
    bindings = [{'reference': ref.to_dict(), 'value': {'type': ref.type, 'value': str(value) if ref.type == 'int64' else value}}
                for ref, value in plan.bind(parameters)]
    cases.append({'name': name, 'layout': index, 'configText': canonical(configs[index].to_dict()),
        'configSha256': configs[index].sha256, 'sql': sql, 'parametersText': canonical(parameters),
        'originalParametersSha256': sha(canonical(parameters)), 'candidateText': canonical(plan.to_dict()),
        'descriptorSha256': sha(canonical(plan.to_dict())), 'bindings': bindings})


for index, table in enumerate(tables):
    target = quote(table.schema) + '.' + quote(table.table)
    fields = ','.join(quote(c.name) for c in table.columns)
    key = quote(table.primary_key)
    row = tuple('A8098C1AF86E11DABD1A00112444BE1E' if c.type == 'uuid' else '值🙂' if c.type == 'text' else True if c.type == 'bool' else 17 for c in table.columns)
    slot = '%s::UUID' if table.key.type == 'uuid' else '%s'
    add('layout' + str(index) + '-select', index, 'SELECT ' + fields + ' FROM ' + target + ' WHERE ' + key + '=' + slot, (row[0],))
    slots = ','.join(slot if c.name == table.primary_key else '%s' for c in table.columns)
    add('layout' + str(index) + '-insert', index, 'INSERT INTO ' + target + '(' + fields + ') VALUES(' + slots + ') RETURNING *', row)
    add('layout' + str(index) + '-update', index, 'UPDATE ' + target + ' SET ' + quote(table.business_columns[0].name) + '=%s WHERE ' + key + '=' + slot + ' RETURNING ' + key, (row[1],row[0]))
    add('layout' + str(index) + '-delete', index, 'DELETE FROM ' + target + ' WHERE ' + key + '=' + slot, (row[0],))
for spelling in ['a8098c1a-f86e-11da-bd1a-00112444be1e','A8098C1A-F86E-11DA-BD1A-00112444BE1E','A8098C1AF86E11DABD1A00112444BE1E']:
    add('uuid-spelling-' + str(len(cases)), 2, 'SELECT m.* FROM identity.members m WHERE m.member_uuid=CAST(%(pk_1)s AS UUID)', {'pk_1':spelling})
for value in [-9223372036854775808, 9223372036854775807]:
    add('int64-' + str(value), 0, 'SELECT * FROM ledger.accounts WHERE account_no=%s', [value])
add('named-repeated', 0, 'UPDATE ledger.accounts SET balance=%(who)s,label=%(Name)s WHERE account_no=%(who)s', {'who':13,'Name':'原始%s'})
add('literal-key-percent', 0, 'DELETE /* raw %s */ FROM ledger.accounts WHERE account_no=7 RETURNING *', None)

# Real SQLAlchemy mapper refresh and INSERT, compiled without a database.
assert importlib.metadata.version('sqlalchemy') == '2.0.55'
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import psycopg
from sqlalchemy.orm import DeclarativeBase, mapped_column
class Base(DeclarativeBase): pass
class Member(Base):
    __tablename__ = 'members'
    __table_args__ = {'schema':'identity'}
    member_uuid = mapped_column(sa.Uuid, primary_key=True)
    email = mapped_column(sa.String(320), nullable=False)
    is_active = mapped_column(sa.Boolean, nullable=False)
clause, _ = sa.inspect(Member)._get_clause
compiled = sa.select(Member).where(clause).compile(dialect=psycopg.dialect())
add('sqlalchemy2055-refresh', 2, str(compiled), {key:'A8098C1AF86E11DABD1A00112444BE1E' for key in compiled.params})
compiled = sa.insert(Member).values(member_uuid='A8098C1AF86E11DABD1A00112444BE1E', email='值🙂 ',
    is_active=True).returning(Member.member_uuid).compile(dialect=psycopg.dialect())
assert '%(email)s::VARCHAR' in str(compiled)
add('sqlalchemy2055-insert', 2, str(compiled), compiled.params)
add('direct-varchar-bind', 0, 'UPDATE ledger.accounts SET label=(%s::vArChAr) WHERE account_no=%s', ['值🙂 ', 7])
output = Path(args.output).resolve()
output.parent.mkdir(parents=True, exist_ok=True)
receipt = {'format':'configured-sql-v2-real-python-cross-inputs/v1', 'cases':cases,
    'sqlglotVersion':importlib.metadata.version('sqlglot'), 'sqlalchemyVersion':importlib.metadata.version('sqlalchemy'),
    'actualDatabaseExecution':False, 'sourceFactsProduced':False, 'modelCoverageAccepted':False,
    'producerSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'adapterSha256':hashlib.sha256((ROOT/'integrations/python/moontxnwitness_capture/configured_sql_v2.py').read_bytes()).hexdigest()}
output.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'cases':len(cases),'output':str(output),'sha256':hashlib.sha256(output.read_bytes()).hexdigest()}))
