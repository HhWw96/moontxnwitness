;; Run the fixed upstream checkers; classification expectations live outside
;; this adapter. Full original upstream return values are retained separately.
(ns moontxnwitness.elle-model-matrix
  (:require [clojure.edn :as edn]
            [clojure.java.io :as io]
            [clojure.string :as str]
            [elle.core :as elle]
            [elle.graph :as g]
            [elle.rels :refer [ww]]
            [elle.rw-register :as register]
            [elle.list-append :as append]
            [jepsen.history :as h])
  (:import (java.security MessageDigest)
           (java.math BigInteger)
           (java.nio.file Files)))

(def fixed-commit "4e359e597c52938b0afebb8bc42273914d68a424")
(def supported-models
  #{:read-uncommitted :read-committed :repeatable-read :serializable
    :strict-serializable :snapshot-isolation :consistent-view
    :strong-session-read-uncommitted :strong-read-uncommitted
    :strong-session-read-committed :strong-read-committed
    :strong-session-serializable :strong-session-snapshot-isolation
    :strong-snapshot-isolation})

(defn sha256-file [path]
  (let [digest (MessageDigest/getInstance "SHA-256")]
    (.update digest (Files/readAllBytes (.toPath (io/file path))))
    (format "%064x" (BigInteger. 1 (.digest digest)))))

(defn json-string [s]
  (str "\""
       (apply str (map (fn [c]
                         (case c
                           \" "\\\"" \\ "\\\\" \newline "\\n" \return "\\r"
                           \tab "\\t" \backspace "\\b" \formfeed "\\f"
                           (if (< (int c) 32) (format "\\u%04x" (int c)) (str c))))
                       (str s)))
       "\""))

(declare json)
(defn json [x]
  (cond
    (nil? x) "null"
    (true? x) "true"
    (false? x) "false"
    (string? x) (json-string x)
    (keyword? x) (json-string (name x))
    (number? x) (str x)
    (map? x) (str "{" (str/join "," (map (fn [[k v]] (str (json (if (keyword? k) (name k) k)) ":" (json v))) x)) "}")
    (sequential? x) (str "[" (str/join "," (map json x)) "]")
    :else (throw (ex-info "Unsupported result-envelope JSON value" {:class (str (class x))}))))

