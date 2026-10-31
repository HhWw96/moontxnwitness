///|
/// This interpreter consumes original capture events and a CO/VIS certificate.
/// It does not import graph indexes, inferred predecessor orders or model rules.
fn mraw_original_program(
  events : Array[Json],
  tx : String,
  snapshot : Map[String, String],
  validate : Bool,
) -> Map[String, String]? {
  let mut own : Map[String, String] = Map([])
  let marks : Array[(String, Map[String, String])] = []
  for raw in events {
    let e = object_fields_unchecked_v3(raw)
    if e.get("tx") != Some(Json(tx)) {
      continue
    }
    let kind = e.at("kind")
    if kind == Json("write") {
      let key = capture_source_string_v4(e.at("key"))
      let expected = match own.get(key) {
        Some(v) => Some(v)
        None => snapshot.get(key)
      }
      if validate &&
        expected !=
        (match e.get("predecessor") {
          Some(String(v)) => Some(v)
          _ => None
        }) {
        return None
      }
      own[key] = capture_source_string_v4(e.at("version"))
    } else if kind == Json("read") {
      let key = capture_source_string_v4(e.at("key"))
      if validate &&
        (match own.get(key) {
          Some(v) => Some(v)
          None => snapshot.get(key)
        }) !=
        (match e.get("version") {
          Some(String(v)) => Some(v)
          _ => None
        }) {
        return None
      }
    } else if kind == Json("savepoint") {
      marks.push((capture_source_string_v4(e.at("instance")), own.copy()))
    } else if kind == Json("rollback_to") || kind == Json("release") {
      let id = capture_source_string_v4(e.at("instance"))
      let mut found = -1
      for i, mark in marks {
        if mark.0 == id {
          found = i
        }
      }
      if found < 0 {
        return None
      }
      if kind == Json("rollback_to") {
        own = marks[found].1.copy()
      }
      let keep = if kind == Json("rollback_to") { found + 1 } else { found }
      while marks.length() > keep {
        ignore(marks.pop())
      }
    } else if kind == Json("rollback_ok") {
      own = Map([])
      marks.clear()
    } else if kind != Json("begin") &&
      kind != Json("commit_request") &&
      kind != Json("commit_ok") &&
      kind != Json("disconnect") {
      return None
    }
  }
  Some(own)
}

///|
fn mraw_replay_original_certificate(
  document : Json,
  certificate : Json,
) -> Bool {
  let events = capture_source_array_v4(
    object_fields_unchecked_v3(document).at("events"),
  )
  let initial : Map[String, String] = Map([])
  let committed : Map[String, Bool] = Map([])
  for i, raw in events {
    let e = object_fields_unchecked_v3(raw)
    if e.at("seq") != Json(i + 1) {
      return false
    }
    if e.at("kind") == Json("snapshot") {
      for key, value in object_fields_unchecked_v3(e.at("initial")) {
        initial[key] = capture_source_string_v4(value)
      }
    }
    if e.at("kind") == Json("commit_ok") {
      committed[capture_source_string_v4(e.at("tx"))] = true
    }
  }
  let finals : Map[String, Map[String, String]] = Map([])
  for tx, _ in committed {
    match mraw_original_program(events, tx, initial, false) {
      Some(own) => finals[tx] = own
      None => return false
    }
  }
  let order : Array[String] = []
  let positions : Map[String, Int32] = Map([])
  for value in capture_source_array_v4(v4_test_at(certificate, ["commitOrder"])) {
    let tx = capture_source_string_v4(value)
    if !committed.contains(tx) || positions.contains(tx) {
      return false
    }
    positions[tx] = order.length()
    order.push(tx)
  }
  if positions.length() != committed.length() {
    return false
  }
  let seen : Map[String, Bool] = Map([])
  for
    raw in capture_source_array_v4(
      v4_test_at(certificate, ["visibilityPrefixes"]),
    ) {
    let tx = capture_source_string_v4(v4_test_at(raw, ["transaction"]))
    if !positions.contains(tx) || seen.contains(tx) {
      return false
    }
    seen[tx] = true
    let count = rcl_number(v4_test_at(raw, ["visiblePrefixLength"]))
    if count < 0 || count > positions.at(tx) {
      return false
    }
    let visible = capture_source_array_v4(
      v4_test_at(raw, ["visibleTransactions"]),
    )
    if visible.length() != count {
      return false
    }
    let snapshot = initial.copy()
    for i in 0..<count {
      if visible[i] != Json(order[i]) {
        return false
      }
      for key, value in finals.at(order[i]) {
        snapshot[key] = value
      }
    }
    if mraw_original_program(events, tx, snapshot, true) is None {
      return false
    }
  }
  seen.length() == committed.length()
}

///|
fn mraw_key_read(tx : String, key : String, version : String) -> Json {
  { "kind": "read", "tx": Json(tx), "key": Json(key), "version": Json(version) }
}

