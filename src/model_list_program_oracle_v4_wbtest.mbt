///|
/// Developer oracle over original append events only. No graph, normalized
/// program, inferred version order or model status is used by this interpreter.
fn mlpo_copy(state : Map[String, Array[Json]]) -> Map[String, Array[Json]] {
  let out : Map[String, Array[Json]] = Map([])
  for key, items in state {
    out[key] = items.copy()
  }
  out
}

///|
fn mlpo_program(
  events : Array[Json],
  tx : String,
  snapshot : Map[String, Array[Json]],
  validate : Bool,
) -> Map[String, Array[Json]]? {
  let mut state = mlpo_copy(snapshot)
  let scopes : Array[(String, Map[String, Array[Json]])] = []
  for raw in events {
    let e = object_fields_unchecked_v3(raw)
    if e.get("tx") != Some(Json(tx)) {
      continue
    }
    let kind = e.at("kind")
    if kind == Json("append") {
      let key = capture_source_string_v4(e.at("key"))
      if !state.contains(key) {
        return None
      }
      let items = state.at(key).copy()
      items.push({ "id": e.at("id"), "value": e.at("value") })
      state[key] = items
    } else if kind == Json("list_read") {
      let key = capture_source_string_v4(e.at("key"))
      if !state.contains(key) {
        return None
      }
      if validate && Json(state.at(key)) != e.at("items") {
        return None
      }
    } else if kind == Json("savepoint") {
      scopes.push(
        (capture_source_string_v4(e.at("instance")), mlpo_copy(state)),
      )
    } else if kind == Json("rollback_to") || kind == Json("release") {
      let instance = capture_source_string_v4(e.at("instance"))
      let mut found = -1
      for i, scope in scopes {
        if scope.0 == instance {
          found = i
        }
      }
      if found < 0 {
        return None
      }
      if kind == Json("rollback_to") {
        state = mlpo_copy(scopes[found].1)
      }
      let keep = if kind == Json("rollback_to") { found + 1 } else { found }
      while scopes.length() > keep {
        ignore(scopes.pop())
      }
    } else if kind != Json("begin") &&
      kind != Json("commit_request") &&
      kind != Json("commit_ok") {
      return None
    }
  }
  Some(state)
}

///|
fn mlpo_replay(document : Json, certificate : Json) -> Bool {
  let root = object_fields_unchecked_v3(document)
  let events = capture_source_array_v4(root.at("events"))
  let initial : Map[String, Array[Json]] = Map([])
  let committed : Map[String, Bool] = Map([])
  let begun : Map[String, Bool] = Map([])
  let supported = [
    "snapshot", "begin", "append", "list_read", "savepoint", "rollback_to", "release",
    "commit_request", "commit_ok",
  ]
  for i, raw in events {
    let e = object_fields_unchecked_v3(raw)
    if e.at("seq") != Json(i + 1) ||
      !supported.contains(capture_source_string_v4(e.at("kind"))) {
      return false
    }
    if e.at("kind") == Json("snapshot") {
      if e.get("consistent") != Some(Json(true)) {
        return false
      }
      for key, items in object_fields_unchecked_v3(e.at("initial")) {
        initial[key] = capture_source_array_v4(items).copy()
      }
    } else {
      let tx = capture_source_string_v4(e.at("tx"))
      if e.at("kind") == Json("begin") {
        if begun.contains(tx) {
          return false
        }
        begun[tx] = true
      } else if !begun.contains(tx) || committed.contains(tx) {
        return false
      }
      if e.at("kind") == Json("commit_ok") {
        committed[tx] = true
      }
    }
  }
  if initial.is_empty() || committed.length() != begun.length() {
    return false
  }
  let empty : Map[String, Array[Json]] = Map([])
  for key, _ in initial {
    empty[key] = []
  }
  let deltas : Map[String, Map[String, Array[Json]]] = Map([])
  for tx, _ in committed {
    match mlpo_program(events, tx, empty, false) {
      Some(delta) => deltas[tx] = delta
      None => return false
    }
  }
  let order : Array[String] = []
  let positions : Map[String, Int32] = Map([])
  for raw in capture_source_array_v4(v4_test_at(certificate, ["commitOrder"])) {
    let tx = capture_source_string_v4(raw)
    if !committed.contains(tx) || positions.contains(tx) {
      return false
    }
    positions[tx] = order.length()
    order.push(tx)
  }
  if order.length() != committed.length() {
    return false
  }
  let prefixes : Map[String, Int32] = Map([])
  for
    row in capture_source_array_v4(
      v4_test_at(certificate, ["visibilityPrefixes"]),
    ) {
    let tx = capture_source_string_v4(v4_test_at(row, ["transaction"]))
    let count = rcl_number(v4_test_at(row, ["visiblePrefixLength"]))
    if !positions.contains(tx) ||
      prefixes.contains(tx) ||
      count < 0 ||
      count > positions.at(tx) {
      return false
    }
    let visible = capture_source_array_v4(
      v4_test_at(row, ["visibleTransactions"]),
    )
    if visible.length() != count {
      return false
    }
    for i in 0..<count {
      if visible[i] != Json(order[i]) {
        return false
      }
    }
    prefixes[tx] = count
  }
  if prefixes.length() != committed.length() {
    return false
  }
  for ti, tx in order {
    let snapshot = mlpo_copy(initial)
    for i in 0..<prefixes.at(tx) {
      for key, items in deltas.at(order[i]) {
        let full = snapshot.at(key).copy()
        full.append(items)
        snapshot[key] = full
      }
    }
    if mlpo_program(events, tx, snapshot, true) is None {
      return false
    }
    // Concurrent committed appenders of the same key are forbidden by SI.
    for previous in 0..<ti {
      let earlier = order[previous]
      for key, items in deltas.at(tx) {
        if !items.is_empty() &&
          !deltas.at(earlier).at(key).is_empty() &&
          prefixes.at(tx) <= previous {
          return false
        }
      }
    }
  }
  true
}

