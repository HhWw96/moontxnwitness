"""Boundary tests for the independent audit. No SDK, network or original results."""
import copy
import io
import json
from pathlib import Path
import sys
import unittest
import warnings
import zipfile

sys.path.insert(0, str(Path(__file__).parent))
import audit_reference as a


def row(model="point-register-v1"):
    initial = {"x": "i"} if model == "point-register-v1" else {"x": []}
    events = [{"kind": "snapshot", "consistent": True, "initial": initial},
              {"kind": "begin", "tx": "A", "connection": "CA"},
              {"kind": "begin", "tx": "B", "connection": "CB"}]
    if model == "point-register-v1":
        events += [{"kind": "write", "tx": "A", "key": "x", "version": "v", "predecessor": "i"},
                   {"kind": "read", "tx": "B", "key": "x", "version": "v"},
                   {"kind": "read", "tx": "A", "key": "x", "version": "i"}]
    else:
        events += [{"kind": "append", "tx": "A", "key": "x", "id": "one", "value": "same"},
                   {"kind": "append", "tx": "A", "key": "x", "id": "two", "value": "same"},
                   {"kind": "list_read", "tx": "B", "key": "x", "items": [{"id": "one", "value": "same"}, {"id": "two", "value": "same"}]}]
    events += [{"kind": "commit_request", "tx": "B"}, {"kind": "commit_ok", "tx": "B"},
               {"kind": "commit_request", "tx": "A"}, {"kind": "commit_ok", "tx": "A"}]
    for index, event in enumerate(events, 1):
        event.update(seq=index, time=index)
    source = {"traceSchema": 3, "clockDomain": "client-clock", "scope": {"exclusiveWriters": True},
              "gaps": [], "dataModel": model, "events": events}
    return {"id": "example", "inputSha256": a.sha(a.canonical(source)), "input": source}


def result_fixture(valid=False, anomalies=None, raw=None):
    if anomalies is None:
        anomalies = []
    if raw is None:
        v = "true" if valid is True else "false" if valid is False else ":unknown"
        raw = ("{:valid? " + v + ", :anomaly-types [" + " ".join(":" + t for t in anomalies) + "]}\n").encode()
    summary = {"id": "example", "inputSha256": "a" * 64, "rawResultFile": "example.edn",
               "cycleSearchTimeout": "cycle-search-timeout" in anomalies, "anomalyTypes": anomalies,
               "valid": valid if type(valid) is bool else "unknown",
               "originalValidity": {"kind": "boolean", "value": valid} if type(valid) is bool else {"kind": "keyword", "value": "unknown"},
               "actualElleInvocationAttempted": True, "actualElleResultReturned": True, "rawResultRetained": True}
    data = a.canonical(summary) + b"\n"
    completion = {"raw": a.bound(raw), "summary": a.bound(data), "result": summary}
    return raw, data, completion


def ledger_fixture():
    controls, run, lines, previous = [["example", "a" * 64]], "run", [], "0" * 64
    for index, phase in enumerate(["preparing", "invocation-intent", "returned", "completed"], 1):
        body = {"sequence": index, "runId": run, "ordinal": 0, "id": "example", "inputSha256": "a" * 64, "phase": phase}
        if phase == "completed":
            body.update(result={}, raw={"bytes": 0, "sha256": a.sha(b"")}, summary={"bytes": 0, "sha256": a.sha(b"")})
        text = a.canonical(body).decode()
        digest = a.sha(text.encode())
        lines.append({"body": text, "bodySha256": digest, "previousSha256": previous})
        previous = digest
    return lines, controls, run


