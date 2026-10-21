"""Compile reviewed fixed SQL from pinned producer AST, not observed journals."""
import ast
import argparse
import hashlib
import json
from pathlib import Path
import re

parser = argparse.ArgumentParser()
parser.add_argument("--producer-dir", type=Path, default=Path(__file__).parent / "producer-templates")
parser.add_argument("--check", action="store_true")
args = parser.parse_args()
PRODUCER = args.producer_dir
EXPECTED = {
    "relation_contract.py": "250b890cb631acb7370e69516c79d8dc4c23962b8a9bb01d7cb7609f8bd0abaa",
    "install.py": "f7d666f58a8ae1cf7b9061b0eb866bc40a08ff0b19796db76135ebcada7fa649",
}
trees = {}
for name, digest in EXPECTED.items():
    raw = (PRODUCER / name).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == digest, name
    trees[name] = ast.parse(raw.decode())
constants = {}
for node in trees["relation_contract.py"].body:
    if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
        name = node.targets[0].id
        if name in ("RELATION", "LOCKS", "COLUMNS", "CONSTRAINTS", "TRIGGERS", "INDEXES", "UNSAFE", "LOCALE"):
            constants[name.lower()] = node.value.value
prefixes = {
    "function_catalog": "SELECT n.nspname,p.proname,p.prosrc,",
    "trigger_catalog": "SELECT tgfoid,tgtype,tgenabled,",
    "function_oid": "SELECT p.oid FROM pg_proc",
    "trigger_oid": "SELECT oid FROM pg_trigger WHERE tgrelid=%s AND tgname=",
}
for name, prefix in prefixes.items():
    values = {node.value for node in ast.walk(trees["install.py"])
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith(prefix)}
    assert len(values) == 1, (name, values)
    constants[name] = values.pop()
out = ["///|", "/// Exact SQL constants compiled from pinned reviewed source, never from input hashes.",
    "fn orm2_sql(name : String) -> String raise {", "  match name {"]
for name, value in constants.items():
    out.append("    " + json.dumps(name) + " => " + json.dumps(value))
out += ['    _ => fail("Unknown fixed ORM control SQL")', "  }", "}", ""]
path = Path(__file__).parent / "orm_control_templates2.mbt"
if args.check:
    observed = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r'    ("(?:[^"\\]|\\.)*") => ("(?:[^"\\]|\\.)*")', line)
        if match:
            observed[json.loads(match[1])] = json.loads(match[2])
    assert observed == constants, "Static compiled SQL constants differ from the pinned producer AST"
else:
    path.write_text("\n".join(out), encoding="utf-8", newline="\n")
print(json.dumps({"inputBindings": EXPECTED, "templates": len(constants),
    "outputSha256": hashlib.sha256(path.read_bytes()).hexdigest(), "checkOnly": args.check}))
