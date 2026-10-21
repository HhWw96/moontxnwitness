;; Result transport only. This does not compute a consistency verdict.
(defn summarize-elle-result [result]
  (let [original (:valid? result)
        anomalies (mapv name (:anomaly-types result))
        timeout? (boolean (some #{"cycle-search-timeout"} anomalies))
        original-typed (cond
                         (boolean? original) {"kind" "boolean" "value" original}
                         (keyword? original) {"kind" "keyword" "value" (subs (str original) 1)}
                         (nil? original) {"kind" "nil"}
                         :else {"kind" "unsupported" "type" (.getName (class original))})
        valid (cond (boolean? original) original
                    (= :unknown original) "unknown"
                    :else "execution-error")]
    {"valid" valid "originalValidity" original-typed
     "anomalyTypes" anomalies "cycleSearchTimeout" timeout?}))
