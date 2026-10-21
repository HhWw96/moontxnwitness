"""Executable bounded location/intent contract; not evidence acquisition."""
import hashlib
import json
import re
from pathlib import Path


class ProtocolError(ValueError): pass


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def digest(value): return hashlib.sha256(value).hexdigest()


def binding(path):
    hashed, size = hashlib.sha256(), 0
    with Path(path).open("rb") as file:
        while block := file.read(65536): hashed.update(block); size += len(block)
    return {"sha256": hashed.hexdigest(), "bytes": size}


def checked(condition, message):
    if not condition: raise ProtocolError(message)


def sha(value):return type(value) is str and re.fullmatch("[a-f0-9]{64}",value)


def root_label(value):
    return type(value) is str and 0<len(value)<=256 and all(not 0xD800<=ord(c)<=0xDFFF for c in value) and len(value.encode("utf-16-le"))<=512


def intent_shape(intent):
    checked(type(intent) is dict and set(intent)=={"schema","plan","nonce","operationToken","sourceIndexSha256","baseGeneration","baseManifestSha256","rootsSha256","archive","targets","beforeSeq"},"Intent exact fields")
    checked(type(intent["schema"]) is int and intent["schema"]==1,"Intent schema type")
    checked(all(type(intent[name]) is str and re.fullmatch("[a-f0-9]{32}",intent[name]) for name in ("plan","nonce","operationToken")),"Intent identity shape")
    checked(all(sha(intent[name]) for name in ("sourceIndexSha256","baseManifestSha256","rootsSha256")),"Intent hash shape")
    checked(type(intent["baseGeneration"]) is int and intent["baseGeneration"]>=0 and type(intent["beforeSeq"]) is int and 0<=intent["beforeSeq"]<=9007199254740991,"Intent integer limits")
    checked(type(intent["targets"]) is list and 0<len(intent["targets"])<=128,"Intent targets bound")


def validate_manifest(value, index):
    """Only shape/binding. Actual source/archive/lifecycle checks remain mandatory."""
    expected={"schema","dataModel","nonce","source","sourceIndexSha256","fenceSha256","transactionBinding","generation","archive","checkpoints","pins","pending","locations","manifestSha256"}
    checked(type(value) is dict and expected<=set(value) and set(value)<=expected|{"completedPlan","completedIntent"},"Manifest exact fields")
    checked(type(value["schema"]) is int and value["schema"] == 1, "Manifest schema")
    checked(value.get("manifestSha256") == digest(canonical({k:v for k,v in value.items() if k != "manifestSha256"})), "Manifest checksum")
    checked(type(value.get("generation")) is int and value["generation"] >= 0, "Generation")
    checked(value.get("dataModel") == "point-register-v1", "Unsupported data model")
    checked(type(value.get("nonce")) is str and re.fullmatch("[a-f0-9]{32}", value["nonce"]), "Nonce")
    checked(type(value["source"]) is str and 0<len(value["source"])<=1024 and sha(value["sourceIndexSha256"]) and sha(value["fenceSha256"]),"Source/fence binding shape")
    cache=value["transactionBinding"]
    checked(type(cache) is dict and set(cache)=={"bytes","sha256"} and type(cache["bytes"]) is int and 0<cache["bytes"]<=8388608 and sha(cache["sha256"]),"Cache binding shape")
    archive=value["archive"]
    checked(archive is None or type(archive) is dict and set(archive)=={"path","bytes","sha256"} and type(archive["path"]) is str and 0<len(archive["path"])<=1024 and type(archive["bytes"]) is int and 0<archive["bytes"]<=67108864 and sha(archive["sha256"]),"Archive binding shape")
    locations = value.get("locations")
    checked(type(locations) is list and len(locations) == len(index["segments"]) <= 128, "Segment count")
    for location, original in zip(locations, index["segments"]):
        checked(set(location) == {"name", "storage"}, "Location fields")
        checked(location["name"] == original["name"] and re.fullmatch("segment-[0-9]{6}\\.jsonl", location["name"]), "Exact original segment name")
        checked(location["storage"] in ("hot", "archive"), "Location type")
        checked(location["storage"] != "archive" or value.get("archive") is not None, "Archive source required")
    checked(type(value.get("pins")) is dict and len(value["pins"]) <= 32, "Pin count")
    checked(type(value.get("checkpoints")) is dict and len(value["checkpoints"]) <= 16, "Checkpoint count")
    for name,checkpoint in value["checkpoints"].items():
        checked(type(name) is str and re.fullmatch("[A-Za-z0-9_-]{1,64}",name) and archive is not None
            and checkpoint=={"archiveSha256":archive["sha256"],"sourceIndexSha256":value["sourceIndexSha256"]},"Checkpoint epoch/archive contradiction")
    count=0
    for name,pin in value["pins"].items():
        checked(type(name) is str and re.fullmatch("[A-Za-z0-9_-]{1,64}",name) and type(pin) is dict and set(pin)=={"transactions","versions","sequences"},"Pin shape")
        for key,roots in pin.items():
            checked(type(roots) is list and len(roots)<=1024,"Pin root bound")
            checked(all(type(v) is int and 0<v<=9007199254740991 for v in roots) if key=="sequences" else all(root_label(v) for v in roots),"Pin label shape")
            count+=len(roots)
    checked(count<=1024 and len(canonical(value["pins"]))<=65536,"Aggregate pin bound")
    checked(value["pending"] is None or type(value["pending"]) is str and re.fullmatch("[a-f0-9]{32}",value["pending"]),"Pending plan shape")
    checked(("completedPlan" in value)==("completedIntent" in value),"Completed intent pair")
    if "completedPlan" in value:
        completed=value["completedIntent"];intent_shape(completed)
        checked(completed["plan"]==value["completedPlan"] and completed["nonce"]==value["nonce"] and completed["sourceIndexSha256"]==value["sourceIndexSha256"]
            and completed["archive"]==archive and completed["baseGeneration"]+2<=value["generation"],"Completed intent binding")
        original={item["name"]:item for item in index["segments"]}
        checked(all(type(item) is dict and item.get("name") in original and item==original[item["name"]] and item["lastSeq"]<completed["beforeSeq"] for item in completed["targets"]),"Completed intent original targets")
    checked(len(canonical(value)) <= 1048576, "Manifest byte bound")
    return value


