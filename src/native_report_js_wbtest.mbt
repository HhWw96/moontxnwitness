///|
#cfg(target="js")
extern "js" fn native038_snapshot(value : NativeReportObject) -> String =
  #| value => JSON.stringify(value)

///|
#cfg(target="js")
extern "js" fn native038_parsed_snapshot(text : String) -> String =
  #| text => JSON.stringify(JSON.parse(text))

///|
#cfg(target="js")
extern "js" fn native051_is_null(value : NativeReportObject) -> Bool =
  #| value => value === null

///|
#cfg(target="js")
extern "js" fn native051_own_fields(value : NativeReportObject) -> Bool =
  #| value => Object.getPrototypeOf(value) === Object.prototype && Object.hasOwn(value, '__proto__') && value.__proto__ === 'safe' && value.constructor === null

///|
#cfg(target="js")
fn native051_check(value : Json) -> Unit raise {
  let original = value.stringify(indent=2)
  let bytes = @utf8.encode(original).length()
  assert_eq(
    native038_snapshot(native_model_record(value, limit=bytes)),
    native038_parsed_snapshot(original),
  )
  assert_true(
    (Some(native_model_record(value, limit=bytes - 1)) catch { _ => None })
    is None,
  )
  assert_eq(value.stringify(indent=2), original)
}

///|
#cfg(target="js")
test "native051 01 bounded host conversion preserves JSON scalars and numeric lexemes" {
  for
    text in [
      "null", "true", "false", "0", "-0", "1e20", "9007199254740993", "1.234567890123456789",
      "[]", "{}", "[null,false,true,{},[]]",
    ] {
    native051_check(@json.parse(text))
  }
}

///|
#cfg(target="js")
test "native051 02 escaped and Unicode strings use the original pretty UTF8 byte limit" {
  for
    text in [
      "", "月", "🙂𐐷", "é", "é", "a\"\\b", "\n\r\t\b\f\u0000\u001f", "  ",
    ] {
    native051_check({ "label": text, "nested": [{ "value": text }] })
  }
}

///|
#cfg(target="js")
test "native051 03 property names cannot alter host prototypes" {
  let value : Json = {
    "__proto__": "safe",
    "constructor": Json::null(),
    "prototype": ["unchanged"],
    "0": "zero",
    "2": "two",
    "01": "leading",
  }
  native051_check(value)
  assert_true(native051_own_fields(native_model_record(value)))
}

///|
#cfg(target="js")
test "native051 04 nested reports are fresh and caller mutation cannot alter later calls" {
  let value : Json = {
    "edges": [{ "from": "A" }],
    "stats": { "dependencies": 1 },
    "findings": [],
  }
  let first = native_model_record(value)
  let second = native_model_record(value)
  let original = native038_snapshot(second)
  native038_mutate(first)
  assert_eq(native038_snapshot(second), original)
  native051_check(value)
}

///|
#cfg(target="js")
test "native051 05 report containers retain the original 64 level guard" {
  let mut value : Json = Json::null()
  for _ in 0..<64 {
    value = [value]
  }
  native051_check(value)
  value = [value]
  assert_true((Some(native_model_record(value)) catch { _ => None }) is None)
}

///|
#cfg(target="js")
test "native051 06 register and list model reports exactly match all fourteen text results" {
  for
    (source, options) in [
      (mraw_history(mraw_simple()).source_text, "{\"models\":\"elle-core\"}"),
      (
        mlp_history(mlp_multi()).source_text,
        "{\"models\":\"elle-core\",\"listProfile\":\"captured-list-prefix-state/v2\"}",
      ),
      (mraw_history(mraw_simple()).source_text, "{\"maxSourceChecks\":0}"),
    ] {
    assert_eq(
      native038_snapshot(classify_models_v4_native(source, options)),
      native038_parsed_snapshot(classify_models_v4_json(source, options)),
    )
  }
}

