"""Parse full wrapper forms with the real Clojure reader; do not evaluate them."""
from pathlib import Path
import hashlib,json,os,subprocess
HERE=Path(__file__).resolve().parent
def bind(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
before=bind((HERE/'elle_batch.clj').read_bytes())
code='''(require '[clojure.java.io :as io])
(with-open [r (java.io.PushbackReader. (io/reader (first *command-line-args*))) ]
  (loop [n 0]
    (let [form (read {:eof ::eof} r)]
      (if (= ::eof form)
        (println (pr-str {:forms n :evaluated false :actual-elle-checker false}))
        (recur (inc n))))))'''
with (HERE/'read_wrapper_forms.clj').open('x',encoding='utf8') as stream:stream.write(code+'\n')
classpath=os.pathsep.join(str(p) for p in sorted((HERE/'runtime').glob('*.jar')))
command=['D:/Java/jdk-25/bin/java.exe','-Xms16m','-Xmx128m','-cp',classpath,'clojure.main',
         str(HERE/'read_wrapper_forms.clj'),str(HERE/'elle_batch.clj')]
env={key:value for key,value in os.environ.items() if key in ('PATH','SystemRoot','SYSTEMROOT','WINDIR','COMSPEC','PATHEXT')}
with (HERE/'reader-first.log').open('xb') as stream:
    result=subprocess.run(command,cwd=HERE,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=30)
after=bind((HERE/'elle_batch.clj').read_bytes())
receipt={'schema':1,'passed':result.returncode==0 and before==after,'exitCode':result.returncode,
         'sourceBefore':before,'sourceAfter':after,'wrapperFormsEvaluated':False,'actualElleCheckerExecuted':False,
         'actualFullWrapperCompiled':False,'formalPerformanceMeasured':False}
with (HERE/'reader-first-receipt.json').open('x',encoding='utf8') as stream:json.dump(receipt,stream,indent=2);stream.write('\n')
print(json.dumps(receipt))
raise SystemExit(0 if receipt['passed'] else 1)