class ReaderTests(unittest.TestCase):
    def test_request_roundtrip(self):
        self.assertEqual(a.edn('{"a" [nil true false -1 "\\u4e2d"]}'), {"a": [None, True, False, -1, "中"]})

    def test_forbidden_edn(self):
        cases = ['#=(+ 1 2)', '#inst "2026-01-01"', '#_ 1 2', '#{1}', '(1)', ':x',
                 '{"x" 1 "x" 2}', '{"x" 1} {}', '{"x"}', '9223372036854775808',
                 '1.0', 'NaN', '"\\ud800"', '[1', '; comment\n1']
        for text in cases:
            with self.subTest(text=text), self.assertRaises(a.AuditError):
                a.edn(text)

    def test_raw_collections_are_data(self):
        value = a.edn('{:valid? false :anomaly-types (:internal) :expected [... "id"] :not #{:x}}', raw=True)
        self.assertIs(value[a.Keyword("valid?")], False)
        self.assertIsInstance(value[a.Keyword("expected")][0], a.EllipsisSymbol)

    def test_raw_tags_and_general_symbols_forbidden(self):
        for text in ['#object[a]', 'foo', '#=(evil)', '{:x 1 :x 2}']:
            with self.subTest(text=text), self.assertRaises(a.AuditError):
                a.edn(text, raw=True)

    def test_edn_python_key_collisions_fail_closed(self):
        for text in ['{true "boolean" 1 "integer"}', '{false "boolean" 0 "integer"}',
                     '{1 "integer" true "boolean"}', '{0 "integer" false "boolean"}',
                     '{true "one"}', '{1 "one"}']:
            with self.subTest(text=text), self.assertRaises(a.AuditError):
                a.edn(text, raw=True)
        self.assertEqual(a.edn('{:x 1 "x" 2}', raw=True), {a.Keyword("x"): 1, "x": 2})

    def test_depth_bound(self):
        with self.assertRaises(a.AuditError):
            a.edn('[' * 66 + '0' + ']' * 66)

    def test_strict_json(self):
        for text in ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}']:
            with self.subTest(text=text), self.assertRaises(a.AuditError):
                a.strict_json(text)

    def test_json_float_overflow_and_nested_nonfinite_rejected(self):
        for text in ['{"x":1e309}', '{"x":-1e309}', '[{"x":[1e309]}]',
                     '{"x":{"y":-1e309}}', '[0,{"x":NaN}]', '{"x":[Infinity]}']:
            with self.subTest(text=text), self.assertRaises(a.AuditError):
                a.strict_json(text)
        self.assertEqual(a.strict_json('{"x":[1.25,-2.5,1e308,1e-308]}'),
                         {"x": [1.25, -2.5, 1e308, 1e-308]})

    def test_actual_options_literal_and_unjustified_assumptions(self):
        source = b'''(def options {:consistency-models [:serializable]
 :additional-graphs [] :linearizable-keys? false :sequential-keys? false
 :wfr-keys? false :directory nil :cycle-search-timeout 10000})'''
        self.assertEqual(a.wrapper_options(source), a.OPTIONS)
        for changed in [source.replace(b":wfr-keys? false", b":wfr-keys? true"),
                        source.replace(b":additional-graphs []", b":additional-graphs [:realtime]"),
                        source.replace(b":serializable", b":strict-serializable"),
                        source + source]:
            with self.subTest(changed=changed), self.assertRaises(a.AuditError):
                a.wrapper_options(changed)


