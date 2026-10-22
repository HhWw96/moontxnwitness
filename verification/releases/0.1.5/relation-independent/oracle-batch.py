"""Independent invocation of the frozen relation interpreter; no database access."""
import importlib.util
import json
import sys
from pathlib import Path

source, inputs, output = map(Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location("relation_review_reference", source)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
rows = json.loads(inputs.read_text(encoding="utf-8"))
results = []
for row in rows:
    result = module.analyze(row["traceText"], row.get("options", {}))
    results.append({"id": row["id"], "expected": row["expected"],
                    "status": result["status"], "passed": result["status"] == row["expected"],
                    "result": result})
receipt = {"schema": 1, "kind": "frozen-independent-relation-interpreter-invocation",
           "inputs": len(rows), "passed": all(row["passed"] for row in results), "results": results}
output.write_text(json.dumps(receipt, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"passed": receipt["passed"], "inputs": len(rows)}))
sys.exit(0 if receipt["passed"] else 1)
