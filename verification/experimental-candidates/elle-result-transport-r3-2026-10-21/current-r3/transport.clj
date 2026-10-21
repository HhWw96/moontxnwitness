;; Preserve returned upstream evidence before attempting its JSON summary.
;; The caller owns path admission and outer process/output budgets.
(defn execute-retained-result [prepare-checker raw-file exception-file identity]
  (let [state (atom {:attempted false :returned false :retained false})]
    (try
      (let [invoke (prepare-checker)]
        (swap! state assoc :attempted true)
        (let [result (invoke)]
          (swap! state assoc :returned true)
          (spit raw-file (str (pr-str result) "\n"))
          (swap! state assoc :retained true)
          (merge identity (summarize-elle-result result)
                 {"actualElleInvocationAttempted" true "actualElleResultReturned" true
                  "rawResultRetained" true "rawResultFile" (.getName raw-file)})))
      (catch Throwable error
        (let [observed @state
              exception-retained (try
                                   (spit exception-file
                                         (str (pr-str {:class (.getName (class error))
                                                       :message (.getMessage error)}) "\n"))
                                   true
                                   (catch Throwable storage-error false))
              stage (cond (not (:attempted observed)) "preparation"
                          (not (:returned observed)) "checker"
                          (not (:retained observed)) "result-retention"
                          :else "result-transport")]
          (merge identity
                 {"valid" "execution-error" "failureStage" stage
                  "actualElleInvocationAttempted" (:attempted observed)
                  "actualElleResultReturned" (:returned observed)
                  "rawResultRetained" (:retained observed)
                  "rawResultFile" (when (:retained observed) (.getName raw-file))
                  "exceptionRecordRetained" exception-retained
                  "errorClass" (.getName (class error)) "errorMessage" (.getMessage error)}))))))
