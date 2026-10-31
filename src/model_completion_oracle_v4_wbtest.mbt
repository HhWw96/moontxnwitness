///|
/// A developer oracle over original register programs. It executes each program
/// against the emitted visible snapshot and checks write conflicts separately;
/// it does not import the author's graph, Ext builder or source-status results.
fn mci_replay_prefix_certificate(history : History, certificate : Json) -> Bool {
  let fields = object_fields_unchecked_v3(certificate)
  let committed = history.transactions.filter(tx => tx.status == Committed)
  let original : Map[String, Transaction] = Map([])
  let finals : Map[String, Map[String, String]] = Map([])
  for tx in committed {
    original[tx.id] = tx
    let writes : Map[String, String] = Map([])
    for op in tx.ops {
      if op.kind == Write {
        writes[op.key] = op.version
      }
    }
    finals[tx.id] = writes
  }
  let co : Array[String] = []
  let co_rank : Map[String, Int32] = Map([])
  for raw in capture_source_array_v4(fields.at("commitOrder")) {
    match raw {
      String(tx) if original.contains(tx) && !co_rank.contains(tx) => {
        co_rank[tx] = co.length()
        co.push(tx)
      }
      _ => return false
    }
  }
  if co.length() != committed.length() {
    return false
  }
  let snapshots : Map[String, Array[String]] = Map([])
  for raw in capture_source_array_v4(fields.at("visibilityPrefixes")) {
    let record = object_fields_unchecked_v3(raw)
    let tx = match record.at("transaction") {
      String(id) => id
      _ => return false
    }
    if !co_rank.contains(tx) || snapshots.contains(tx) {
      return false
    }
    let count = capture_source_seq_v4(record.at("visiblePrefixLength")).to_int()
    if count < 0 || count > co_rank.at(tx) {
      return false
    }
    let values = capture_source_array_v4(record.at("visibleTransactions"))
    if values.length() != count {
      return false
    }
    let visible : Array[String] = []
    for i in 0..<count {
      if values[i] != Json(co[i]) {
        return false
      }
      visible.push(co[i])
    }
    snapshots[tx] = visible
  }
  if snapshots.length() != committed.length() {
    return false
  }
  let versions : Map[String, Array[String]] = Map([])
  let owners : Map[String, Map[String, String]] = Map([])
  for key, init in history.initial {
    let written : Map[String, String] = Map([])
    for tx, writes in finals {
      match writes.get(key) {
        Some(v) => written[v] = tx
        _ => ()
      }
    }
    let order = match history.version_orders.get(key) {
      Some(order) => order.copy()
      None =>
        if written.length() <= 1 {
          let values = [init]
          values.append(written.keys().collect())
          values
        } else {
          return false
        }
    }
    if order.length() != written.length() + 1 || order[0] != init {
      return false
    }
    for i in 1..<order.length() {
      if !written.contains(order[i]) {
        return false
      }
      if i > 1 {
        let earlier = written.at(order[i - 1])
        let later = written.at(order[i])
        if co_rank.at(earlier) >= co_rank.at(later) ||
          !snapshots.at(later).contains(earlier) {
          return false
        }
      }
    }
    versions[key] = order
    owners[key] = written
  }
  for tx in committed {
    let state = history.initial.copy()
    let visible = snapshots.at(tx.id)
    for key, order in versions {
      let producer = owners.at(key)
      for i in 1..<order.length() {
        if visible.contains(producer.at(order[i])) {
          state[key] = order[i]
        }
      }
    }
    for op in tx.ops {
      if op.kind == Read {
        if state.get(op.key) != Some(op.version) {
          return false
        }
      } else {
        state[op.key] = op.version
      }
    }
  }
  true
}

