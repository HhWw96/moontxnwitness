"""Continue only the two CLI checks not executed after the retained stdout harness failure."""
from pathlib import Path
import hashlib,json,sys,traceback
ROOT=Path(__file__).resolve().parent.parent
HELPER=ROOT/'fix1/candidate_audit_fix1.py';raw=HELPER.read_bytes()
assert hashlib.sha256(raw).hexdigest()=='ab53f37bc3b8516f265db0741950a15ac8988c8a813eac1d02e1c26cd0ee5391'
ns={'__name__':'verified_offline_candidate_helpers','__file__':str(HELPER)};exec(compile(raw,str(HELPER),'exec'),ns)
out=Path(__file__).resolve().parent/'first-run';out.mkdir();write=ns['write_new'];binding=ns['binding'];decoded=ns['decoded'];run=ns['run']
old=ROOT/'fix1/first-run';extracted=ROOT/'first-run';portable=extracted/'portable-extracted/MoonTxnWitness-v0.2.7';source=extracted/'source-extracted/MoonTxnWitness-v0.2.7';node=Path(r'D:\nodejs\node.exe')
receipt={'format':'moontxnwitness027-prepublication-candidate-audit-continuation/v1','passed':False,'actualRemainingCliInvocations':0,'priorAnalysisCliRepeated':False,'firstTwoHarnessFailuresPreserved':True,'newDatabaseExecution':False,'newHTTP':False,'compilerExecuted':False,'publicDownloadVerified':False,'sourceClosedReductionClaimed':False,'fatal':None}
try:
 prior=decoded((old/'AUDIT.json').read_bytes());assert prior['passed']is False and 'JSONDecodeError'in prior['fatal'];assert len(prior['steps'])==7 and all(row.get('passed')is True for row in prior['steps'])
 process=decoded((old/'configured-cli-analyze.process.json').read_bytes());assert process['passed']is True and process['actualExitCode']==1 and process['stdout']['bytes']==0
 report=old/'configured-cli.report.json';capsule=old/'configured-cli.capsule.json';assert decoded(report.read_bytes())['status']=='violation'
 envelope=portable/'verification/releases/0.2.7/current-pg-sdk-loop/first/first-run/results/list-write-skew/source.original.json';cli=portable/'dist/moontxnwitness.mjs'
 receipt['actualRemainingCliInvocations']+=1;verified=run(node,[cli,'verify-model-profile-v3',envelope,report],'configured-cli-verify',out,portable);assert verified['valid']is True
 receipt['actualRemainingCliInvocations']+=1;replayed=run(node,[cli,'replay-model-profile-v3',capsule],'configured-cli-replay',out,portable);assert replayed['valid']is True and replayed['status']=='violation'
 receipt['configuredCliRoundTrip']={'analyzeAlreadyExecutedOnce':True,'analyzeExitCode':1,'analysisSavedReportIsViolation':True,'verificationPassed':True,'replayPassed':True,'totalActualCliInvocations':3}
 for kind,treepath in [('source',source),('portable',portable)]:
  manifest=decoded((extracted/(kind+'-extraction-manifest.json')).read_bytes());expected={row['file']:{k:row[k]for k in ('bytes','sha256')}for row in manifest};assert ns['tree'](treepath)==expected;receipt[kind+'AllOriginalFilesUnchanged']={'passed':True,'files':len(expected)}
 receipt['localSourceRebuild']={'status':'not-executed','initialCfreeBytes':430751744,'fixedCompilationMinimumCfreeBytes':1073741824,'reason':'Initial C reserve insufficient; no compiler run or substituted author dist. Original actual CI source consumer and Native results bound separately.'}
 receipt['resourceAfterChecks']=ns['resources'](out);receipt['passed']=True
except Exception:receipt['fatal']=traceback.format_exc()
write(out/'receipt.json',receipt);print(json.dumps(receipt));sys.exit(0 if receipt['passed']else 1)