///|
#cfg(target="js")
test "native051 07 relation predicate model report preserves budgets and complete evidence" {
  for options in ["{}", "{\"models\":\"elle-core\"}", "{\"maxSourceChecks\":0}"] {
    let source = rpred_history(rpred_empty_skew(), empty=true).source_text
    assert_eq(
      native038_snapshot(classify_relation_models_v4_native(source, options)),
      native038_parsed_snapshot(
        classify_relation_models_v4_json(source, options),
      ),
    )
  }
}

///|
#cfg(target="js")
test "native051 08 invalid input requests existing text errors instead of fabricated reports" {
  for text in ["{}", "{", "null"] {
    assert_true(native051_is_null(classify_models_v4_native(text, "{}")))
    assert_true(
      native051_is_null(classify_relation_models_v4_native(text, "{}")),
    )
  }
  for options in ["{", "{\"models\":[]}", "{\"maxStates\":100001}"] {
    assert_true(
      native051_is_null(
        classify_models_v4_native(
          mraw_history(mraw_simple()).source_text,
          options,
        ),
      ),
    )
    assert_true(
      native051_is_null(
        classify_relation_models_v4_native(rmwire_source(), options),
      ),
    )
  }
}

///|
#cfg(target="js")
extern "js" fn native038_mutate(value : NativeReportObject) -> Unit =
  #| value => { value.edges[0].from = 'changed'; value.edges.push({}); value.stats.dependencies = -1; value.findings.push({code:'changed'}); }

///|
#cfg(target="js")
fn native038_edge(from : String, to : String) -> Edge {
  {
    from,
    to,
    kind: RT,
    key: None,
    from_op: None,
    to_op: None,
    from_version: None,
    to_version: None,
    reason: "The source completed before the target began on the asserted common observer clock.",
  }
}

///|
#cfg(target="js")
fn native038_check(
  report : Report,
  extras~ : Map[String, Json] = Map([]),
) -> Unit raise {
  let expected = report_string(report, extras~)
  assert_eq(
    native038_snapshot(native_report_object(report, extras~)),
    native038_parsed_snapshot(expected),
  )
  // Neither source fields nor the original text renderer are mutated.
  assert_eq(report_string(report, extras~), expected)
}

///|
#cfg(target="js")
test "native038 01 empty report preserves all metadata and explicit nulls" {
  native038_check(analyze(hist([])))
}

///|
#cfg(target="js")
test "native038 02 Unicode and escaping retain exact parsed text semantics" {
  let edges : Array[Edge] = []
  for
    name in [
      "月", "🙂𐐷", "é", "é", "a\"\\b", "\n\r\t\b\f\u0000\u001f", "  ",
      "",
    ] {
    edges.push(native038_edge(name, name + "end"))
  }
  native038_check({ ..analyze(hist([])), edges, })
}

///|
#cfg(target="js")
test "native038 03 every optional provenance mask preserves null versus present values" {
  let edges : Array[Edge] = []
  for mask in 0..<32 {
    edges.push({
      ..native038_edge("from", "to"),
      key: if mask % 2 != 0 {
        Some("")
      } else {
        None
      },
      from_op: if mask / 2 % 2 != 0 {
        Some(0)
      } else {
        None
      },
      to_op: if mask / 4 % 2 != 0 {
        Some(2147483647)
      } else {
        None
      },
      from_version: if mask / 8 % 2 != 0 {
        Some("")
      } else {
        None
      },
      to_version: if mask / 16 % 2 != 0 {
        Some("version\u0000")
      } else {
        None
      },
    })
  }
  native038_check({ ..analyze(hist([])), edges, })
}

///|
#cfg(target="js")
test "native038 04 all dependency kinds and nonstandard RT retain their complete shell" {
  let edges = [WR, WW, RW, RT].map(kind => {
    ..native038_edge("A", "B"),
    kind,
    reason: "custom reason\"\\🙂",
    key: Some("__proto__"),
    from_op: Some(0),
    to_op: Some(1),
    from_version: Some("a"),
    to_version: Some("b"),
  })
  native038_check({ ..analyze(hist([])), edges, })
}

