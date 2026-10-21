from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
OLD=ROOT/'artifacts/elle-result-summary-r2'
def bind(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
helper=(OLD/'result_summary.clj').read_bytes()
assert bind(helper)['sha256']=='28cc491ea897d7191ea6305219abdd1009d53b822a79cfccbac3d79dfdf1709c'
with (HERE/'result_summary.clj').open('xb') as stream:stream.write(helper)
wrapper=(OLD/'elle_batch.clj').read_text()
line='(load-file (str (io/file (.getParentFile (io/file *file*)) "result_summary.clj")))'
assert line in wrapper
wrapper=wrapper.replace(line,line+'\n(load-file (str (io/file (.getParentFile (io/file *file*)) "transport.clj")))')
start=wrapper.index('(defn execute-one ')
end=wrapper.index('(let [[input-path',start)
replacement='''(defn execute-one [request raw-root]
  (let [id (get request "id")]
    (when-not (and (string? id) (re-matches #"[a-zA-Z0-9_-]{1,128}" id))
      (throw (ex-info "Unsafe original ID" {})))
    (execute-retained-result
      (fn []
        (let [h (history/history (mapv operation (get request "operations")))
              checker (case (get request "model") "point-register-v1" register/check "append-list-v1" append-list/check)]
          (fn [] (checker options h))))
      (io/file raw-root (str id ".edn"))
      (io/file raw-root (str id ".exception.edn"))
      {"id" id "inputSha256" (get request "inputSha256")})))

'''
wrapper=wrapper[:start]+replacement+wrapper[end:]
with (HERE/'elle_batch.clj').open('x',encoding='utf8') as stream:stream.write(wrapper)
def delimiters(path):
    text=path.read_text();stack=[];quoted=False;escaped=False;comment=False
    for offset,char in enumerate(text):
        if comment:
            if char=='\n':comment=False
            continue
        if quoted:
            if escaped:escaped=False
            elif char=='\\':escaped=True
            elif char=='"':quoted=False
            continue
        if char==';':comment=True
        elif char=='"':quoted=True
        elif char in '([{':stack.append((char,offset))
        elif char in ')]}':
            assert stack and '([{'.index(stack[-1][0])==')]}'.index(char),(path.name,offset,char,stack[-1:])
            stack.pop()
    assert not stack and not quoted,(path.name,stack)
for path in HERE.glob('*.clj'):delimiters(path)
files={path.name:bind(path.read_bytes()) for path in HERE.glob('*.clj')}
value={'schema':1,'candidate':'returned-result-preservation-r3','files':files,'plannedUnitTests':6,'plannedAssertions':27,
       'plannedJavaMajor':25,'clojure':'1.12.6','checkerInputs':'Explicitly synthetic callbacks; actual Elle classes never loaded',
       'actualTestsExecuted':False,'actualElleCheckerExecuted':False,'actualFullWrapperCompiled':False,'formalPerformanceMeasured':False}
with (HERE/'preregistered-before-tests.json').open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2);stream.write('\n')
print(json.dumps({'frozenFiles':len(files),'staticDelimiterCheck':True,'actualTestsExecuted':False}))