///|
test "model completion oracle 01 two real transactions finish all fourteen required definitions" {
  let a : Transaction = {
    id: "A",
    status: Committed,
    ops: [
      read_op("x", "x0"),
      write_op("x", "x1"),
      read_op("y", "y0"),
      write_op("y", "y1"),
    ],
    start: Some(1L),
    end: Some(2L),
  }
  let b : Transaction = {
    id: "B",
    status: Committed,
    ops: [
      read_op("x", "x1"),
      write_op("x", "x2"),
      read_op("y", "y1"),
      write_op("y", "y2"),
    ],
    start: Some(3L),
    end: Some(4L),
  }
  let input = hist([a, b], orders={
    "x": ["x0", "x1", "x2"],
    "y": ["y0", "y1", "y2"],
  })
  let facts = mct_facts(
    input,
    clients=[{ id: "logical-client", transactions: ["A", "B"], }],
    clients_complete=true,
  )
  let report = mct_report(facts)
  for model in elle_core_models_v4() {
    assert_eq(mct_status(report, model), "checked-compatible")
    assert_true(
      capture_source_array_v4(
        object_fields_unchecked_v3(mct_model(report, model)).at("pendingRules"),
      ).is_empty(),
    )
  }
  for
    (model, context) in [
      (ElleSnapshotIsolation, "data-only"),
      (ElleSessionSnapshotIsolation, "process"),
      (ElleStrongSnapshotIsolation, "realtime"),
    ] {
    let certificate = object_fields_unchecked_v3(
      mct_rule(report, model, "completion/Ext/" + context),
    ).at("evidence")
    assert_true(mci_replay_prefix_certificate(input, certificate))
  }
}

///|
test "model completion oracle 02 256 two-key read-write histories independently replay every accepted SI certificate" {
  let mut accepted = 0
  let mut refuted = 0
  for writes in 0..<16 {
    for reads in 0..<16 {
      let awx = (writes & 1) != 0
      let awy = (writes & 2) != 0
      let bwx = (writes & 4) != 0
      let bwy = (writes & 8) != 0
      let aops = [
        read_op("x", if (reads & 1) != 0 && bwx { "bx" } else { "x0" }),
        read_op("y", if (reads & 2) != 0 && bwy { "by" } else { "y0" }),
      ]
      let bops = [
        read_op("x", if (reads & 4) != 0 && awx { "ax" } else { "x0" }),
        read_op("y", if (reads & 8) != 0 && awy { "ay" } else { "y0" }),
      ]
      if awx {
        aops.push(write_op("x", "ax"))
      }
      if awy {
        aops.push(write_op("y", "ay"))
      }
      if bwx {
        bops.push(write_op("x", "bx"))
      }
      if bwy {
        bops.push(write_op("y", "by"))
      }
      let x = ["x0"]
      let y = ["y0"]
      if awx {
        x.push("ax")
      }
      if bwx {
        x.push("bx")
      }
      if awy {
        y.push("ay")
      }
      if bwy {
        y.push("by")
      }
      let input = hist([tx("A", aops), tx("B", bops)], orders={ "x": x, "y": y })
      let report = mct_report(mct_facts(input), models=[ElleSnapshotIsolation])
      match mct_status(report, ElleSnapshotIsolation) {
        "checked-compatible" => {
          accepted += 1
          let certificate = object_fields_unchecked_v3(
            mct_rule(report, ElleSnapshotIsolation, "completion/Ext/data-only"),
          ).at("evidence")
          assert_true(mci_replay_prefix_certificate(input, certificate))
        }
        "refuted" => refuted += 1
        _ => assert_true(false)
      }
    }
  }
  assert_true(accepted > 0 && refuted > 0)
  assert_eq(accepted + refuted, 256)
}

///|
test "model completion oracle 03 a replay oracle rejects a plausible but false visibility prefix" {
  let input = skew()
  let report = mct_report(mct_facts(input), models=[ElleSnapshotIsolation])
  let certificate = v4_json_copy(
    object_fields_unchecked_v3(
      mct_rule(report, ElleSnapshotIsolation, "completion/Ext/data-only"),
    ).at("evidence"),
  )
  assert_true(mci_replay_prefix_certificate(input, certificate))
  let co = capture_source_array_v4(
    object_fields_unchecked_v3(certificate).at("commitOrder"),
  )
  let prefixes = capture_source_array_v4(
    object_fields_unchecked_v3(certificate).at("visibilityPrefixes"),
  )
  for raw in prefixes {
    let row = object_fields_unchecked_v3(raw)
    if row.at("transaction") == co[1] {
      row["visiblePrefixLength"] = Json(1)
      row["visibleTransactions"] = Json([co[0]])
    }
  }
  assert_false(mci_replay_prefix_certificate(input, certificate))
}
