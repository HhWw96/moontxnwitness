from pathlib import Path
import hashlib,json
OUT=Path(__file__).resolve().parent
def binding(p):
    b=p.read_bytes()
    return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
load=lambda p:json.loads(p.read_text(encoding='utf-8'))
manifest=load(OUT/'inputs/legacy-capsules-manifest.json')
register=load(OUT/'inputs/legacy-receipts/0-receipt.json')
capture=load(OUT/'inputs/legacy-receipts/1-receipt.json')
listing=load(OUT/'inputs/legacy-receipts/2-database-receipt.json')
relation=load(OUT/'inputs/legacy-receipts/3-model-receipt.json')
database=load(OUT/'inputs/legacy-receipts/4-database-receipt.json')
assert all(x['actualDatabaseExecution'] is True for x in [register,capture,listing,database])
assert relation['actualDatabaseExecution'] is False
assert relation['sourceDatabaseExecutionReceipt']==binding(OUT/'inputs/legacy-receipts/4-database-receipt.json')
counts={'registerCapsuleHashToOriginalReceipt':0,'listTraceBytesToOriginalDatabaseReceipt':0,'relationCapsuleHashToOriginalModelReceipt':0,'captureCasesSupportedByStoredScenarioReceipt':0}
for row in manifest['capsules']:
    p=OUT/row['file']
    assert binding(p)=={'bytes':row['bytes'],'sha256':row['sha256']}
    capsule=load(p)
    if row['family']=='register-v2':
        assert register['files'][p.name]==row['sha256']
        counts['registerCapsuleHashToOriginalReceipt']+=1
    elif row['family']=='append-list-v3':
        case=next(x for x in listing['cases'] if x['directory']==p.parent.name)
        trace=next(x for x in case['files'] if x['file']=='trace.json')
        assert hashlib.sha256(capsule['traceText'].encode()).hexdigest()==trace['sha256']
        assert len(capsule['traceText'].encode())==trace['bytes']
        assert case['passed'] is True and case['expectedModelStatus']==row['expectedStatus']
        counts['listTraceBytesToOriginalDatabaseReceipt']+=1
    elif row['family']=='relation-v3':
        case=next(x for x in relation['cases'] if f"{x['name']}-{x['round']:02d}"==p.parent.name)
        assert case['artifactBindings']['capsule.json']==binding(p)
        assert case['passed'] is True and case['status']==row['expectedStatus']
        counts['relationCapsuleHashToOriginalModelReceipt']+=1
    else:
        case=next(x for x in capture['scenarios'] if x['name']==p.name.removesuffix('.capsule.json'))
        assert case['expectedVerdict']==row['expectedStatus']
        counts['captureCasesSupportedByStoredScenarioReceipt']+=1
assert counts=={'registerCapsuleHashToOriginalReceipt':3,'listTraceBytesToOriginalDatabaseReceipt':120,'relationCapsuleHashToOriginalModelReceipt':160,'captureCasesSupportedByStoredScenarioReceipt':4}
receipt={'schema':1,'passed':True,'newDatabaseExecution':False,'scope':'Read-only linkage of retained replay inputs to prior stored receipts; not source authentication or a new database run.',
         'counts':counts,'relationModelReceiptIsNotDatabaseExecution':True,
         'relationModelReceiptBindsPriorActualDatabaseReceipt':True,
         'captureReceiptHasScenarioAndRuntimeBindingsButNoPerCapsuleHash':'Four capsule bytes are frozen by the independent input manifest; the old capture receipt identifies scenarios and the producing runtime. No stronger per-capsule historical receipt hash claim is made.',
         'implementation':binding(Path(__file__)),
         'receipts':{p.name:binding(p) for p in (OUT/'inputs/legacy-receipts').iterdir()}}
with (OUT/'legacy-origin-link-audit.json').open('x',encoding='utf-8',newline='\n') as f:
    json.dump(receipt,f,ensure_ascii=False,indent=2)
    f.write('\n')
print(json.dumps({'passed':True,'counts':counts}))
