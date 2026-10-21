(require '[clojure.test :refer [deftest is run-tests]])
(load-file (first *command-line-args*))
(when-not (= "1.12.6" (clojure-version))
  (throw (ex-info "Fixed pure-unit Clojure runtime required" {})))

(deftest proven-false-with-partial-timeout-is-preserved
  ;; This combination is present in the frozen upstream list-append tests.
  (is (= {"valid" false "originalValidity" {"kind" "boolean" "value" false}
          "anomalyTypes" ["PL-SI-cycle-exists" "cycle-search-timeout"]
          "cycleSearchTimeout" true}
         (summarize-elle-result {:valid? false :anomaly-types [:PL-SI-cycle-exists :cycle-search-timeout]}))))

(deftest boolean-with-timeout-remains-original
  (is (true? (get (summarize-elle-result {:valid? true :anomaly-types [:cycle-search-timeout]}) "valid")))
  (is (true? (get (summarize-elle-result {:valid? true :anomaly-types [:cycle-search-timeout]}) "cycleSearchTimeout"))))

(deftest unknown-and-timeout-are-independent
  (is (= "unknown" (get (summarize-elle-result {:valid? :unknown :anomaly-types [:cycle-search-timeout]}) "valid")))
  (is (= {"kind" "keyword" "value" "unknown"} (get (summarize-elle-result {:valid? :unknown}) "originalValidity")))
  (is (false? (get (summarize-elle-result {:valid? :unknown}) "cycleSearchTimeout"))))

(deftest ordinary-booleans-and-anomalies-retain-types-and-order
  (is (= {"valid" true "originalValidity" {"kind" "boolean" "value" true}
          "anomalyTypes" [] "cycleSearchTimeout" false} (summarize-elle-result {:valid? true})))
  (is (= ["G2-item" "G0"] (get (summarize-elle-result {:valid? false :anomaly-types [:G2-item :G0]}) "anomalyTypes"))))

(deftest malformed-or-missing-validity-never-becomes-a-pass
  (doseq [value [nil 0 1 "unknown" :false :timeout [] {}]]
    (is (= "execution-error" (get (summarize-elle-result {:valid? value :anomaly-types [:cycle-search-timeout]}) "valid")))))

(let [result (run-tests)]
  (println (pr-str {:kind :pure-result-transport-unit-tests :tests (:test result)
                   :assertions (+ (:pass result) (:fail result) (:error result))
                   :failures (:fail result) :errors (:error result)
                   :java (System/getProperty "java.version")
                   :clojure (clojure-version) :actual-elle-checker false}))
  (System/exit (if (zero? (+ (:fail result) (:error result))) 0 1)))