///|
priv struct MLPOSearch {
  maximum : Int32
  mut checks : Int32
  mut limited : Bool
  mut unsupported : Bool
  mut certificate : Json?
}

///|
fn mlpo_prefix_choices(
  document : Json,
  order : Array[String],
  at : Int32,
  rows : Array[Json],
  search : MLPOSearch,
) -> Unit {
  if search.certificate is Some(_) || search.limited {
    return
  }
  if at == order.length() {
    if search.checks >= search.maximum {
      search.limited = true
      return
    }
    search.checks += 1
    let certificate : Json = {
      "commitOrder": Json(order),
      "visibilityPrefixes": Json(rows),
    }
    if mlpo_replay(document, certificate) {
      search.certificate = Some(v4_json_copy(certificate))
    }
    return
  }
  for count in 0..<(at + 1) {
    let visible : Array[String] = []
    for i in 0..<count {
      visible.push(order[i])
    }
    rows.push({
      "transaction": Json(order[at]),
      "visiblePrefixLength": Json(count),
      "visibleTransactions": Json(visible),
    })
    mlpo_prefix_choices(document, order, at + 1, rows, search)
    ignore(rows.pop())
    if search.certificate is Some(_) || search.limited {
      return
    }
  }
}

///|
fn mlpo_orders(
  document : Json,
  remaining : Array[String],
  prefix : Array[String],
  search : MLPOSearch,
) -> Unit {
  if search.certificate is Some(_) || search.limited {
    return
  }
  if remaining.is_empty() {
    mlpo_prefix_choices(document, prefix, 0, [], search)
    return
  }
  for tx in remaining {
    prefix.push(tx)
    mlpo_orders(document, remaining.filter(id => id != tx), prefix, search)
    ignore(prefix.pop())
    if search.certificate is Some(_) || search.limited {
      return
    }
  }
}