class ProjectionTests(unittest.TestCase):
    def test_original_register_projection(self):
        original = row()
        request = a.expected_request(original)
        self.assertEqual([o["type"] for o in request["operations"]], ["invoke", "invoke", "ok", "ok"])
        self.assertEqual([o["process"] for o in request["operations"]], [0, 1, 1, 0])
        self.assertEqual(request["operations"][0]["value"], [["w", "x", "v"], ["r", "x", None]])
        self.assertEqual(request["operations"][2]["value"], [["r", "x", "v"]])
        self.assertEqual(request["operations"][3]["value"][-1], ["r", "x", None])
        self.assertEqual(a.check_projection(original, request)["extraUnmappedSemanticFacts"], [])

    def test_list_repeated_business_values_retain_ids(self):
        original = row("append-list-v1")
        request = a.expected_request(original)
        self.assertEqual(request["operations"][0]["value"], [["append", "x", "one"], ["append", "x", "two"]])
        self.assertEqual(request["operations"][2]["value"], [["r", "x", ["one", "two"]]])
        self.assertIsNone(request["initialRegisterVersionRenaming"])

    def test_each_prepared_field_bound(self):
        original = row()
        for label, mutate in [
            ("invoke read", lambda p: p["operations"][0]["value"][1].__setitem__(2, "v")),
            ("read source", lambda p: p["operations"][2]["value"][0].__setitem__(2, None)),
            ("write ID", lambda p: p["operations"][0]["value"][0].__setitem__(2, "other")),
            ("process", lambda p: p["operations"][2].__setitem__("process", 0)),
            ("index", lambda p: p["operations"][2].__setitem__("index", 9)),
            ("status", lambda p: p["operations"][2].__setitem__("type", "fail")),
            ("mapping", lambda p: p["originalSeqMapping"][2].__setitem__("rawSeq", 9)),
            ("initial", lambda p: p["initialRegisterVersionRenaming"].__setitem__("x", "other")),
            ("drop mop", lambda p: p["operations"][0]["value"].pop()),
            ("extra", lambda p: p.__setitem__("inferred", True)),
        ]:
            with self.subTest(label=label), self.assertRaises(a.AuditError):
                actual = copy.deepcopy(a.expected_request(original))
                mutate(actual)
                a.check_projection(original, actual)

    def test_unmapped_semantic_facts_rejected(self):
        for field, value in [("versionOrders", {}), ("logicalClients", []), ("unknownFact", True)]:
            changed = row()
            changed["input"][field] = value
            with self.subTest(field=field), self.assertRaises(a.AuditError):
                a.expected_request(changed)

    def test_unsupported_original_observations_rejected(self):
        mutations = [
            lambda s: s["gaps"].append("lost event"),
            lambda s: s["scope"].__setitem__("exclusiveWriters", 1),
            lambda s: s["events"][3].__setitem__("predecessor", "other"),
            lambda s: s["events"][4].__setitem__("version", "missing"),
            lambda s: s["events"][4].__setitem__("seq", 99),
            lambda s: s["events"][4].__setitem__("unknownField", True),
            lambda s: s["events"][-1].__setitem__("kind", "commit_unknown"),
            lambda s: s["events"][0].__setitem__("consistent", False),
            lambda s: s["events"][0]["initial"].pop("x"),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(a.AuditError):
                changed = row()
                mutate(changed["input"])
                a.expected_request(changed)

    def test_list_sources_and_business_values_bound(self):
        for field, value in [("id", "missing"), ("value", "other")]:
            original = row("append-list-v1")
            original["input"]["events"][5]["items"][0][field] = value
            with self.subTest(field=field), self.assertRaises(a.AuditError):
                a.expected_request(original)

    def test_list_duplicate_identity_rejected(self):
        original = row("append-list-v1")
        original["input"]["events"][4]["id"] = "one"
        with self.assertRaises(a.AuditError):
            a.expected_request(original)

    def test_anomalous_repeated_observed_identity_preserved(self):
        original = row("append-list-v1")
        original["input"]["events"][5]["items"].append({"id": "one", "value": "same"})
        request = a.expected_request(original)
        self.assertEqual(request["operations"][2]["value"], [["r", "x", ["one", "two", "one"]]])
        self.assertEqual(a.check_projection(original, request)["repeatedObservedAppendIdentities"], 1)
        altered = copy.deepcopy(request)
        altered["operations"][2]["value"][0][2].pop()
        with self.assertRaises(a.AuditError):
            a.check_projection(original, altered)

    def test_nonempty_initial_list_not_silently_dropped(self):
        original = row("append-list-v1")
        original["input"]["events"][0]["initial"]["x"] = [{"id": "before", "value": "same"}]
        with self.assertRaises(a.AuditError):
            a.expected_request(original)


class EvidenceTests(unittest.TestCase):
    def test_ledger_and_each_identity_phase(self):
        lines, controls, run = ledger_fixture()
        result = a.check_ledger(b"\n".join(a.canonical(x) for x in lines), controls, run)
        self.assertIn("example", result)
        for field, changed in [("id", "other"), ("inputSha256", "b" * 64), ("runId", "other"),
                               ("sequence", 8), ("ordinal", 1), ("phase", "reader-error")]:
            mutated = copy.deepcopy(lines)
            body = a.strict_json(mutated[3]["body"])
            body[field] = changed
            mutated[3]["body"] = a.canonical(body).decode()
            mutated[3]["bodySha256"] = a.sha(mutated[3]["body"].encode())
            with self.subTest(field=field), self.assertRaises(a.AuditError):
                a.check_ledger(b"\n".join(a.canonical(x) for x in mutated), controls, run)

    def test_ledger_hash_chain_not_just_json(self):
        lines, controls, run = ledger_fixture()
        for field in ["bodySha256", "previousSha256"]:
            changed = copy.deepcopy(lines)
            changed[2][field] = "b" * 64
            with self.subTest(field=field), self.assertRaises(a.AuditError):
                a.check_ledger(b"\n".join(a.canonical(x) for x in changed), controls, run)

    def test_actual_valid_false_unknown_timeout(self):
        for valid, anomalies, expected in [(True, [], True), (False, ["G1c"], True),
                                           (None, ["empty-transaction-graph"], False),
                                           (False, ["cycle-search-timeout"], False)]:
            raw, summary, completion = result_fixture(valid, anomalies)
            result = a.check_result(raw, summary, completion, "example", "a" * 64)
            self.assertEqual(result["comparisonEligible"], expected)

    def test_upstream_true_omits_anomaly_field(self):
        raw, summary, completion = result_fixture(True, [], b"{:valid? true}\n")
        self.assertTrue(a.check_result(raw, summary, completion, "example", "a" * 64)["validity"])

    def test_rehashed_raw_result_still_checked(self):
        raw, summary, completion = result_fixture(False, ["G1c"])
        raw = raw.replace(b"false", b"true")
        completion["raw"] = a.bound(raw)
        with self.assertRaises(a.AuditError):
            a.check_result(raw, summary, completion, "example", "a" * 64)

    def test_summary_and_completed_both_rehashed_still_checked(self):
        raw, data, completion = result_fixture(False, ["G1c"])
        summary = a.strict_json(data)
        summary["anomalyTypes"] = ["G0"]
        data = a.canonical(summary)
        completion.update(summary=a.bound(data), result=summary)
        with self.assertRaises(a.AuditError):
            a.check_result(raw, data, completion, "example", "a" * 64)

    def test_invocation_claim_not_a_result(self):
        raw, data, completion = result_fixture(False)
        summary = a.strict_json(data)
        summary["actualElleResultReturned"] = False
        data = a.canonical(summary)
        completion.update(summary=a.bound(data), result=summary)
        with self.assertRaises(a.AuditError):
            a.check_result(raw, data, completion, "example", "a" * 64)

    def test_sdk_members_forbidden(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as z:
            z.writestr("SDK-COLLECTION.json", "{}")
        stream.seek(0)
        archive = a.Archive(stream, "test")
        with self.assertRaises(a.AuditError):
            archive.read("SDK-COLLECTION.json")
        self.assertEqual(archive.opened, [])

    def test_archive_traversal_names(self):
        for path in ["../escape", "/absolute", "C:/path", "a\\b"]:
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w") as z:
                z.writestr(path.replace("\\", "/"), "x")
            # Windows ZipInfo normalizes a backslash before writing, so create
            # the actual unsafe member bytes in both central/local names.
            payload = stream.getvalue()
            if "\\" in path:
                payload = payload.replace(path.replace("\\", "/").encode(), path.encode())
            with self.subTest(path=path), self.assertRaises(a.AuditError):
                a.Archive(io.BytesIO(payload), "test")

    def test_actual_duplicate_archive_member_rejected(self):
        stream = io.BytesIO()
        with warnings.catch_warnings(record=True) as observed:
            warnings.simplefilter("always")
            with zipfile.ZipFile(stream, "w") as z:
                z.writestr("raw/same.edn", "{:valid? true}")
                z.writestr("raw/same.edn", "{:valid? false}")
        self.assertTrue(observed)
        stream.seek(0)
        with zipfile.ZipFile(stream) as z:
            self.assertEqual(z.namelist(), ["raw/same.edn", "raw/same.edn"])
        stream.seek(0)
        with self.assertRaisesRegex(a.AuditError, "duplicate member"):
            a.Archive(stream, "test")

    def test_archive_member_bound(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as z:
            z.writestr("raw.edn", "0123456789")
        stream.seek(0)
        with self.assertRaises(a.AuditError):
            a.Archive(stream, "test").read("raw.edn", limit=5)

    def test_binding_rejects_same_size_changed_bytes(self):
        with self.assertRaises(a.AuditError):
            a.check_binding(b"b", a.bound(b"a"), "fixed source")


if __name__ == "__main__":
    unittest.main(verbosity=2)
