from pathlib import Path
import ast,hashlib,json
HERE=Path(__file__).resolve().parent
tree=ast.parse((HERE/'prepare.py').read_text())
function=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='delimiters')
namespace={};exec(compile(ast.Module(body=[function],type_ignores=[]),'retained-delimiter-check','exec'),namespace)
def bind(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
for path in HERE.glob('*.clj'):namespace['delimiters'](path)
files={path.relative_to(HERE).as_posix():bind(path.read_bytes()) for path in HERE.rglob('*') if path.is_file() and path.suffix in ('.clj','.json')}
value={'schema':1,'candidate':'returned-result-preservation-r3','files':files,'plannedUnitTests':6,'plannedAssertions':27,
       'plannedJavaMajor':25,'clojure':'1.12.6','checkerInputs':'Explicitly synthetic callbacks; actual Elle classes never loaded',
       'actualTestsExecuted':False,'actualElleCheckerExecuted':False,'actualFullWrapperCompiled':False,'formalPerformanceMeasured':False,
       'staticFailure':'One extra closing delimiter in draft test was corrected before source freeze; original draft retained under history'}
with (HERE/'preregistered-before-tests.json').open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2);stream.write('\n')
print(json.dumps({'frozenFiles':len(files),'staticDelimiterCheck':True,'actualTestsExecuted':False}))