///|
fn mlpo_solve(document : Json, maximum~ : Int32 = 128) -> MLPOSearch {
  let txs : Array[String] = []
  for raw in capture_source_array_v4(v4_test_at(document, ["events"])) {
    let e = object_fields_unchecked_v3(raw)
    if e.at("kind") == Json("begin") {
      txs.push(capture_source_string_v4(e.at("tx")))
    }
  }
  txs.sort()
  let search : MLPOSearch = {
    maximum,
    checks: 0,
    limited: false,
    unsupported: false,
    certificate: None,
  }
  let supported = [
    "snapshot", "begin", "append", "list_read", "savepoint", "rollback_to", "release",
    "commit_request", "commit_ok",
  ]
  let root = object_fields_unchecked_v3(document)
  let events = capture_source_array_v4(root.at("events"))
  let committed : Map[String, Bool] = Map([])
  if root.get("dataModel") != Some(Json("append-list-v1")) ||
    !capture_source_array_v4(root.get_or_default("gaps", Json::null())).is_empty() {
    search.unsupported = true
    return search
  }
  for i, raw in events {
    let e = object_fields_unchecked_v3(raw)
    if e.at("seq") != Json(i + 1) ||
      !supported.contains(capture_source_string_v4(e.at("kind"))) {
      search.unsupported = true
      return search
    }
    if e.at("kind") == Json("commit_ok") {
      committed[capture_source_string_v4(e.at("tx"))] = true
    }
  }
  if committed.length() != txs.length() {
    search.unsupported = true
    return search
  }
  if txs.length() > 3 {
    search.limited = true
    return search
  }
  mlpo_orders(document, txs, [], search)
  search
}

///|
fn mlpo_read(tx : String, key : String, items : Array[Json]) -> Json {
  {
    "kind": "list_read",
    "tx": Json(tx),
    "key": Json(key),
    "items": Json(items.copy()),
  }
}

///|
fn mlpo_append(tx : String, key : String, id : String) -> Json {
  leg_test_append(tx, id, key~)
}

///|
fn mlpo_item(id : String) -> Json {
  { "id": Json(id), "value": "same" }
}

///|
fn mlpo_history(seed : Int32) -> HistoryV4 {
  let suffix = seed.to_string()
  let body : Array[Json] = []
  if seed % 5 == 3 {
    let a = "A" + suffix
    let b = "B" + suffix
    let a1 = "a1-" + suffix
    let a2 = "a2-" + suffix
    let b1 = "b1-" + suffix
    let b2 = "b2-" + suffix
    body.append([
      leg_test_begin(a),
      leg_test_begin(b),
      mlpo_read(a, "y", []),
      mlpo_read(b, "x", []),
      mlpo_append(a, "x", a1),
      mlpo_read(a, "x", [mlpo_item(a1)]),
      mlpo_append(a, "x", a2),
      mlpo_read(a, "x", [mlpo_item(a1), mlpo_item(a2)]),
      mlpo_append(b, "y", b1),
      mlpo_read(b, "y", [mlpo_item(b1)]),
      mlpo_append(b, "y", b2),
      mlpo_read(b, "y", [mlpo_item(b1), mlpo_item(b2)]),
    ])
    leg_test_commit(body, a)
    leg_test_commit(body, b)
  } else if seed % 5 == 4 {
    let w = "W" + suffix
    let a = "A" + suffix
    let y = "y-" + suffix
    let wx = "w-" + suffix
    let temp = "temp-" + suffix
    let mark = a + "-s"
    body.append([
      leg_test_begin(w),
      mlpo_append(w, "y", y),
      mlpo_append(w, "x", wx),
    ])
    leg_test_commit(body, w)
    body.append([
      leg_test_begin(a),
      mlpo_read(a, "y", [mlpo_item(y)]),
      {
        "kind": "savepoint",
        "tx": Json(a),
        "name": "same",
        "instance": Json(mark),
      },
      mlpo_append(a, "x", temp),
      mlpo_read(a, "x", [mlpo_item(wx), mlpo_item(temp)]),
      { "kind": "rollback_to", "tx": Json(a), "instance": Json(mark) },
    ])
    leg_test_commit(body, a)
  } else {
    let state : Map[String, Array[Json]] = { "x": [], "y": [] }
    for ti in 0..<3 {
      let tx = "T" + suffix + "-" + ti.to_string()
      let key = if (seed + ti) % 2 == 0 { "x" } else { "y" }
      let other = if key == "x" { "y" } else { "x" }
      let first = tx + "-first"
      let last = tx + "-last"
      let temp = tx + "-temp"
      let mark = tx + "-s"
      body.append([
        leg_test_begin(tx),
        mlpo_read(tx, key, state.at(key)),
        mlpo_read(tx, other, state.at(other)),
      ])
      let base = state.at(key).copy()
      if seed % 5 == 2 && ti == 1 {
        let own = base.copy()
        own.push(mlpo_item(temp))
        body.append([
          {
            "kind": "savepoint",
            "tx": Json(tx),
            "name": "same",
            "instance": Json(mark),
          },
          mlpo_append(tx, key, temp),
          mlpo_read(tx, key, own),
          { "kind": "rollback_to", "tx": Json(tx), "instance": Json(mark) },
        ])
      } else {
        let own = base.copy()
        own.push(mlpo_item(first))
        body.append([mlpo_append(tx, key, first), mlpo_read(tx, key, own)])
        if seed % 5 == 1 {
          let temporary = own.copy()
          temporary.push(mlpo_item(temp))
          body.append([
            {
              "kind": "savepoint",
              "tx": Json(tx),
              "name": "same",
              "instance": Json(mark),
            },
            mlpo_append(tx, key, temp),
            mlpo_read(tx, key, temporary),
            { "kind": "rollback_to", "tx": Json(tx), "instance": Json(mark) },
            mlpo_read(tx, key, own),
          ])
        }
        own.push(mlpo_item(last))
        body.append([mlpo_append(tx, key, last), mlpo_read(tx, key, own)])
        state[key] = own
      }
      leg_test_commit(body, tx)
    }
  }
  if seed % 4 == 0 {
    let mut changed = false
    for i in 0..<(body.length() - 1) {
      let event = object_fields_unchecked_v3(body[i])
      let next = object_fields_unchecked_v3(body[i + 1])
      if !changed &&
        event.at("kind") == Json("append") &&
        next.at("kind") == Json("list_read") &&
        event.at("tx") == next.at("tx") &&
        event.at("key") == next.at("key") {
        next["items"] = Json(([] : Array[Json]))
        changed = true
      }
    }
    if !changed {
      abort("negative corpus case has no own-read target")
    }
  }
  mlp_history(body)
}

