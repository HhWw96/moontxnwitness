"""Independent provisional relation inputs; writes a fresh ignored run only.

Expected classifications come from named hand-designed cases/templates below,
not from any production analyzer. The independent reference is only a selfcheck;
any disagreement is retained and never used to replace expected classifications.
"""
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid
from relation_oracle import analyze, MIN_I64, MAX_I64

HERE = Path(__file__).resolve().parent
OUT = HERE / ("frozen-draft-" + uuid.uuid4().hex)


def hash_bytes(value):
    return hashlib.sha256(value).hexdigest()


def row(key="0", version="v0", n="0", b=True, t=""):
    return {"key": key, "version": version, "values": {"n": n, "b": b, "t": t}}


class Trace:
    def __init__(self, rows=(), key_type="int64", relations=None):
        schema = {"primaryKey": "id", "columns": {"id": key_type, "n": "int64", "b": "bool", "t": "text"}}
        schemas = {"r": schema} if relations is None else relations
        self.t = {"traceSchema": 3, "dataModel": "relation-set-v1", "clockDomain": "independent-relation-draft", "relationSchema": schemas,
                  "scope": {"exclusiveWriters": True, "completeSnapshotTables": list(schemas)}, "events": [], "gaps": []}
        self.e("snapshot", initial={name: copy.deepcopy(list(rows)) if name == "r" else [] for name in schemas}, consistent=True)

    def e(self, kind, **fields):
        n = len(self.t["events"]) + 1
        self.t["events"].append({"seq": n, "time": n, "kind": kind, **copy.deepcopy(fields)})
        return n

    def begin(self, tx="T"):
        self.e("begin", tx=tx, connection="connection-" + tx)

    def commit(self, tx="T"):
        self.e("commit_request", tx=tx)
        self.e("commit_ok", tx=tx)

    def abort(self, tx="T"):
        self.e("rollback_ok", tx=tx)

    def read(self, rows, predicate=(), tx="T", relation="r", complete=True):
        self.e("row_read", tx=tx, relation=relation, rows=rows, predicate=list(predicate), complete=complete)

    def write(self, key, action, version, predecessor, values, tx="T", relation="r"):
        self.e("row_write", tx=tx, relation=relation, key=key, action=action, version=version, predecessor=predecessor, values=values)


def query(rows, predicate, actual=None, key_type="int64"):
    t = Trace(rows, key_type)
    t.begin(); t.read(rows if actual is None else actual, predicate); t.commit()
    return t.t