def validate_intent(intent, manifest, index):
    intent_shape(intent)
    checked(type(intent) is dict and intent.get("schema") == 1, "Intent schema")
    base = intent.get("baseGeneration")
    checked(type(base) is int, "Intent base generation")
    checked((manifest.get("generation"),manifest.get("pending")) in ((base,None),(base+1,intent.get("plan")))
        or manifest.get("generation") == base+2 and manifest.get("completedPlan") == intent.get("plan") and manifest.get("pending") is None,
        "Intent/pending plan binding")
    checked(type(intent.get("plan")) is str and re.fullmatch("[a-f0-9]{32}", intent["plan"]), "Plan identity")
    checked(intent.get("nonce") == manifest["nonce"], "Owner binding")
    checked(type(intent.get("operationToken")) is str and re.fullmatch("[a-f0-9]{32}",intent["operationToken"]),"Prepared operation token")
    checked(intent.get("sourceIndexSha256") == manifest["sourceIndexSha256"], "Source epoch binding")
    checked(sha(intent["baseManifestSha256"]) and sha(intent["rootsSha256"]),"Intent digest shape")
    checked(intent.get("archive") == manifest["archive"], "Archive binding")
    checked(manifest["generation"] in (base,base+1,base+2), "Intent generation")
    checked(type(intent.get("targets")) is list and 0 < len(intent["targets"]) <= 128, "Intent target count")
    checked(type(intent.get("beforeSeq")) is int and intent["beforeSeq"]>=0,"Intent cutoff")
    original = {item["name"]:item for item in index["segments"]}
    names = [item.get("name") for item in intent["targets"]]
    checked(len(set(names)) == len(names), "Duplicate deletion target")
    for item in intent["targets"]:
        checked(item.get("name") in original and item == original[item["name"]], "Exact original deletion binding")
        checked(item["lastSeq"]<intent["beforeSeq"],"Intent segment cutoff")
    return intent


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    contract = json.loads((here / "contract-v1.json").read_text())
    plan = json.loads((here / "test-plan.json").read_text())
    checked(contract["scope"]["archivesNeverDeleted"] is True and contract["scope"]["listRelationSupported"] is False, "Scope gate")
    checked(len(plan["cases"]) == 24 and len({case["id"] for case in plan["cases"]}) == 24, "Preregistered cases")
    print(json.dumps({"contract":binding(here/"contract-v1.json"),"testPlan":binding(here/"test-plan.json"),
        "actualFilesystemAcceptanceExecuted":False,"implementationComplete":False}))