///|
test "list program oracle 01 archived false SI prefix certificate fails original append semantics" {
  let h = mlp_history(mlp_revoked_cross_key_body())
  let old : Json = {
    "commitOrder": ["W", "A"],
    "visibilityPrefixes": [
      {
        "transaction": "W",
        "visiblePrefixLength": 0,
        "visibleTransactions": [],
      },
      {
        "transaction": "A",
        "visiblePrefixLength": 1,
        "visibleTransactions": ["W"],
      },
    ],
  }
  assert_false(mlpo_replay(h.source_document, old))
  let result = mlpo_solve(h.source_document)
  assert_false(result.limited)
  assert_true(result.certificate is None)
}

///|
test "list program oracle 02 one thousand distinct original histories agree with finite SI interpretation" {
  let seen : Map[String, Bool] = Map([])
  let mut accepted = 0
  let mut rejected = 0
  for seed in 0..<1000 {
    let h = mlpo_history(seed)
    assert_false(seen.contains(h.source_text))
    seen[h.source_text] = true
    let oracle = mlpo_solve(h.source_document)
    assert_false(oracle.limited, msg="oracle budget " + seed.to_string())
    assert_false(
      oracle.unsupported,
      msg="unsupported corpus " + seed.to_string(),
    )
    let report = mlp_model_report(model_facts_v4(h).unwrap(), models=[
      ElleSnapshotIsolation,
    ])
    if oracle.certificate is Some(cert) {
      accepted += 1
      assert_true(mlpo_replay(h.source_document, cert))
      assert_eq(
        mct_status(report, ElleSnapshotIsolation),
        "checked-compatible",
        msg="compatible seed " + seed.to_string() + ": " + report.stringify(),
      )
      let certificate = v4_test_at(
        mct_rule(report, ElleSnapshotIsolation, "completion/Ext/data-only"),
        ["evidence"],
      )
      assert_true(
        mlpo_replay(h.source_document, certificate),
        msg="model prefix replay " + seed.to_string(),
      )
    } else {
      rejected += 1
      assert_eq(
        mct_status(report, ElleSnapshotIsolation),
        "refuted",
        msg="incompatible seed " + seed.to_string() + ": " + report.stringify(),
      )
    }
  }
  assert_eq(accepted, 750)
  assert_eq(rejected, 250)
}

