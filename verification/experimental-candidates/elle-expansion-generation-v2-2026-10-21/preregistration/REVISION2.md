The original v1 source-only index and generator are preserved. No original
generated dataset exists: neither revision has run. This revision fixes the two
static input-gate/allocation findings and keeps the same deterministic generation
algorithm, seed and family quotas.

Generation now requires the exact bytes of the third actual comparison receipt
from run39599513353 and explicitly requires its fixed b663 SDK source. That run
has six determinate agreements and two expected empty-graph coverage differences.
The current mainline is outside that statement. D's independent review is still
an external gate; hashing a receipt does not replace it. Do not generate before
root confirms that gate.

The smoke file is bounded before allocation and after the read. Dataset SHA is
streamed with a strict32MiB bound. All original raw-generation/dedup rules remain
unchanged. Static source authoring only: no generator, checker, SDK, Node, JVM,
compiler, database or performance process was executed for this revision.
