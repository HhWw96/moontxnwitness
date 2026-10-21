
import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'integrations/python'))
from moontxnwitness_capture.journal_v3 import SegmentedJournal,JournalReader
trace=json.loads(Path('fixtures/v3/initial-read-commit.json').read_bytes())
w=SegmentedJournal('fresh-journal')
for event in trace['events']:
    assert w.append(event).accepted
assert w.close(source_closed=True).complete
result=JournalReader('fresh-journal').export('journal-export.json',clock_domain=trace['clockDomain'],exclusive_writers=True)
raw=Path('journal-export.json').read_bytes()
assert result['bytes']==len(raw) and result['sha256']==hashlib.sha256(raw).hexdigest()
assert json.loads(raw)==trace
print(json.dumps({'passed':True,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'actualDatabaseExecution':False}))
