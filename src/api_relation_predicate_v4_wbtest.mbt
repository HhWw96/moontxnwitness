///|
test "predicate wire 01 category and rule definition are required independently" {
  for
    options in [
      "{}", "{\"category\":\"G2\"}", "{\"ruleSet\":\"adya-2000-scoped-categories-v1\"}",
      "{\"category\":\"G2\",\"ruleSet\":\"unknown\"}",
    ] {
    assert_eq(
      wire034_at(classify_relation_predicate_v4_json("{}", options), ["status"]),
      Json("invalid"),
    )
  }
}

///|
test "predicate wire 02 duplicate decoded keys and unknown fields are refused" {
  for
    options in [
      "{\"category\":\"G2\",\"cate\\u0067ory\":\"G0\",\"ruleSet\":\"adya-2000-scoped-categories-v1\"}",
      "{\"category\":\"G2\",\"ruleSet\":\"adya-2000-scoped-categories-v1\",\"models\":[\"serializable\"]}",
    ] {
    assert_eq(
      wire034_at(classify_relation_predicate_v4_json("{}", options), ["status"]),
      Json("invalid"),
    )
  }
}

///|
test "predicate wire 03 all categories and both definitions bind revalidated evidence" {
  let source = rpred_history(rpred_empty_skew(), empty=true).source_text
  for
    category in [
      "G0", "G1c", "G2-item", "G2", "G-single-item", "G-single", "G-nonadjacent",
    ] {
    for
      rules in [
        "adya-2000-scoped-categories-v1", "elle-4e359e5-scoped-categories-v1",
      ] {
      let options = (
        { "category": Json(category), "ruleSet": Json(rules) } : Json).stringify()
      let report = classify_relation_predicate_v4_json(source, options)
      assert_eq(wire034_at(report, ["category"]), Json(category))
      assert_eq(
        wire034_at(
          verify_relation_predicate_classification_v4_json(
            source, report, options,
          ),
          ["valid"],
        ),
        Json(true),
      )
      assert_eq(
        wire034_at(
          verify_relation_predicate_classification_v4_json(source, report, "{}"),
          ["valid"],
        ),
        Json(false),
      )
    }
  }
}

///|
test "predicate wire 04 overflow and fractional budgets never become acceptance" {
  for
    (key, number) in [
      ("maxStates", 100001.0),
      ("maxEdgeChecks", -1.0),
      ("maxGraphChecks", 0.5),
      ("maxPredicateChecks", 1000001.0),
      ("maxCandidateVisits", 100001.0),
    ] {
    let options : Json = {
      "category": "G2",
      "ruleSet": "adya-2000-scoped-categories-v1",
    }
    let fields = match options {
      Object(fields) => fields
      _ => abort("object")
    }
    fields[key] = Json(number)
    assert_eq(
      wire034_at(
        classify_relation_predicate_v4_json("{}", options.stringify()),
        ["status"],
      ),
      Json("invalid"),
    )
  }
}
