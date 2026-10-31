///|
/// Bounded encoding cache: values are official JSON strings, never conclusions.
/// Saturation only disables insertion and does not affect output or analysis.
priv struct QuotedStrings {
  values : Map[String, String]
  mut units : Int32
}

///|
let quoted_strings : QuotedStrings = { values: Map([]), units: 0, }

///|
fn cached_quote(value : String) -> String {
  match quoted_strings.values.get(value) {
    Some(text) => text
    None => {
      let text = Json(value).stringify()
      if quoted_strings.values.length() < 2048 &&
        quoted_strings.units + value.length() + text.length() <= 131072 {
        quoted_strings.values[value] = text
        quoted_strings.units += value.length() + text.length()
      }
      text
    }
  }
}

///|
fn scalar_string(value : Json, strings : Map[String, String]) -> String {
  match value {
    String(s) => quoted_cached(strings, s)
    _ => value.stringify()
  }
}

///|
/// Stream the largest array instead of materializing its JSON object tree.
/// Public report_json remains available for structured MoonBit callers.
fn report_string(r : Report, extras~ : Map[String, Json] = Map([])) -> String {
  let b = json_text()
  let strings : Map[String, String] = Map([])
  write_report(b, r, strings, extras~)
  b.to_string()
}

///|
/// Append a complete report without flattening a nested result into a temporary string.
fn write_report(
  b : JsonText,
  r : Report,
  strings : Map[String, String],
  extras~ : Map[String, Json] = Map([]),
) -> Unit {
  let small = report_json({
    ..r,
    edges: [],
    coverage: [],
    inferred_orders: Map([]),
    order_sources: Map([]),
  })
  let fields = match small {
    Object(m) => m
    _ => abort("Report object")
  }
  for name, value in extras {
    fields[name] = value
  }
  match fields.at("stats") {
    Object(m) => m["dependencies"] = Json(r.edges.length())
    _ => abort("Report stats")
  }
  b.write_char('{')
  let mut first = true
  for name, value in fields {
    if !first {
      b.write_char(',')
    }
    first = false
    b.write_string(quoted_cached(strings, name))
    b.write_char(':')
    if name == "coverage" {
      write_coverage(b, r, strings)
    } else if name == "versionOrderSources" {
      b.write_char('{')
      let mut first_key = true
      for key, source in r.order_sources {
        if !first_key {
          b.write_char(',')
        }
        first_key = false
        b.write_string(quoted_cached(strings, key))
        b.write_char(':')
        b.write_string(quoted_cached(strings, source))
      }
      b.write_char('}')
    } else if name == "versionOrders" {
      b.write_char('{')
      let mut first_key = true
      for key, versions in r.inferred_orders {
        if !first_key {
          b.write_char(',')
        }
        first_key = false
        b.write_string(quoted_cached(strings, key))
        b.write_string(":[")
        for i, version in versions {
          if i > 0 {
            b.write_char(',')
          }
          b.write_string(quoted_cached(strings, version))
        }
        b.write_char(']')
      }
      b.write_char('}')
    } else if name == "edges" {
      write_report_edges(b, r.edges, strings)
    } else {
      b.write_string(scalar_string(value, strings))
    }
  }
  b.write_char('}')
}

///|
fn write_coverage(
  b : JsonText,
  r : Report,
  strings : Map[String, String],
) -> Unit {
  b.write_char('[')
  for i, row in r.coverage {
    if i > 0 {
      b.write_char(',')
    }
    let source = r.order_sources.at(row.key)
    b.write_string("{\"key\":")
    b.write_string(quoted_cached(strings, row.key))
    b.write_string(",\"committedReads\":")
    b.write_string(row.committed_reads.to_string())
    b.write_string(",\"committedFinalWrites\":")
    b.write_string(row.committed_final_writes.to_string())
    b.write_string(",\"unresolvedReads\":")
    b.write_string(row.unresolved_reads.to_string())
    b.write_string(",\"versionOrderSource\":")
    b.write_string(quoted_cached(strings, source))
    b.write_string(",\"sourceLabel\":")
    b.write_string(
      quoted_cached(
        strings,
        order_source_cn(source, row.committed_final_writes),
      ),
    )
    b.write_char('}')
  }
  b.write_char(']')
}

///|
fn quoted_cached(strings : Map[String, String], value : String) -> String {
  match strings.get(value) {
    Some(text) => text
    None => {
      let text = cached_quote(value)
      strings[value] = text
      text
    }
  }
}

///|
fn optional_quoted(strings : Map[String, String], value : String?) -> String {
  match value {
    Some(s) => quoted_cached(strings, s)
    None => "null"
  }
}

///|
fn optional_integer(value : Int32?) -> String {
  match value {
    Some(i) => i.to_string()
    None => "null"
  }
}

///|
fn has_standard_rt_shell(e : Edge) -> Bool {
  e.kind == RT &&
  e.key is None &&
  e.from_op is None &&
  e.to_op is None &&
  e.from_version is None &&
  e.to_version is None &&
  e.reason ==
  "The source completed before the target began on the asserted common observer clock."
}

///|
fn write_standard_rt_shell(b : JsonText, from : String, to : String) -> Unit {
  b.write_string("{\"from\":")
  b.write_string(from)
  b.write_string(",\"to\":")
  b.write_string(to)
  b.write_string(
    ",\"kind\":\"rt\",\"key\":null,\"fromOp\":null,\"toOp\":null,\"fromVersion\":null,\"toVersion\":null,\"reason\":\"The source completed before the target began on the asserted common observer clock.\"}",
  )
}

///|
fn write_edge(b : JsonText, e : Edge, strings : Map[String, String]) -> Unit {
  // Keep the original per-edge entry and its MoonBit cache on every target.
  if has_standard_rt_shell(e) {
    write_standard_rt_shell(
      b,
      quoted_cached(strings, e.from),
      quoted_cached(strings, e.to),
    )
    return
  }
  b.write_string("{\"from\":")
  b.write_string(quoted_cached(strings, e.from))
  b.write_string(",\"to\":")
  b.write_string(quoted_cached(strings, e.to))
  b.write_string(",\"kind\":")
  b.write_string(quoted_cached(strings, dependency_label(e.kind)))
  b.write_string(",\"key\":")
  b.write_string(optional_quoted(strings, e.key))
  b.write_string(",\"fromOp\":")
  b.write_string(optional_integer(e.from_op))
  b.write_string(",\"toOp\":")
  b.write_string(optional_integer(e.to_op))
  b.write_string(",\"fromVersion\":")
  b.write_string(optional_quoted(strings, e.from_version))
  b.write_string(",\"toVersion\":")
  b.write_string(optional_quoted(strings, e.to_version))
  b.write_string(",\"reason\":")
  b.write_string(quoted_cached(strings, e.reason))
  b.write_char('}')
}
