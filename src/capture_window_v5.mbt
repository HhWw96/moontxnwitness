///|
priv struct CaptureWindowV5 {
  unlocated : Bool
  closed : Map[String, Bool]
  uncertain_after : Map[String, Int64]
  complete : Bool
}

///|
/// Sequence holes may contain operations on every transaction then active.
/// Producer-finality and known local prefixes are separate source properties.
fn capture_window_v5(
  history : HistoryV4,
  normalized : Json,
  charge : () -> Bool,
) -> CaptureWindowV5 {
  let n = object_fields_unchecked_v3(normalized)
  let root = object_fields_unchecked_v3(history.source_document)
  let unlocated = !capture_source_array_v4(
    root.get_or_default("gaps", Json::null()),
  ).is_empty()
  let missing : Array[Int64] = []
  let unknown : Map[String, Int64] = Map([])
  let closed : Map[String, Bool] = Map([])
  let cutoff : Map[String, Int64] = Map([])
  let verified_statements : Map[Int64, Bool] = Map([])
  let verified_facts : Map[Int64, Bool] = Map([])
  let proof = object_fields_unchecked_v3(
    n.get_or_default("sqlProof", Json::null()),
  )
  for
    seq in capture_source_array_v4(
      proof.get_or_default("verifiedStatements", Json::null()),
    ) {
    if !charge() {
      return { unlocated, closed, uncertain_after: cutoff, complete: false, }
    }
    verified_statements[capture_source_seq_v4(seq)] = true
  }
  for
    seq in capture_source_array_v4(
      proof.get_or_default("verifiedFacts", Json::null()),
    ) {
    if !charge() {
      return { unlocated, closed, uncertain_after: cutoff, complete: false, }
    }
    verified_facts[capture_source_seq_v4(seq)] = true
  }
  let mut expected = 1L
  for event in capture_source_array_v4(n.at("observations")) {
    if !charge() {
      return { unlocated, closed, uncertain_after: cutoff, complete: false, }
    }
    let e = object_fields_unchecked_v3(event)
    let seq = capture_source_seq_v4(e.at("seq"))
    if seq != expected {
      missing.push(expected)
    }
    expected = seq + 1L
    let kind = e.at("kind")
    let unproved = (
        kind == Json("statement") && !verified_statements.contains(seq)
      ) ||
      (kind == Json("condition") && !verified_facts.contains(seq)) ||
      (kind == Json("rows") && e.get("complete") == Some(Json(false)))
    if unproved {
      match e.get("tx") {
        Some(String(tx)) =>
          match unknown.get(tx) {
            Some(first) if first <= seq => ()
            _ => unknown[tx] = seq
          }
        _ => ()
      }
    }
  }
  for raw in capture_source_array_v4(n.at("transactions")) {
    if !charge() {
      return { unlocated, closed, uncertain_after: cutoff, complete: false, }
    }
    let tx = object_fields_unchecked_v3(raw)
    let id = capture_source_string_v4(tx.at("id"))
    let start = capture_source_seq_v4(tx.at("beginSeq"))
    let end = match tx.at("endSeq") {
      Number(n, ..) => Some(n.to_int64())
      _ => None
    }
    let mut first = unknown.get(id)
    for hole in missing {
      if !charge() {
        return { unlocated, closed, uncertain_after: cutoff, complete: false, }
      }
      if hole > start &&
        (end is None || hole <= end.unwrap()) &&
        (first is None || hole < first.unwrap()) {
        first = Some(hole)
      }
    }
    if unlocated {
      first = Some(start)
    }
    match first {
      Some(at) => cutoff[id] = at
      _ => ()
    }
    let confirmed = tx.at("status") == Json("committed") ||
      tx.at("status") == Json("aborted")
    closed[id] = confirmed &&
      !unlocated &&
      end is Some(last) &&
      (first is None || first.unwrap() > last)
  }
  { unlocated, closed, uncertain_after: cutoff, complete: true, }
}

///|
fn capture_prefix_known_v5(
  window : CaptureWindowV5?,
  tx : String,
  at : Int64,
) -> Bool {
  match window {
    Some(window) if window.complete && !window.unlocated =>
      match window.uncertain_after.get(tx) {
        Some(first) => at < first
        None => true
      }
    _ => false
  }
}
