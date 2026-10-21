This is an unexecuted expansion preregistration, separate from the small frozen
smoke. It does not contain actual checker outputs or a claim that 2000 inputs
have already been generated. It must not run before real smoke acceptance.

After the original fixed smoke and its independent review succeed, run only the
input-generation stage remotely:

```text
python -B <draft>/generate.py --smoke-comparison <accepted-smoke>/comparison-first.json --output <new-input-freeze>
```

The generator imports neither the adapter nor a checker. It writes 1000 raw
register and 1000 raw append histories, with ten fixed 200-input family quotas,
and no consistency truth fields. Only exact/alpha-program duplicates are skipped;
no model output can affect selection. Candidate exhaustion and partial files are
retained failures. Its fixed first-occurrence shape is explicitly not a claim of
full graph isomorphism uniqueness.

An independently authored streaming reader must first verify every canonical
input binding, common-range constraints and all unique shape hashes. Freeze that
input artifact and audit before an actual expansion evaluator runs. The current
small smoke main cannot be reused as a bulk wrapper: a separate reviewed batch
adapter/evaluator must preserve observations, unknowns and errors without
injecting generated truth labels. No such evaluator is implemented here.

No generator, Java, Clojure, Node, compiler, actual checker or database ran on the
local host for this draft. The contract and source are ready for read-only review;
actual generation, independent input freeze and every checker comparison remain
pending the real smoke gate.
