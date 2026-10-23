# Internal validity and the frozen model identifiers

The root integration decision requires the existing PL3/strict graph definitions
to remain unchanged. INT is reported separately as an operational applicability
precondition. Generalized SI retains its original explicit INT requirement.

Graph refutation has priority: register/list write skew contains a G2-item cycle
and must keep its original PL3 `refuted` expectation. A broad intermediate edit
accidentally altered those two draft assertions; they will be restored to the
preserved original draft. Own-write visibility examples instead have an INT
counterexample without the corresponding transaction-interference graph cycle.
They must expose INT and failed applicability, while the unchanged graph
identifier is not silently extended with another forbidden phenomenon.

Both original draft assertions and the intermediate mistaken edit are saved
byte-for-byte beside this note, with SHA-256 in the decision JSON. No v026
compiler or test has yet executed, and no test failure is being removed. The
combined edit/check attempt was rejected by automatic review before execution;
the safer sequence documents the semantic decision before editing or running.
