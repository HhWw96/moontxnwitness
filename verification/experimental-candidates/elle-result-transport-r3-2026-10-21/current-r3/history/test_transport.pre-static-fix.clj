(require '[clojure.test :refer [deftest is run-tests]] '[clojure.edn :as edn])
(load-file (first *command-line-args*))
(load-file (second *command-line-args*))
(def test-root (java.io.File. (nth *command-line-args* 2)))
(when-not (.mkdir test-root) (throw (ex-info "Fresh owned test root required" {})))
(defn paths [name]
  [(java.io.File. test-root (str name ".edn"))
   (java.io.File. test-root (str name ".exception.edn"))])
(def identity-fields {"id" "fixed-raw-input" "inputSha256" "unchanged"})

(deftest returned-false-plus-timeout-persists-before-summary
  (let [[raw exception] (paths "false-timeout")
        original {:valid? false :anomaly-types [:PL-SI-cycle-exists :cycle-search-timeout]}
        output (execute-retained-result (fn [] (fn [] original)) raw exception identity-fields)]
    (is (= original (edn/read-string (slurp raw))))
    (is (false? (get output "valid")))
    (is (true? (get output "cycleSearchTimeout")))
    (is (true? (get output "actualElleResultReturned")))
    (is (true? (get output "rawResultRetained")))))

(deftest summary-error-keeps-original-returned-evidence
  (let [[raw exception] (paths "summary-error")
        original {:valid? false :anomaly-types [:G2-item]}
        problem (ex-info "summary refused" {})
        output (with-redefs [summarize-elle-result (fn [_] (throw problem))]
                 (execute-retained-result (fn [] (fn [] original)) raw exception identity-fields))]
    (is (= original (edn/read-string (slurp raw))))
    (is (= "execution-error" (get output "valid")))
    (is (= "result-transport" (get output "failureStage")))
    (is (true? (get output "actualElleResultReturned")))
    (is (true? (get output "rawResultRetained")))
    (is (= identity-fields (select-keys output ["id" "inputSha256"])))
    (is (= "summary refused" (:message (edn/read-string (slurp exception)))))))

(deftest preparation-failure-does-not-claim-checker-invocation
  (let [[raw exception] (paths "prepare-error")
        output (execute-retained-result (fn [] (throw (ex-info "bad history" {}))) raw exception identity-fields)]
    (is (= "preparation" (get output "failureStage")))
    (is (false? (get output "actualElleInvocationAttempted")))
    (is (false? (get output "actualElleResultReturned")))
    (is (not (.exists raw)))))

(deftest checker-failure-is-distinct-from-never-invoked
  (let [[raw exception] (paths "checker-error")
        output (execute-retained-result (fn [] (fn [] (throw (ex-info "checker stopped" {})))) raw exception identity-fields)]
    (is (= "checker" (get output "failureStage")))
    (is (true? (get output "actualElleInvocationAttempted")))
    (is (false? (get output "actualElleResultReturned")))
    (is (true? (get output "exceptionRecordRetained")))))

(deftest raw-storage-failure-keeps-returned-state-without-claiming-retention
  (let [[_ exception] (paths "raw-storage-error")
        raw (java.io.File. test-root "absent-parent/raw.edn")
        output (execute-retained-result (fn [] (fn [] {:valid? false})) raw exception identity-fields)]
    (is (= "result-retention" (get output "failureStage")))
    (is (true? (get output "actualElleResultReturned")))
    (is (false? (get output "rawResultRetained")))
    (is (nil? (get output "rawResultFile")))))

(deftest secondary-exception-storage-failure-does-not-mask-primary
  (let [[raw _] (paths "exception-storage-error")
        exception (java.io.File. test-root "absent-parent/exception.edn")
        output (execute-retained-result (fn [] (fn [] (throw (ex-info "original checker error" {})))) raw exception identity-fields)]
    (is (= "checker" (get output "failureStage")))
    (is (= "original checker error" (get output "errorMessage")))
    (is (false? (get output "exceptionRecordRetained"))))))

(let [result (run-tests)]
  (println (pr-str {:kind :synthetic-checker-result-transport-tests :tests (:test result)
                   :assertions (+ (:pass result) (:fail result) (:error result))
                   :failures (:fail result) :errors (:error result)
                   :java (System/getProperty "java.version") :clojure (clojure-version)
                   :actual-elle-checker false}))
  (System/exit (if (zero? (+ (:fail result) (:error result))) 0 1)))
