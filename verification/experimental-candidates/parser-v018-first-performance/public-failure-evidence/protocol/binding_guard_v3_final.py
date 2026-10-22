"""Source/core guards only. No runtime import, measurement, build, database or network."""
from pathlib import Path
import hashlib
import json
import re
SHA=lambda b:hashlib.sha256(b).hexdigest()
HEX=re.compile(r"^[a-f0-9]{64}$")
def verified(row,path):
    assert HEX.fullmatch(row["sha256"])
    raw=Path(path).read_bytes()
    assert len(raw)==row["bytes"] and SHA(raw)==row["sha256"],str(path)
    return raw
def within(root,name):
    base=Path(root).resolve();path=(base/name).resolve()
    assert path.is_relative_to(base) and path!=base,name
    return path
def stage_bound_engines(binding,output):
    assert binding["schema"]==1 and binding["kind"]=="root-actual17-actual18-core-source-binding"
    assert binding["baselineVersion"]=="0.1.7" and binding["currentVersion"]=="0.1.8"
    assert set(binding["engines"])=={"baseline","current"}
    assert binding["baselineReleasedByRoot"] is True
    publication=binding["baselinePublicationReceipt"]
    verified(publication,publication["path"])
    staged={}
    # Validate both complete source/core bindings before creating either module copy.
    for engine,version in [("baseline","0.1.7"),("current","0.1.8")]:
        row=binding["engines"][engine]
        assert row["version"]==version
        source=row["source"];mapping={x["file"]:x for x in source["files"]}
        assert len(mapping)==len(source["files"])
        assert {"moon.mod","package.json"}.issubset(mapping)
        for name,item in mapping.items():verified(item,within(source["root"],name))
        assert json.loads(within(source["root"],"package.json").read_bytes())["version"]==version
        inputs=sorted(["moon.mod"]+[name for name in mapping if name.startswith("src/") and (name.endswith(".mbt") or name.endswith("/moon.pkg"))])
        actual=sorted(p.relative_to(Path(source["root"])).as_posix() for p in (Path(source["root"])/"src").rglob("*") if p.is_file() and (p.suffix==".mbt" or p.name=="moon.pkg"))
        assert inputs==sorted(["moon.mod"]+actual),"Missing source inputs"
        digest=hashlib.sha256()
        for name in inputs:digest.update(name.encode()+b"\0");digest.update(within(source["root"],name).read_bytes());digest.update(b"\0")
        assert digest.hexdigest()==source["sourceFingerprint"]
        core=row["core"];raw=verified(core,core["path"])
        # Actual compiler output is self-contained. An unexpected new dependency
        # must be explicitly reviewed before extending this fixed protocol.
        text=raw.decode("utf-8")
        assert not re.search(r"(?m)^\s*import\b|^\s*export\b[^;\n]*\bfrom\s*['\"]|\bimport\s*\(",text),"Unbound core module dependency"
        build=row["buildManifest"];build_value=json.loads(verified(build,build["path"]))
        assert build_value["version"]==version
        assert build_value["sourceSha256"]==source["sourceFingerprint"]
        assert build_value["coreSha256"]==core["sha256"]
        staged[engine]={"version":version,"file":core["path"],"bytes":core["bytes"],"sha256":core["sha256"],"sourceFingerprint":source["sourceFingerprint"],"sourceFiles":source["files"],"sourceRoot":source["root"],"buildManifest":build,"build":build_value,"raw":raw}
    for engine,row in staged.items():
        target=Path(output)/(engine+".mjs")
        target.write_bytes(row.pop("raw"))
        assert SHA(target.read_bytes())==row["sha256"]
        row["copy"]=str(target)
    return staged
