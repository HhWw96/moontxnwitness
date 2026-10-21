(require '[clojure.edn :as edn]
         '[clojure.java.io :as io]
         '[clojure.string :as str]
         '[elle.rw-register :as register]
         '[elle.list-append :as append-list]
         '[elle.txn :as txn]
         '[jepsen.history :as history])

(load-file (str (io/file (.getParentFile (io/file *file*)) "result_summary.clj")))

(def options {:consistency-models [:serializable]
              :additional-graphs [] :linearizable-keys? false
              :sequential-keys? false :wfr-keys? false
              :directory nil :cycle-search-timeout 10000})

(defn json-text [value]
  (cond (nil? value) "null" (true? value) "true" (false? value) "false"
        (string? value) (pr-str value) (number? value) (str value)
        (sequential? value) (str "[" (str/join "," (map json-text value)) "]")
        (map? value) (str "{" (str/join "," (map (fn [[k v]] (str (json-text k) ":" (json-text v))) value)) "}")
        :else (throw (ex-info "Unsupported result transport" {}))))

(defn operation [input]
  {:index (get input "index") :process (get input "process")
   :type (keyword (get input "type")) :f :txn
   :value (mapv (fn [[f k v]] [(keyword f) k v]) (get input "value"))})

(defn execute-one [request raw-root]
  (let [id (get request "id")]
    (when-not (and (string? id) (re-matches #"[a-zA-Z0-9_-]{1,128}" id))
      (throw (ex-info "Unsafe original ID" {})))
    (try
      (let [h (history/history (mapv operation (get request "operations")))
            checker (case (get request "model") "point-register-v1" register/check "append-list-v1" append-list/check)
            result (checker options h)
            summary (summarize-elle-result result)
            raw-file (io/file raw-root (str id ".edn"))]
        (spit raw-file (str (pr-str result) "\n"))
        (merge summary
               {"id" id "inputSha256" (get request "inputSha256")
                "rawResultFile" (.getName raw-file) "actualElleInvocationAttempted" true
                "actualElleResultReturned" true}))
      (catch Throwable error
        (spit (io/file raw-root (str id ".exception.edn"))
              (str (pr-str {:class (.getName (class error)) :message (.getMessage error)}) "\n"))
        {"id" id "inputSha256" (get request "inputSha256") "valid" "execution-error"
         "actualElleInvocationAttempted" true "actualElleResultReturned" false
         "errorClass" (.getName (class error)) "errorMessage" (.getMessage error)}))))

(let [[input-path output-path raw-path] *command-line-args*
      input (io/file input-path) output (io/file output-path) raw-root (io/file raw-path)]
  (when-not (and (= "21" (System/getProperty "java.specification.version"))
                 (= "1.12.6" (clojure-version))
                 (empty? (txn/additional-graphs options)))
    (throw (ex-info "Fixed runtime and graph options required" {})))
  (when (or (> (.length input) 8388608) (.exists output) (.exists raw-root))
    (throw (ex-info "Fresh bounded batch required" {})))
  (.mkdirs raw-root)
  ;; Persist each first result before starting the next input. A process timeout
  ;; leaves a readable prefix; the outer collector must account for missing IDs
  ;; as actual timeout, execution failure or never invoked, according to retained
  ;; execution evidence. Keep every partial file and never retry an input.
  (with-open [reader (io/reader input) writer (io/writer output)]
    (loop [lines (line-seq reader) seen #{} processed 0]
      (when-let [line (first lines)]
        (when (or (>= processed 50) (> (count line) 1048576))
          (throw (ex-info "Batch cardinality/line budget" {})))
        (let [request (edn/read-string {:readers {}} line)
              id (get request "id")]
          (when (contains? seen id) (throw (ex-info "Duplicate original ID" {})))
          (.write writer (str (json-text (execute-one request raw-root)) "\n"))
          (.flush writer)
          (recur (rest lines) (conj seen id) (inc processed))))))
  (shutdown-agents))
