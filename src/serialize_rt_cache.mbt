///|
/// Only already encoded strings cross this JS cache. JSON encoding stays in
/// quoted_cached/cached_quote; no Option, Map or object-layout ABI is exposed.
#cfg(target="js")
#external
priv type ReportRTQuotedCache

///|
#cfg(target="js")
extern "js" fn new_report_rt_quoted_cache() -> ReportRTQuotedCache =
  #| () => new Map()

///|
/// An official quoted JSON string has at least two units, so an empty result is
/// a safe miss sentinel without depending on MoonBit's Option representation.
#cfg(target="js")
extern "js" fn report_rt_cache_get(
  cache : ReportRTQuotedCache,
  key : String,
) -> String =
  #| (cache, key) => { const value = cache.get(key); return value === undefined ? "" : value; }

///|
#cfg(target="js")
extern "js" fn report_rt_cache_put(
  cache : ReportRTQuotedCache,
  key : String,
  encoded : String,
) -> Unit =
  #| (cache, key, encoded) => { cache.set(key, encoded); }

///|
#cfg(target="js")
fn report_rt_cached_quote(
  cache : ReportRTQuotedCache,
  strings : Map[String, String],
  value : String,
) -> String {
  let encoded = report_rt_cache_get(cache, value)
  if !encoded.is_empty() {
    return encoded
  }
  let encoded = quoted_cached(strings, value)
  report_rt_cache_put(cache, value, encoded)
  encoded
}

///|
#cfg(target="js")
fn write_report_edge(
  b : JsonText,
  edge : Edge,
  strings : Map[String, String],
  rt_cache : ReportRTQuotedCache,
) -> Unit {
  if has_standard_rt_shell(edge) {
    write_standard_rt_shell(
      b,
      report_rt_cached_quote(rt_cache, strings, edge.from),
      report_rt_cached_quote(rt_cache, strings, edge.to),
    )
  } else {
    write_edge(b, edge, strings)
  }
}

///|
#cfg(target="js")
fn write_report_edges(
  b : JsonText,
  edges : Array[Edge],
  strings : Map[String, String],
) -> Unit {
  let rt_cache = new_report_rt_quoted_cache()
  b.write_char('[')
  for i, edge in edges {
    if i > 0 {
      b.write_char(',')
    }
    write_report_edge(b, edge, strings, rt_cache)
  }
  b.write_char(']')
}

///|
/// Other backends retain the original loop and allocate no additional cache.
#cfg(not(target="js"))
fn write_report_edges(
  b : JsonText,
  edges : Array[Edge],
  strings : Map[String, String],
) -> Unit {
  b.write_char('[')
  for i, edge in edges {
    if i > 0 {
      b.write_char(',')
    }
    write_edge(b, edge, strings)
  }
  b.write_char(']')
}