def freeze():
    OUT.mkdir(exist_ok=False)
    records = []

    def case(name, trace, expected, options=None, note=""):
        text = json.dumps(trace, ensure_ascii=True, separators=(",", ":"))
        records.append({"id": name, "traceText": text, "inputSha256": hash_bytes(text.encode()), "expected": expected, "options": {} if options is None else options, "note": note})

    # Precision boundaries differ beyond JavaScript's safe integer interval.
    integer_values = [MIN_I64, MIN_I64 + 1, -9007199254740993, -9007199254740992, -1, 0, 1,
                      9007199254740991, 9007199254740992, 9007199254740993, MAX_I64 - 1, MAX_I64]
    initial = [row(str(i), "int-v" + str(i), str(n)) for i, n in enumerate(integer_values)]
    compare = {"eq": lambda a, b: a == b, "lt": lambda a, b: a < b, "le": lambda a, b: a <= b, "gt": lambda a, b: a > b, "ge": lambda a, b: a >= b}
    for n in integer_values:
        for op, comparison in compare.items():
            actual = [r for r in initial if comparison(int(r["values"]["n"]), n)]
            case("int64-%s-%s" % (str(n), op), query(initial, [{"column": "n", "op": op, "value": str(n)}], actual), "consistent")
    for value in ["+1", "01", "-01", "-0", "1.0", "1e0", str(MIN_I64 - 1), str(MAX_I64 + 1), 1, 1.5, True, None]:
        case("invalid-int64-" + repr(value), query([row(n=value)], []), "invalid")
    texts = ["", "\x00", "A", "a", "é", "e\u0301", "\ue000", "\U00010000", "\U0010ffff"]
    text_rows = [row(value, "text-v" + str(i), str(i), t=value) for i, value in enumerate(texts)]
    for pivot in texts:
        for op in ["eq", "lt"]:
            actual = [r for r in text_rows if compare[op](r["key"], pivot)]
            case("unicode-codepoint-%s-%s" % (texts.index(pivot), op), query(text_rows, [{"column": "id", "op": op, "value": pivot}], actual, "text"), "consistent")
    case("unicode-no-normalization", query([row(t="e\u0301")], [{"column": "t", "op": "eq", "value": "é"}], []), "consistent")
    case("unpaired-high-surrogate", query([row(t="\ud800")], []), "invalid")
    case("unpaired-low-surrogate", query([row(t="\udfff")], []), "invalid")
    case("version-256-utf16-units", query([row(version="\U00010000" * 128)], []), "consistent")
    case("version-258-utf16-units", query([row(version="\U00010000" * 129)], []), "invalid")
    case("version-nul-is-scalar", query([row(version="\0")], []), "consistent")
    case("empty-version-invalid", query([row(version="")], []), "invalid")
    case("empty-and-empty-relation", query([], [], []), "consistent")
    case("contradictory-and", query([row()], [{"column": "n", "op": "gt", "value": "1"}, {"column": "n", "op": "lt", "value": "0"}], []), "consistent")
    case("bool-only-equality", query([row()], [{"column": "b", "op": "eq", "value": True}]), "consistent")
    case("bool-order-invalid", query([row()], [{"column": "b", "op": "lt", "value": True}], []), "invalid")
    case("predicate-no-implicit-conversion", query([row()], [{"column": "n", "op": "eq", "value": 0}], []), "invalid")
    case("duplicate-returned-key", query([row()], [], [row(), row()]), "violation")
    case("known-version-wrong-key", query([row()], [], [row(key="1")]), "violation")
    case("known-version-wrong-content", query([row()], [], [row(n="1")]), "violation")
    case("known-row-does-not-match", query([row()], [{"column": "n", "op": "eq", "value": "1"}], [row()]), "violation")
    case("complete-query-omits-row", query([row()], [], []), "violation")
    partial = query([row()], [], []);partial["events"][2]["complete"] = False
    case("partial-query", partial, "inconclusive")
    case("unknown-read-version", query([row()], [], [row(version="unknown")]), "inconclusive")
    for name, mutate in [("snapshot-inconsistent", lambda t: t["events"][0].update(consistent=False)),
                         ("exclusive-writers-unproven", lambda t: t["scope"].update(exclusiveWriters=False)),
                         ("snapshot-coverage-omitted", lambda t: t["scope"].update(completeSnapshotTables=[]))]:
        t = query([row()], []);mutate(t);case(name, t, "inconclusive")
    t = query([row()], []);del t["events"][0]["initial"]["r"];case("initial-table-missing", t, "invalid")
    t = Trace([row(), row()]);case("duplicate-initial-key", t.t, "invalid")
    t = query([row()], []);t["events"][0]["initial"]["r"][0]["values"]["id"]="0";case("primary-key-repeated-in-values", t, "invalid")
    t = Trace();t.begin();t.write("0", "insert", "v1", None, row()["values"]);t.read([row(version="v1")]);t.commit();case("insert-initial-absence", t.t, "consistent")
    t = Trace([row()]);t.begin();t.write("0", "insert", "v1", None, row()["values"]);t.commit();case("insert-over-live-row", t.t, "violation")
    t = Trace([row()]);t.begin();t.write("0", "update", "v1", "missing", row()["values"]);t.commit();case("unknown-write-predecessor", t.t, "inconclusive")
    t = Trace([row()]);t.begin();t.write("1", "update", "v1", "v0", row()["values"]);t.commit();case("wrong-key-write-predecessor", t.t, "violation")
    t = Trace([row()]);t.begin();t.write("0", "delete", "d1", "v0", None);t.read([]);t.commit();case("delete-tombstone-not-live", t.t, "consistent")
    for name, predecessor, expected in [("delete-reinsert", "d1", "consistent"), ("delete-reinsert-null-source", None, "violation")]:
        t = Trace([row()]);t.begin();t.write("0", "delete", "d1", "v0", None);t.write("0", "insert", "v1", predecessor, row()["values"]);t.read([row(version="v1")]);t.commit();case(name,t.t,expected)
    t = Trace([row()]);t.begin();t.write("0", "delete", "d1", "v0", None);t.write("0", "update", "v1", "d1", row()["values"]);t.commit();case("update-tombstone",t.t,"violation")
    t = Trace([row()]);t.begin("W");t.write("0","delete","d1","v0",None,tx="W");t.commit("W");t.begin();t.read([row(version="d1")]);t.commit();case("read-known-tombstone",t.t,"violation")
    t = Trace([row()]);t.begin();t.write("0","update","v1","v0",row()["values"]);t.write("0","update","v2","v1",row()["values"]);t.read([row(version="v2")]);t.commit();case("same-value-distinct-versions",t.t,"consistent")
    t = Trace([row()]);t.begin();t.write("0","update","v1","v0",row()["values"]);t.write("0","update","v1","v1",row()["values"]);t.commit();case("duplicate-produced-version",t.t,"invalid")
    t = Trace([row()]);t.begin("W");t.write("0","update","v1","v0",row()["values"],tx="W");t.abort("W");t.begin();t.read([row(version="v1")]);t.commit();case("read-aborted-source",t.t,"violation")
    t = Trace([row()]);t.begin();t.read([row(n="1")]);t.abort();case("aborted-read-no-opacity",t.t,"consistent")
    t = Trace([row()]);t.begin();t.read([row(version="missing")]);t.abort();case("aborted-unknown-source-still-gap",t.t,"inconclusive")
    t = Trace([row()]);t.begin();t.e("savepoint",tx="T",name="s",instance="s1");t.write("0","update","v1","v0",row()["values"]);t.read([row(version="v1")]);t.e("rollback_to",tx="T",instance="s1");t.read([row()]);t.commit();case("own-read-before-later-rollback",t.t,"consistent")
    t = Trace([row()]);t.begin();t.e("savepoint",tx="T",name="s",instance="s1");t.write("0","update","v1","v0",row()["values"]);t.e("rollback_to",tx="T",instance="s1");t.read([row(version="v1")]);t.commit();case("own-read-after-source-revoked",t.t,"violation")
    t = Trace([row()]);t.begin();t.e("savepoint",tx="T",name="s",instance="s1");t.e("savepoint",tx="T",name="s",instance="s2");t.e("rollback_to",tx="T",instance="s1");t.commit();case("hidden-older-same-name-mark",t.t,"invalid")
    t = Trace([row()]);t.begin();t.e("savepoint",tx="T",name="s",instance="s1");t.e("savepoint",tx="T",name="s",instance="s2");t.e("release",tx="T",instance="s2");t.e("rollback_to",tx="T",instance="s1");t.read([row()]);t.commit();case("release-reveals-older-same-name",t.t,"consistent")
    t = Trace([row()]);t.begin();t.e("savepoint",tx="T",name="a",instance="a");t.e("savepoint",tx="T",name="b",instance="b");t.write("0","delete","d1","v0",None);t.e("release",tx="T",instance="b");t.e("rollback_to",tx="T",instance="a");t.read([row()]);t.commit();case("parent-rollback-restores-released-child-tombstone",t.t,"consistent")
    t = Trace([row()]);t.begin();t.e("commit_request",tx="T");case("unknown-commit",t.t,"inconclusive")
    t = Trace([row()]);t.begin();request=t.e("commit_request",tx="T");t.e("rollback_ok",tx="T");case("idle-rollback-after-request-unknown",t.t,"inconclusive")
    t = Trace([row()]);t.begin();request=t.e("commit_request",tx="T");t.e("rollback_ok",tx="T",commitResponse={"request":request,"commandTag":"ROLLBACK"});case("server-rollback-response",t.t,"consistent")
    t = Trace([row()]);t.begin();t.e("statement",tx="T",sql="SELECT * FROM r");t.e("rows",tx="T",statement=3,rows=[],complete=True);t.commit();case("raw-sql-unmapped",t.t,"inconclusive")
    t = Trace();t.begin();t.e("append",tx="T",key="x",id="item",value="v");t.commit();case("mixed-list-event",t.t,"invalid")
    t = query([row()], [{"column":"n","op":"eq","value":"0"}]);
    for budget,expected in [(7,"inconclusive"),(8,"consistent"),(9,"consistent")]:case("read-exact-check-budget-"+str(budget),t,expected,{"maxOperationChecks":budget})
    case("read-zero-state-budget",t,"inconclusive",{"maxStates":0})
    t = Trace();t.begin();t.commit();case("empty-transaction-zero-checks",t.t,"consistent",{"maxOperationChecks":0,"maxStates":1})
    case("empty-history-zero-budgets",Trace().t,"consistent",{"maxStates":0,"maxOperationChecks":0})
    case("direct-source-proof-zero-search-budgets",query([row()],[],[row(n="1")]),"violation",{"maxStates":0,"maxOperationChecks":0})
    t = Trace();t.begin();t.e("savepoint",tx="T",name="s",instance="s");t.read([]);t.e("rollback_to",tx="T",instance="s");t.e("release",tx="T",instance="s");t.commit()
    for budget,expected in [(4,"inconclusive"),(5,"consistent")]:case("scope-actions-budget-"+str(budget),t.t,expected,{"maxOperationChecks":budget})
    t = Trace()
    for i in range(7):t.begin(str(i));t.commit(str(i))
    case("seven-committed-capacity",t.t,"inconclusive")
    for count,expected in [(128,"consistent"),(129,"inconclusive")]:
        t = Trace();t.begin()
        for _ in range(count):t.read([])
        t.abort();case("aborted-ops-exact-capacity-"+str(count),t.t,expected)
    # Supplements follow root's explicit null-predecessor/finalWrites rulings.
    # The original first 151 boundary inputs and their expectations remain intact.
    for action in ["update","delete"]:
        t=Trace([row()]);t.begin();t.write("0",action,"v1",None,None if action=="delete" else row()["values"]);t.commit()
        case("supplement-"+action+"-null-predecessor-invalid",t.t,"invalid")
    t=Trace([row()]);t.begin();t.write("0","update","v1","v0",row()["values"]);t.write("0","delete","d1","v1",None);t.commit();case("supplement-final-write-is-tombstone",t.t,"consistent")
    schemas={"r":{"primaryKey":"id","columns":{"id":"int64","n":"int64","b":"bool","t":"text"}},"s":{"primaryKey":"id","columns":{"id":"text","n":"int64","b":"bool","t":"text"}}}
    t=Trace([row()],relations=schemas);t.t["events"][0]["initial"]["s"]=[row(version="s0")];t.begin();t.write("0","update","r1","v0",row()["values"]);t.write("0","update","s1","s0",row()["values"],relation="s");t.write("0","update","r2","r1",row()["values"]);t.commit();case("supplement-final-writes-structured-relation-type-key",t.t,"consistent")
    t=Trace([row()],relations=schemas);t.t["events"][0]["initial"]["s"]=[row(version="s0")];t.begin();t.read([row(version="s0")]);t.commit();case("supplement-known-source-wrong-relation",t.t,"violation")
    t=Trace([row()],relations=schemas);t.t["events"][0]["initial"]["s"]=[row(version="s0")];t.begin();t.write("0","update","r1","s0",row()["values"]);t.commit();case("supplement-known-predecessor-wrong-relation",t.t,"violation")
    t=Trace([row()]);t.begin();t.read([row(version="future")]);t.begin("W");t.write("0","update","future","v0",row()["values"],tx="W");t.commit("W");t.commit();case("supplement-later-read-source-does-not-repair-gap",t.t,"inconclusive")
    t=Trace([row()]);t.begin();t.write("0","update","v2","future",row()["values"]);t.begin("W");t.write("0","update","future","v0",row()["values"],tx="W");t.commit("W");t.commit();case("supplement-later-predecessor-source-does-not-repair-gap",t.t,"inconclusive")
    t=Trace([row()]);t.begin("W");t.write("0","update","v1","v0",row()["values"],tx="W");t.write("0","update","v2","v1",row()["values"],tx="W");t.commit("W");t.begin();t.read([row(version="v1")]);t.commit();case("supplement-external-intermediate-source-not-final-state",t.t,"violation")
    t=Trace([row()]);t.begin();t.write("0","update","v1","v0",row()["values"]);t.read([row()]);t.commit();case("supplement-own-state-not-restored-by-reading-old-source",t.t,"violation")
    t=Trace([row()]);t.begin();t.e("savepoint",tx="T",name="s",instance="s1");t.e("release",tx="T",instance="s1");t.e("savepoint",tx="T",name="s",instance="s1");t.commit();case("supplement-savepoint-instance-cannot-be-reused",t.t,"invalid")
    t=query([row(b=0)],[]);case("supplement-boolean-number-not-coerced",t,"invalid")
    for count,expected in [(8,"consistent"),(9,"invalid")]:
        rs={"r%d"%i:{"primaryKey":"id","columns":{"id":"text"}} for i in range(count)}
        case("supplement-relation-count-"+str(count),Trace(relations=rs).t,expected)
    for count,expected in [(16,"consistent"),(17,"invalid")]:
        rs={"r":{"primaryKey":"id","columns":{"id":"int64",**{"c%d"%i:"text" for i in range(count-1)}}}}
        case("supplement-column-count-"+str(count),Trace(relations=rs).t,expected)
    for width,expected in [(63,"consistent"),(64,"invalid")]:
        rs={"r"*width:{"primaryKey":"id","columns":{"id":"int64"}}}
        case("supplement-ascii-relation-name-width-"+str(width),Trace(relations=rs).t,expected)
    rs={"r":{"primaryKey":"id","columns":{"id":"bool"}}};case("supplement-bool-primary-key-invalid",Trace(relations=rs).t,"invalid")
    boundary_count = len(records)

    # One thousand unique histories vary relations, row-set sizes, predicates,
    # thresholds, scope programs and write counts, not merely identity strings.
    for i in range(1000):
        size, threshold = i % 7, i * 100003 - 50000000
        initial = [row(str(j), "g%d-v%d" % (i,j), str(threshold+j), b=j%2==0, t=texts[(i+j)%len(texts)]) for j in range(size)]
        pattern = i % 5
        t = Trace(initial)
        t.begin()
        if pattern == 0:
            predicate=[{"column":"n","op":"ge","value":str(threshold+i%4)}]
            actual=[r for r in initial if int(r["values"]["n"])>=threshold+i%4]
            t.read(actual,predicate);expected="consistent"
        elif pattern == 1:
            # Contradictory AND remains a complete valid empty query.
            t.read([], [{"column":"n","op":"gt","value":str(threshold+size+1)},{"column":"n","op":"lt","value":str(threshold-1)}]);expected="consistent"
        elif pattern == 2:
            # Each transaction reads the complete matching set before either
            # inserts a new matching row; every serial order has a phantom.
            predicate=[{"column":"n","op":"ge","value":str(threshold)}]
            t.read(initial,predicate);t.begin("U");t.read(initial,predicate,tx="U")
            t.write(str(size+1),"insert","g%d-a"%i,None,row(n=str(threshold+1))["values"])
            t.commit();t.write(str(size+2),"insert","g%d-b"%i,None,row(n=str(threshold+2))["values"],tx="U");t.commit("U");expected="violation"
        elif pattern == 3:
            t.read([row(str(size+10),"g%d-missing"%i,str(threshold))]);expected="inconclusive"
        else:
            t.e("savepoint",tx="T",name="s",instance="s%d"%i)
            new=row(str(size+10),"g%d-own"%i,str(threshold))
            t.write(new["key"],"insert",new["version"],None,new["values"])
            t.read(initial+[new]);t.e("rollback_to",tx="T",instance="s%d"%i);t.read(initial);expected="consistent"
        if pattern != 2:t.commit()
        case("generated-%04d"%i,t.t,expected)
    assert len({r["inputSha256"] for r in records[boundary_count:]}) == 1000
    differences=[];counts={};normalizations=[]
    for r in records:
        actual=analyze(r["traceText"],r["options"])
        counts[actual["status"]]=counts.get(actual["status"],0)+1
        if actual["status"] != r["expected"]:differences.append({"id":r["id"],"expected":r["expected"],"actual":actual})
        normalizations.append({"id":r["id"],"inputSha256":r["inputSha256"],"analysisStatus":actual["status"],"normalization":actual.get("normalization"),"invalidNormalizationExpected":actual["status"]=="invalid"})
        if actual.get("normalization") and r["id"] in {"same-value-distinct-versions","supplement-final-write-is-tombstone","supplement-final-writes-structured-relation-type-key"}:
            wanted={"same-value-distinct-versions":[4],"supplement-final-write-is-tombstone":[4],"supplement-final-writes-structured-relation-type-key":[4,5]}[r["id"]]
            if actual["normalization"]["transactions"][0]["finalWrites"]!=wanted:differences.append({"id":r["id"],"metadata":"hand-audited finalWrites mismatch","wanted":wanted,"actual":actual["normalization"]["transactions"][0]["finalWrites"]})
    files={}
    for name,data in [("boundary.json",records[:boundary_count]),("generated-1000.json",records[boundary_count:]),("normalization-oracle.json",normalizations)]:
        raw=(json.dumps(data,ensure_ascii=True,separators=(",",":"))+"\n").encode();(OUT/name).write_bytes(raw);files[name]={"sha256":hash_bytes(raw),"bytes":len(raw),"cases":len(data)}
    manifest={"schema":1,"status":"provisional independent draft, not production acceptance","createdAt":datetime.now(timezone.utc).isoformat(),"files":files,
              "boundaryCount":boundary_count,"generatedCount":1000,"generatedUniqueInputSha256Count":1000,"oracleSha256":hash_bytes((HERE/'relation_oracle.py').read_bytes()),"generatorSha256":hash_bytes(Path(__file__).read_bytes()),
              "normalizationComparison":{"fields":["schema","dataModel","algorithm","status","relationSchema","observations","effects","transactions","history"],"coverageComplete":True,"diagnosticMessages":"Reference gap messages are descriptive independent diagnostics; do not silently ignore unexplained primary coverage differences."},
              "expectedFrozenBeforeAnyProductionRun":True,"productionImports":False,"actualDatabaseExecution":False,"draftAssumptions":["Every declared relation explicitly appears in initial snapshot; any incomplete table prevents complete result.","Unknown read/write predecessor sources remain permanent gaps; source-proven findings follow capacity/coverage checks and consume no search budget.","Only committed complete scope journals are serialized; all-trace row operations count for exact capacity.","No initial tombstone representation; preceding-window delete tokens remain missing sources.","Version IDs use Unicode scalars up to 256 UTF16 units; relation/column names ASCII and text values allow empty/NUL."],
              "independentSelfcheck":{"passed":not differences,"cases":len(records),"statusCounts":counts,"differences":differences}}
    previous=HERE/'frozen-draft-3d635bfba99a4dbda268f97dd02853b9'
    if previous.exists():
        old=json.loads((previous/'boundary.json').read_bytes());old_generated=json.loads((previous/'generated-1000.json').read_bytes())
        assert records[:len(old)]==old and records[boundary_count:]==old_generated
        manifest['preservedPriorDraft']={'manifestSha256':hash_bytes((previous/'manifest.json').read_bytes()),'original151BoundaryBytesAndExpectationsUnchanged':True,'original1000GeneratedBytesAndExpectationsUnchanged':True}
    for name in ['relation_oracle.py','freeze_inputs.py']:(OUT/name).write_bytes((HERE/name).read_bytes())
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=True,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({"directory":OUT.as_posix(),"boundary":boundary_count,"generated":1000,"selfcheckPassed":not differences,"differences":differences,"manifestSha256":hash_bytes((OUT/'manifest.json').read_bytes())}))
    return 0 if not differences else 1


if __name__=='__main__':raise SystemExit(freeze())
