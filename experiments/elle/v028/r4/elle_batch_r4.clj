;; Derived from r3 only to add durable invocation-intent and retained-evidence ledger.
;; No anomaly/model rules, original histories, operation mapping or options changed.
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

(defn json-text [value]
  (cond (nil? value) "null" (true? value) "true" (false? value) "false"
        (string? value) (pr-str value) (number? value) (str value)
        (sequential? value) (str "[" (str/join "," (map json-text value)) "]")
        (map? value) (str "{" (str/join "," (map (fn [[k v]] (str (json-text k) ":" (json-text v))) value)) "}")
        :else (throw (ex-info "Unsupported result transport" {}))))

(defn sha-bytes [raw]
  (let [digest (.digest (java.security.MessageDigest/getInstance "SHA-256") raw)]
    (apply str (map #(format "%02x" (bit-and 255 %)) digest))))

(defn file-binding [file]
  (when (> (.length (io/file file)) 8388608)
    (throw (ex-info "Retained file budget exceeded" {})))
  (let [raw (java.nio.file.Files/readAllBytes (.toPath (io/file file)))]
    {"bytes" (count raw) "sha256" (sha-bytes raw)}))

(defn load-verified! [path digest]
  (let [file (io/file path)]
    (when (> (.length file) 1048576) (throw (ex-info "Source budget" {})))
    (let [raw (java.nio.file.Files/readAllBytes (.toPath file))]
      (when-not (= digest (sha-bytes raw)) (throw (ex-info "Source byte pin differs" {})))
      ;; Exactly the checked snapshot is evaluated; no source/bytecode file loader.
      (load-string (String. raw "UTF-8")))))

(defn sync-file! [file]
  (with-open [handle (java.io.RandomAccessFile. (io/file file) "rw")]
    (.sync (.getFD handle))))

(defn write-new! [file text]
  (when-not (.createNewFile (io/file file)) (throw (ex-info "Fresh result file required" {})))
  (with-open [out (java.io.FileOutputStream. (io/file file))]
    (.write out (.getBytes text "UTF-8"))
    (.flush out)
    (.sync (.getFD out))))

(defn operation [input]
  {:index (get input "index") :process (get input "process")
   :type (keyword (get input "type")) :f :txn
   :value (mapv (fn [[f k v]] [(keyword f) k v]) (get input "value"))})

(defn read-one [line]
  (with-open [reader (clojure.lang.LineNumberingPushbackReader. (java.io.StringReader. line))]
    (let [eof (Object.)
          value (edn/read {:readers {} :eof eof} reader)]
      (when (or (identical? eof value)
                (not (identical? eof (edn/read {:readers {} :eof eof} reader))))
        (throw (ex-info "Exactly one original EDN request required" {})))
      value)))

(declare execute-retained-result)

(let [[input-path summary-path raw-path ledger-path control-path summary-source summary-sha
       transport-source transport-sha run-id] *command-line-args*
      input (io/file input-path)
      summaries (io/file summary-path)
      raw-root (io/file raw-path)
      ledger (io/file ledger-path)
      control (edn/read-string (slurp control-path))
      sequence (atom 0)
      previous (atom (apply str (repeat 64 "0")))
      append! (fn [ordinal phase fields]
                (let [[id digest] (nth control ordinal)
                      body (merge {"sequence" (inc @sequence) "runId" run-id
                                   "ordinal" ordinal "id" id "inputSha256" digest
                                   "phase" phase} fields)
                      text (json-text body)
                      body-sha (sha-bytes (.getBytes text "UTF-8"))
                      line (str (json-text {"body" text "bodySha256" body-sha
                                            "previousSha256" @previous}) "\n")]
                  (with-open [out (java.io.FileOutputStream. ledger true)]
                    (.write out (.getBytes line "UTF-8"))
                    (.flush out)
                    (.sync (.getFD out)))
                  (reset! previous body-sha)
                  (swap! sequence inc)))]
  (when-not (and (= "21" (System/getProperty "java.specification.version"))
                 (= "1.12.6" (clojure-version))
                 (empty? (txn/additional-graphs options)))
    (throw (ex-info "Fixed runtime and graph options required" {})))
  (when-not (and (vector? control) (<= 1 (count control) 50)
                 (= (count control) (count (set (map first control))))
                 (every? (fn [[id digest]]
                           (and (string? id) (re-matches #"[a-zA-Z0-9_-]{1,128}" id)
                                (string? digest) (re-matches #"[a-f0-9]{64}" digest))) control)
                 (.isFile ledger) (zero? (.length ledger))
                 (.isDirectory raw-root) (.isDirectory summaries)
                 (zero? (count (.listFiles raw-root)))
                 (zero? (count (.listFiles summaries)))
                 (<= (.length input) 8388608))
    (throw (ex-info "Fresh bounded original batch and output required" {})))
  (load-verified! summary-source summary-sha)
  (load-verified! transport-source transport-sha)
  (with-open [reader (io/reader input)]
    (loop [lines (line-seq reader) ordinal 0]
      (if (< ordinal (count control))
        (let [[id digest] (nth control ordinal)
              request (try
                        (let [line (first lines)]
                          (when (or (nil? line) (> (count line) 1048576))
                            (throw (ex-info "Missing or oversized original request" {})))
                          (let [request (read-one line)]
                            (when-not (and (= id (get request "id"))
                                           (or (not (contains? request "inputSha256"))
                                               (= digest (get request "inputSha256"))))
                              (throw (ex-info "Original request identity differs" {})))
                            request))
                        (catch Throwable error
                          (append! ordinal "reader-error"
                                   {"errorClass" (.getName (class error))
                                    "errorMessage" (.getMessage error)})
                          (throw error)))
              raw-file (io/file raw-root (str id ".edn"))
              exception-file (io/file raw-root (str id ".exception.edn"))]
          (append! ordinal "preparing" {})
          (let [result
                (execute-retained-result
                  (fn []
                    (let [h (history/history (mapv operation (get request "operations")))
                          checker (case (get request "model")
                                    "point-register-v1" register/check
                                    "append-list-v1" append-list/check)]
                      (fn []
                        ;; This synced intent does not by itself prove entry/return.
                        (append! ordinal "invocation-intent" {})
                        (let [result (checker options h)]
                          (append! ordinal "returned" {})
                          result))))
                  raw-file exception-file {"id" id "inputSha256" digest})
                summary-file (io/file summaries (str id ".json"))]
            (when (.exists raw-file) (sync-file! raw-file))
            (when (.exists exception-file) (sync-file! exception-file))
            (write-new! summary-file (str (json-text result) "\n"))
            (append! ordinal "completed"
                     {"result" result "summary" (file-binding summary-file)
                      "raw" (when (.exists raw-file) (file-binding raw-file))})
            (recur (rest lines) (inc ordinal))))
        (when (seq lines)
          (throw (ex-info "Extra original batch inputs" {}))))))
  (shutdown-agents))
