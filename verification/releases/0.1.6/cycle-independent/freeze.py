from pathlib import Path
import datetime,hashlib,json
OUT=Path(__file__).resolve().parent
def binding(p):
    b=p.read_bytes()
    return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def write_json(p,x):
    with p.open('x',encoding='utf-8',newline='\n') as f:
        json.dump(x,f,ensure_ascii=False,indent=2)
        f.write('\n')
assert not (OUT/'closure-manifest.json').exists()
primary=OUT/'runs/review-ApJey1/receipt.json'
offline=OUT/'offline-replay/review-XCvsac/receipt.json'
a=json.loads(primary.read_text(encoding='utf-8'));b=json.loads(offline.read_text(encoding='utf-8'))
assert a['passed'] and b['passed'] and len(a['checks'])==len(b['checks'])==10
assert a['mainSourceAndRuntimeUnchanged'] is True
assert a['frozenDependenciesUnchanged'] and b['frozenDependenciesUnchanged']
assert a['actualBuild']['sourceSha256']=='3eabe931cc6816527c0cf43334722b805ab8dc51bd66be102232c79eb43e41b1'
summary={'schema':1,'kind':'independent-ai-actual-v016-cycle-review','passed':True,
 'actualBuild':a['actualBuild'],'primaryReceipt':{'path':primary.relative_to(OUT).as_posix(),**binding(primary)},
 'standaloneOfflineReplay':{'path':offline.relative_to(OUT).as_posix(),**binding(offline)},
 'groups':10,'frozenHistories':132,'generatedRingCases':117,'additionalSavepointCases':2,'originalManualCases':13,
 'derivedMutationsRejected':11,'sourceMutationsRejected':8,
 'storedOldCapsulesReplayed':{'registerV2':3,'captureV2':4,'listV3':120,'relationV3':160,'total':287},
 'oldCapsuleSourceVersionsRetained':True,'countsOverlap':True,
 'onlyExpectedReportVersionDifferences':['top-level version','nested evidence.version'],
 'onlyExpectedV2ReplayVersionDifference':'currentEngine',
 'observationVersionIdentitiesUnchanged':True,'frozenExpectationsChanged':False,
 'sourceAndRuntimeVerifiedBeforeImport':True,'mainSourceAndRuntimeUnchanged':True,
 'storedOldElleInputsReviewed':8,'retainedEmptyGraphUnknowns':2,'newElleExecution':False,
 'databaseExecuted':False,'newCoreBuilt':False,'performanceMeasured':False,'downloaded':False,
 'overallMainRegressionReexecuted':False,'humanAcceptance':False,'contestApproval':False,
 'preparationFailureRetained':'preparation-attempt1-failure.json',
 'preparationFailureBeforeProductImport':True,'originalToolFailureStillInConversation':True,
 'legacyOriginLinkAudit':binding(OUT/'legacy-origin-link-audit.json'),
 'findingsRequiringImplementationChange':[]}
write_json(OUT/'review-summary.json',summary)
private_hits=[]
prefix=chr(67)+':'+chr(92)+'Users'+chr(92)
escaped_prefix=prefix.replace(chr(92),chr(92)*2)
for p in OUT.rglob('*'):
    if not p.is_file():continue
    s=p.read_text(encoding='utf-8',errors='ignore')
    if prefix in s or escaped_prefix in s:
        private_hits.append(p.relative_to(OUT).as_posix())
assert not private_hits,private_hits
files={p.relative_to(OUT).as_posix():binding(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='closure-manifest.json'}
manifest={'schema':1,'kind':'complete-lightweight-actual-v016-independent-review-closure',
 'frozenAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'passed':True,
 'sourceSha256':a['actualBuild']['sourceSha256'],'coreSha256':a['actualBuild']['coreSha256'],
 'captureCoreSha256':a['actualBuild']['captureCoreSha256'],
 'summary':binding(OUT/'review-summary.json'),'primaryReceipt':binding(primary),
 'standaloneReplayPassed':True,'newDatabaseOrElleExecution':False,'newCoreBuild':False,
 'formalPerformanceMeasured':False,'fullSourceMirrorIncluded':False,
 'privateLocalPrefixScanPassed':True,'rawBytes':sum(v['bytes'] for v in files.values()),'files':files}
write_json(OUT/'closure-manifest.json',manifest)
print(json.dumps({'closure':'artifacts/v016-actual-independent','manifest':binding(OUT/'closure-manifest.json'),
 'summary':binding(OUT/'review-summary.json'),'primaryReceipt':binding(primary),'files':len(files),'rawBytes':manifest['rawBytes']},ensure_ascii=False))
