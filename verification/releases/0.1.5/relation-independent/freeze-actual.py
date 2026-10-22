"""Copy the successful actual-v0.1.5 audit and its complete executable input closure."""
import hashlib
import json
import shutil
from pathlib import Path

here = Path(__file__).resolve().parent
root = here.parents[3]
run = root / 'artifacts/r15-actual/actual15-wPC00h'
receipt = json.loads((run / 'receipt.json').read_text(encoding='utf-8'))
assert receipt['passed'] and receipt['version'] == '0.1.5' and len(receipt['checks']) == 9
assert receipt['sourceUnchanged'] and receipt['runtimeUnchanged'] and receipt['fingerprintUnchanged']
mirror = here / 'reproduction/repository'
copies = {}

def binding(path):
    raw = path.read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

def copy(original, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        assert binding(original) == binding(target)
    else:
        shutil.copyfile(original, target)
    assert binding(original) == binding(target)
    copies[target.relative_to(here).as_posix()] = {'source': original.relative_to(root).as_posix(), **binding(original)}

for path in run.rglob('*'):
    if path.is_file():
        copy(path, here / 'actual-v015/run' / path.relative_to(run))
for name, value in {**receipt['sourceBindingsBefore'], **receipt['runtimeBindingsBefore']}.items():
    assert binding(root / name) == value
    copy(root / name, mirror / name)
for name in ['LICENSE', 'THIRD_PARTY.md']:
    copy(root / name, mirror / name)
expected = json.loads((here / 'expected.actual.json').read_text(encoding='utf-8'))
legacy = expected['legacy']
register = root / legacy['registerReceipt']
copy(register, mirror / register.relative_to(root))
for name in ['rr.capsule.json', 'serial.capsule.json', 'mini.capsule.json']:
    copy(register.parent / name, mirror / register.parent.relative_to(root) / name)
phase_path = root / legacy['listPhaseReceipt']
copy(phase_path, mirror / phase_path.relative_to(root))
phase = json.loads(phase_path.read_text(encoding='utf-8'))
list_path = root / 'verification' / phase['receipts']['list']['path']
for name in ['database-receipt.json', 'model-receipt.json']:
    copy(list_path / name, mirror / list_path.relative_to(root) / name)
list_database = json.loads((list_path / 'database-receipt.json').read_text(encoding='utf-8'))
for row in list_database['cases']:
    copy(list_path / row['directory'] / 'capsule.json', mirror / list_path.relative_to(root) / row['directory'] / 'capsule.json')
raw_path = root / expected['database']['rawDirectory']
model_path = root / expected['database']['modelDirectory']
raw = json.loads((raw_path / 'database-receipt.json').read_text(encoding='utf-8'))
model = json.loads((model_path / 'model-receipt.json').read_text(encoding='utf-8'))
copy(raw_path / 'database-receipt.json', mirror / raw_path.relative_to(root) / 'database-receipt.json')
for row in raw['scenarios']:
    for value in row['artifacts']:
        original = raw_path / row['path'] / value['path']
        assert binding(original) == {'bytes': value['bytes'], 'sha256': value['sha256']}
        copy(original, mirror / original.relative_to(root))
copy(model_path / 'model-receipt.json', mirror / model_path.relative_to(root) / 'model-receipt.json')
copy(model_path / 'independent-oracle-executed.py', mirror / model_path.relative_to(root) / 'independent-oracle-executed.py')
by_case = {(row['name'], row['round']): row['path'] for row in raw['scenarios']}
for row in model['cases']:
    for name, value in row['artifactBindings'].items():
        original = model_path / by_case[(row['name'], row['round'])] / name
        assert binding(original) == value
        copy(original, mirror / original.relative_to(root))
new_phase = root / 'verification/releases/0.1.5/relation-database-20261022T132231Z-c9085b9c.json'
copy(new_phase, mirror / new_phase.relative_to(root))
copy_record = here / 'actual-input-copy-bindings.json'
if copy_record.exists():
    assert json.loads(copy_record.read_text(encoding='utf-8')) == copies
else:
    with copy_record.open('x', encoding='utf-8') as output:
        output.write(json.dumps(copies, indent=2) + '\n')
blocked = [str(root).encode(), root.as_posix().encode(),
           ('C:' + chr(92) + 'Users' + chr(92)).encode(), ('C:/' + 'Users/').encode(),
           ('D:' + chr(92) + 'CodexScratch').encode(), ('D:/' + 'CodexScratch').encode()]
configuration_file = mirror / 'experiments/relation_v3/local_postgres.py'
configuration_binding = receipt['sourceBindingsBefore']['experiments/relation_v3/local_postgres.py']
assert binding(configuration_file) == configuration_binding
configured_guard = ('D:/' + 'CodexScratch/MoonTxnWitness-v011-20261020').encode()
assert configuration_file.read_bytes().count(configured_guard) == 1
for path in here.rglob('*'):
    if path.is_file():
        raw = path.read_bytes()
        if path == configuration_file:
            raw = raw.replace(configured_guard, b'<fixed-generic-owned-database-scratch-guard>')
        for prefix in blocked:
            assert prefix not in raw, path.relative_to(here)
privacy = {'schema': 1, 'kind': 'actual-v015-public-closure-private-prefix-scan', 'passed': True,
           'privateOriginalsCopied': False,
           'exactStaticSourceConfigurationException': {
               'file': configuration_file.relative_to(here).as_posix(), **configuration_binding,
               'literalSha256': hashlib.sha256(configured_guard).hexdigest(), 'occurrences': 1,
               'reason': 'Previously public fixed generic scratch guard for owned database helpers; no username or credentials. Source bytes preserved. This helper is not executed in offline review.'}}
with (here / 'privacy-actual.json').open('x', encoding='utf-8') as output:
    output.write(json.dumps(privacy, indent=2) + '\n')
print(json.dumps({'copiedFiles': len(copies), 'copiedRawBytes': sum(value['bytes'] for value in copies.values()),
                  'actualReceipt': binding(here / 'actual-v015/run/receipt.json'), 'privatePrefixScanPassed': True}))