(defrecord RawWWExplainer [sources]
  elle/DataExplainer
  (explain-pair-data [_ a b]
    (when-let [facts (get sources [(:index a) (:index b)])]
      (let [[_ _ _ ai bi] (first facts)]
        (cond-> {:type :ww :raw-source-references (mapv #(nth % 2) facts)
                 :source-kind :explicit-original-predecessor-facts}
          (some? ai) (assoc :a-mop-index ai)
          (some? bi) (assoc :b-mop-index bi)))))
  (render-explanation [_ data a-name b-name]
    (str a-name " precedes " b-name " by explicit original predecessor facts: "
         (pr-str (:raw-source-references data)))))

(defn explicit-ww-analyzer [facts]
  (fn [history]
    (let [ops (into {} (map (juxt :index identity) (h/oks history)))
          grouped (group-by #(subvec % 0 2) facts)]
      (doseq [[from to source ai bi :as fact] facts]
        (assert (and (vector? fact) (<= 3 (count fact) 5)
                     (integer? from) (integer? to) (not= from to)
                     (contains? ops from) (contains? ops to)
                     (string? source) (not (str/blank? source)))
                "A declared WW fact must bind two distinct confirmed completions and its original source")
        (doseq [[op-index mop-index] [[from ai] [to bi]]]
          (when (some? mop-index)
            (let [mops (:value (get ops op-index))]
              (assert (and (integer? mop-index) (<= 0 mop-index) (< mop-index (count mops))
                           (= :w (first (nth mops mop-index))))
                      "WW explanation micro-operation must identify an actual write")))))
      {:graph (reduce (fn [graph [from to]]
                        (g/link graph (get ops from) (get ops to) ww))
                      (g/op-digraph) (keys grouped))
       :explainer (->RawWWExplainer grouped)})))

(defn timeout-result? [raw]
  (boolean (some #{:cycle-search-timeout}
                 (tree-seq coll? seq raw))))

(defn run-one [root position request]
  (let [id (:id request)
        raw-name (format "raw/%04d.edn" position)
        raw-file (io/file root raw-name)]
    (io/make-parents raw-file)
    (try
      (assert (and (string? id) (not (str/blank? id))) "A nonempty request identity is required")
      (assert (contains? supported-models (:model request)) "Unsupported fixed model name")
      (assert (#{:register :list} (:data-model request)) "Unsupported upstream datatype")
      (assert (and (vector? (:history request)) (<= (count (:history request)) 4096)) "History must be a bounded vector")
      (let [extra (vec (or (:extra-ww request) []))
            _ (assert (or (= :register (:data-model request)) (empty? extra))
                      "Extra WW facts are a register-only explicit-source adapter")
            history (h/history (:history request))
            opts (cond-> {:consistency-models [(:model request)]
                          :cycle-search-timeout 5000
                          :linearizable-keys? false :sequential-keys? false :wfr-keys? false}
                   (seq extra) (assoc :additional-graphs [(explicit-ww-analyzer extra)]))
            checker (if (= :register (:data-model request)) register/check append/check)
            raw (checker opts history)
            validity (:valid? raw)
            result {:id id :model (name (:model request))
                    :dataModel (name (:data-model request))
                    :validity (when (boolean? validity) validity)
                    :unknown (not (boolean? validity))
                    :timeout (timeout-result? raw)
                    :anomalyTypes (vec (sort (map name (:anomaly-types raw))))
                    :rawResultFile raw-name
                    :explicitWWFacts (count extra)}]
        (spit raw-file (str (pr-str raw) "\n") :encoding "UTF-8")
        result)
      (catch Throwable error
        (spit raw-file (str (pr-str (Throwable->map error)) "\n") :encoding "UTF-8")
        {:id id :validity nil :unknown true :timeout false :anomalyTypes []
         :error {:class (.getName (class error)) :message (.getMessage error)}
         :rawResultFile raw-name}))))

(let [[input output & extra] *command-line-args*]
  (assert (and input output (empty? extra)) "Usage: upstream.clj REQUESTS.edn OUTPUT_DIR")
  (let [requests-sha256 (sha256-file input)
        requests (edn/read-string {:readers {} :default (fn [tag value] (throw (ex-info "Tagged request value is not supported" {:tag tag})))}
                                  (slurp input :encoding "UTF-8"))
        _ (assert (and (vector? requests) (pos? (count requests)) (<= (count requests) 2048)) "A bounded nonempty request vector is required")
        _ (assert (= (count requests) (count (set (map :id requests)))) "Request identities must be unique")
        result-file (io/file output "results.json")
        journal (io/file output "results.jsonl")
        _ (assert (and (not (.exists result-file)) (not (.exists journal))) "Original results must not be overwritten")
        rows (mapv (fn [i request]
                     (let [row (run-one output i request)]
                       (spit journal (str (json row) "\n") :append true :encoding "UTF-8")
                       (when (zero? (mod (inc i) 10)) (println (str "Completed actual upstream requests: " (inc i))))
                       row))
                   (range) requests)
        errors (count (filter :error rows))
        timeouts (count (filter :timeout rows))
        envelope {:format "moontxnwitness-actual-fixed-elle-model-results/v1"
                  :fixedElleCommit fixed-commit :passed (zero? errors)
                  :requestsSha256 requests-sha256
                  :requestCount (count requests) :executionErrors errors :timeouts timeouts
                  :scope "Actual fixed upstream execution; model comparison is performed separately"
                  :results rows}]
    (spit result-file (str (json envelope) "\n") :encoding "UTF-8")
    (shutdown-agents)
    (System/exit (if (zero? errors) 0 1))))
