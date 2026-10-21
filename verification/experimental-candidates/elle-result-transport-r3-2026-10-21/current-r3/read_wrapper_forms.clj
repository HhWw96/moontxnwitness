(require '[clojure.java.io :as io])
(with-open [r (java.io.PushbackReader. (io/reader (first *command-line-args*))) ]
  (loop [n 0]
    (let [form (read {:eof ::eof} r)]
      (if (= ::eof form)
        (println (pr-str {:forms n :evaluated false :actual-elle-checker false}))
        (recur (inc n))))))