///|
fn mraw_key_write(
  tx : String,
  key : String,
  version : String,
  predecessor : String,
) -> Json {
  {
    "kind": "write",
    "tx": Json(tx),
    "key": Json(key),
    "version": Json(version),
    "predecessor": Json(predecessor),
  }
}

///|
fn mraw_corpus_history(seed : Int32) -> HistoryV4 {
  if seed % 5 == 3 {
    let a = "A" + seed.to_string()
    let b = "B" + seed.to_string()
    let x = "x" + seed.to_string() + "v1"
    let y = "y" + seed.to_string() + "v1"
    let body = [
      raw5_begin(a),
      raw5_begin(b),
      raw5_read(a, "x0"),
      mraw_key_read(b, "y", "y0"),
      mraw_key_write(a, "y", y, "y0"),
      raw5_write(b, x, "x0"),
      mraw_key_read(a, "y", y),
      raw5_read(b, x),
    ]
    raw5_commit(body, a)
    raw5_commit(body, b)
    return mraw_history(body)
  }
  let body : Array[Json] = []
  let state : Map[String, String] = { "x": "x0", "y": "y0" }
  for ti in 0..<3 {
    let id = "T" + ti.to_string()
    let key = if (seed + ti) % 2 == 0 { "x" } else { "y" }
    let other = if key == "x" { "y" } else { "x" }
    let base = state.at(key)
    let first = "v" + seed.to_string() + "t" + ti.to_string() + "a"
    let last = "v" + seed.to_string() + "t" + ti.to_string() + "b"
    body.push(raw5_begin(id))
    body.push(mraw_key_read(id, key, base))
    body.push(mraw_key_read(id, other, state.at(other)))
    if seed % 5 == 1 {
      body.push({
        "kind": "savepoint",
        "tx": Json(id),
        "name": "s",
        "instance": Json(id + "-s1"),
      })
      body.push(mraw_key_write(id, key, first, base))
      body.push(mraw_key_read(id, key, first))
      body.push({
        "kind": "rollback_to",
        "tx": Json(id),
        "instance": Json(id + "-s1"),
      })
      body.push(mraw_key_read(id, key, base))
      body.push(mraw_key_write(id, key, last, base))
      state[key] = last
    } else if seed % 5 == 2 {
      body.push(mraw_key_write(id, key, first, base))
      body.push(mraw_key_read(id, key, first))
      body.push(mraw_key_write(id, key, last, first))
      body.push(mraw_key_read(id, key, last))
      state[key] = last
    } else if seed % 5 == 4 && ti < 2 {
      body.push(mraw_key_read(id, key, base))
    } else {
      body.push(mraw_key_write(id, key, first, base))
      body.push(mraw_key_read(id, key, first))
      state[key] = first
    }
    raw5_commit(body, id)
  }
  mraw_history(body)
}

///|
test "raw register oracle 01 one thousand original captured programs replay their actual CO VIS certificates" {
  let unique : Map[String, Bool] = Map([])
  for seed in 0..<1000 {
    let history = mraw_corpus_history(seed)
    let original = history.source_text
    assert_false(unique.contains(original))
    unique[original] = true
    let facts = mraw_facts(history)
    let options = model_options_v4(models=[ElleSnapshotIsolation]).unwrap()
    let report = model_classification_v4_json(
      classify_models_v4(facts, options),
    )
    assert_eq(
      mct_status(report, ElleSnapshotIsolation),
      "checked-compatible",
      msg="seed " + seed.to_string(),
    )
    let certificate = v4_test_at(
      mct_rule(report, ElleSnapshotIsolation, "completion/Ext/data-only"),
      ["evidence"],
    )
    assert_true(
      mraw_replay_original_certificate(history.source_document, certificate),
      msg="original replay " + seed.to_string(),
    )
    assert_eq(
      v4_test_at(certificate, ["sourceProjection", "programEvents"]),
      object_fields_unchecked_v3(history.source_document).at("events"),
    )
  }
}

///|
test "raw register oracle 02 certificate replay rejects a tampered read visibility independently" {
  let history = mraw_corpus_history(1)
  let report = mraw_report(history, models=[ElleSnapshotIsolation])
  let certificate = v4_test_at(
    mct_rule(report, ElleSnapshotIsolation, "completion/Ext/data-only"),
    ["evidence"],
  )
  assert_true(
    mraw_replay_original_certificate(history.source_document, certificate),
  )
  let records = capture_source_array_v4(
    v4_test_at(certificate, ["visibilityPrefixes"]),
  )
  let last = records[records.length() - 1]
  object_fields_unchecked_v3(last)["visiblePrefixLength"] = Json(0)
  object_fields_unchecked_v3(last)["visibleTransactions"] = Json(
    ([] : Array[String]),
  )
  assert_false(
    mraw_replay_original_certificate(history.source_document, certificate),
  )
}