///|
#cfg(target="js")
test "native038 05 native arrays and nested objects are fresh for every call" {
  let report = { ..analyze(hist([])), edges: [native038_edge("A", "B")], }
  let first = native_report_object(report)
  let second = native_report_object(report)
  let original = native038_snapshot(second)
  native038_mutate(first)
  assert_eq(native038_snapshot(second), original)
  native038_check(report)
}

///|
#cfg(target="js")
test "native038 06 coverage version orders and witness retain actual sources" {
  let history = hist(
    [
      tx("A", [read_op("x", "x0"), write_op("y", "y1")]),
      tx("B", [read_op("y", "y0"), write_op("x", "x1")]),
    ],
    orders=Map([("x", ["x0", "x1"]), ("y", ["y0", "y1"])]),
  )
  let report = analyze(history)
  assert_true(report.outcome == Violation)
  assert_true(!report.witness.is_empty())
  native038_check(report)
}

///|
#cfg(target="js")
test "native038 07 balanced extras and actual zero budgets remain unchanged" {
  let result = analyze_with_options(
    hist([]),
    options=analysis_options(
      max_attempts=0,
      max_operation_checks=0,
      max_cached_states=0,
    ),
  )
  native038_check(result.report, extras=analysis_extras(result))
}

///|
#cfg(target="js")
test "native038 08 legacy invalid inputs retain the original report" {
  for text in ["not json", "[]", "{}", "{\"version\":\"business\"}"] {
    assert_eq(
      native038_snapshot(analyze_native_js_v1(text)),
      native038_parsed_snapshot(analyze_json(text)),
    )
  }
}

///|
#cfg(target="js")
test "native038 09 invalid options follow the existing parser and defaults" {
  for
    options in [
      "not json", "[]", "{\"maxAttempts\":-1}", "{\"maxAttempts\":100001}", "{\"ignored\":true}",
    ] {
    assert_eq(
      native038_snapshot(analyze_options_native_js_v1("{}", options)),
      native038_parsed_snapshot(analyze_options_json("{}", options)),
    )
  }
}

///|
#cfg(target="js")
test "native038 10 metadata map keys keep JS parsed key order" {
  let report = analyze({
    model: Serializable,
    initial: Map([("10", "x0"), ("2", "y0"), ("__proto__", "z0")]),
    version_orders: Map([]),
    transactions: [],
  })
  native038_check(report)
}

///|
#cfg(target="js")
test "native038 11 complete 49770-edge dense array keeps every edge and statistic" {
  let edges : Array[Edge] = []
  for i in 0..<316 {
    for j in (i + 1)..<316 {
      edges.push(native038_edge("T" + i.to_string(), "T" + j.to_string()))
    }
  }
  assert_eq(edges.length(), 49770)
  native038_check({ ..analyze(hist([])), edges, })
}

///|
#cfg(target="js")
test "native038 12 extras preserve business version strings and nested values" {
  native038_check(
    analyze(hist([])),
    extras=Map([
      (
        "extension",
        { "version": "business🙂", "nested": [null, "", 0, false] },
      ),
    ]),
  )
}

///|
#cfg(target="js")
extern "js" fn source_digest_test_host_available() -> Bool =
  #| () => typeof globalThis.process?.getBuiltinModule === 'function' && typeof ''.isWellFormed === 'function'

///|
#cfg(target="js")
extern "js" fn source_digest_test_malformed() -> String =
  #| () => '\ud800x\udc00'

///|
#cfg(target="js")
test "source digest uses the available Node primitive without changing SHA" {
  let native = source_digest_native("abc")
  if source_digest_test_host_available() {
    assert_eq(
      native, "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    )
  } else {
    assert_eq(native, "")
  }
}

///|
#cfg(target="js")
test "source digest keeps malformed UTF-16 on the original encoder path" {
  assert_eq(source_digest_native(source_digest_test_malformed()), "")
}