///|
test "list program oracle 03 candidate budget exhaustion is not an unsatisfiability proof" {
  let h = mlpo_history(0)
  let none = mlpo_solve(h.source_document, maximum=0)
  assert_true(none.limited)
  assert_eq(none.checks, 0)
  let full = mlpo_solve(h.source_document)
  assert_false(full.limited)
  assert_true(full.certificate is None)
  let exact = mlpo_solve(h.source_document, maximum=full.checks)
  assert_false(exact.limited)
  let short = mlpo_solve(h.source_document, maximum=full.checks - 1)
  assert_true(short.limited)
}

///|
test "list program oracle 04 unsupported or incomplete programs are never declared unsatisfiable" {
  let raw = classification26_test_list(mlp_multi())
  let events = capture_source_array_v4(v4_test_at(raw, ["events"]))
  let changed = object_fields_unchecked_v3(events[3])
  changed["kind"] = Json("statement")
  changed["sql"] = Json("unknown SQL")
  let unknown = mlpo_solve(raw)
  assert_true(unknown.unsupported)
  assert_eq(unknown.checks, 0)
  assert_true(unknown.certificate is None)
  let hole = classification26_test_list(mlp_multi())
  let keep = capture_source_array_v4(v4_test_at(hole, ["events"])).filter(e => {
    v4_test_at(e, ["seq"]) != Json(3)
  })
  object_fields_unchecked_v3(hole)["events"] = Json(keep)
  assert_true(mlpo_solve(hole).unsupported)
}

///|
test "list program oracle 05 production typed replay independently rejects the archived invalid prefix" {
  let h = mlp_history(mlp_revoked_cross_key_body())
  let parsed = match h.payload {
    ListSnapshot(p) => p
    _ => abort("list required")
  }
  let rows : Array[Json] = [
    { "transaction": "W", "visiblePrefixLength": 0, "visibleTransactions": [] },
    {
      "transaction": "A",
      "visiblePrefixLength": 1,
      "visibleTransactions": ["W"],
    },
  ]
  assert_eq(
    model_list_certificate_replay_v4(parsed, ["W", "A"], rows, 1000000).status,
    "unknown",
  )
}

///|
test "list program oracle 06 RC permits changing external reads without requiring a single SI snapshot" {
  let body = [
    leg_test_begin("R"),
    leg_test_read("R", []),
    leg_test_begin("W"),
    leg_test_append("W", "a"),
  ]
  leg_test_commit(body, "W")
  body.push(leg_test_read("R", ["a"]))
  leg_test_commit(body, "R")
  let h = mlp_history(body)
  let oracle = mlpo_solve(h.source_document)
  assert_false(oracle.limited)
  assert_false(oracle.unsupported)
  assert_true(oracle.certificate is None)
  let standalone = internal_consistency_v4_json(
    inspect_internal_consistency_v4(h),
  )
  assert_eq(v4_test_at(standalone, ["status"]), Json("refuted"))
  let report = mlp_model_report(model_facts_v4(h).unwrap(), models=[
    ElleReadUncommitted,
    ElleReadCommitted,
    ElleRepeatableRead,
    ElleSnapshotIsolation,
  ])
  assert_eq(mct_status(report, ElleReadUncommitted), "checked-compatible")
  assert_eq(mct_status(report, ElleReadCommitted), "checked-compatible")
  assert_eq(mct_status(report, ElleRepeatableRead), "refuted")
  assert_eq(mct_status(report, ElleSnapshotIsolation), "refuted")
  assert_false(
    capture_source_array_v4(
      v4_test_at(mct_model(report, ElleReadCommitted), ["rules"]),
    ).any(r => v4_test_at(r, ["rule"]) == Json("literal/internal")),
  )
}
