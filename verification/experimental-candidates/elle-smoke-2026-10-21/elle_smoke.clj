(require '[clojure.edn :as edn]
         '[clojure.java.io :as io]
         '[clojure.string :as str]
         '[elle.rw-register :as register]
         '[elle.list-append :as append-list]
         '[elle.txn :as txn]
         '[jepsen.history :as history])

(def options {:consistency-models [:serializable]
              :additional-graphs [] :linearizable-keys? false
              :sequential-keys? false :wfr-keys? false
              :directory nil :cycle-search-timeout 10000})

(defn json-text [v]
  (cond (nil? v) "null" (true? v) "true" (false? v) "false"
        (string? v) (pr-str v) (number? v) (str v)
        (sequential? v) (str "[" (str/join "," (map json-text v)) "]")
        (map? v) (str "{" (str/join "," (map (fn [[k x]] (str (json-text k) ":" (json-text x))) v)) "}")
        :else (throw (ex-info "Unsupported output transport" {}))))

(defn op [input]
  {:index (get input "index") :process (get input "process")
   :type (keyword (get input "type")) :f :txn
   :value (mapv (fn [[f k v]] [(keyword f) k v]) (get input "value"))})

(defn file-sha256 [file]
  (let [path (.toPath (io/file file))]
    (when (> (java.nio.file.Files/size path) (* 8 1024 1024))
      (throw (ex-info "Bounded EDN input required" {})))
    (let [digest (.digest (java.security.MessageDigest/getInstance "SHA-256")
                          (java.nio.file.Files/readAllBytes path))]
      (apply str (map #(format "%02x" (bit-and 0xff %)) digest)))))

(let [[input-path output-path raw-directory] *command-line-args*
      output (io/file output-path) raw-root (io/file raw-directory)
      input-hash (file-sha256 input-path)]
  (when-not (= "21" (System/getProperty "java.specification.version"))
    (throw (ex-info "JDK21 required" {})))
  (when-not (= "1.12.6" (clojure-version))
    (throw (ex-info "Pinned Clojure1.12.6 required" {})))
  (when (seq (txn/additional-graphs options))
    (throw (ex-info "Unexpected automatic process/realtime graph" {})))
  (when (.exists output) (throw (ex-info "Refuse old execution output" {})))
  (when (.exists raw-root) (throw (ex-info "Refuse old raw output directory" {})))
  (.mkdirs raw-root)
  (let [results
        (with-open [reader (io/reader input-path)]
          (mapv
            (fn [line]
              (let [request (edn/read-string {:readers {}} line)
                    id (get request "id")]
                (when-not (and (string? id) (re-matches #"[a-zA-Z0-9_-]{1,128}" id))
                  (throw (ex-info "Unsafe case identifier" {})))
                (try
                 (let [
                    h (history/history (mapv op (get request "operations")))
                    checker (case (get request "model")
                              "point-register-v1" register/check
                              "append-list-v1" append-list/check)
                    result (checker options h)
                    valid (if (= :unknown (:valid? result)) "unknown" (:valid? result))
                    raw-file (io/file raw-root (str id ".edn"))
                    anomalies (mapv name (:anomaly-types result))]
                (spit raw-file (str (pr-str result) "\n"))
                {"id" id "valid" valid "anomalyTypes" anomalies
                 "passed" (and (= valid (get request "expectedElleValid"))
                               (not (some #{"cycle-search-timeout"} anomalies)))
                 "rawResultFile" (.getName raw-file)
                 "actualElleExecuted" true
                 "java" (System/getProperty "java.version")
                 "clojure" (clojure-version)})
                 (catch Throwable error
                   (spit (io/file raw-root (str id ".exception.edn"))
                         (str (pr-str {:class (.getName (class error))
                                       :message (.getMessage error)}) "\n"))
                   {"id" id "passed" false "valid" "execution-error"
                    "actualElleInvocationAttempted" true "actualElleResultReturned" false
                    "errorClass" (.getName (class error)) "errorMessage" (.getMessage error)}))))
            (line-seq reader)))]
    (when-not (= input-hash (file-sha256 input-path))
      (throw (ex-info "Actual checker input changed during execution" {})))
    (spit output (str (json-text {"schema" 1 "passed" (every? #(get % "passed") results)
                                  "fixedElleCommit" "4e359e597c52938b0afebb8bc42273914d68a424"
                                  "inputEdnSha256" input-hash
                                  "automaticAdditionalGraphCount" 0 "cases" results}) "\n"))
    (shutdown-agents)
    (when-not (every? #(get % "passed") results) (System/exit 1))))
