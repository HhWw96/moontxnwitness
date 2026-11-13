///|
fn rps_scoped_snapshot_v4(graph : ScopedDependencyGraphV4) -> String {
  (
    {
      "record": scoped_dependency_graph_v4_json(graph),
      "nodes": Json(graph.nodes),
      "adjacency": Json(graph.adjacency),
      "indexedEdges": Json(
        graph.edges.map(edge => {
          (
            {
              "id": Json(edge.id),
              "from": Json(edge.from),
              "to": Json(edge.to),
              "original": edge.original,
            } : Json)
        }),
      ),
    } : Json).stringify()
}

///|
fn rps_program_snapshot_v4(parsed : RelationV3Parsed) -> String {
  fn cell(value : RelationV3Cell) -> Json {
    match value {
      Integer(n) => { "int64": Json(n.to_string()) }
      Text(s) => { "text": Json(s) }
      Boolean(b) => { "bool": Json(b) }
    }
  }
  fn row(value : RelationV3Row) -> Json {
    {
      "key": Json(value.key),
      "version": Json(value.version),
      "values": Json(value.values.map(cell)),
    }
  }
  (
    {
      "normalized": parsed.normalized,
      "initial": Json(parsed.initial),
      "keys": Json(
        parsed.keys.map(key => {
          (
            {
              "table": Json(key.table),
              "value": cell(key.value),
              "wire": key.wire,
            } : Json)
        }),
      ),
      "sources": Json(
        parsed.sources.map(source => {
          (
            {
              "row": row(source.row),
              "action": Json(source.action),
              "predecessor": relation_v3_optional_text(source.predecessor),
              "writer": relation_v3_optional_text(source.writer),
              "seq": Json(source.seq.to_string()),
            } : Json)
        }),
      ),
      "programs": Json(
        parsed.programs.map(program => {
          let actions = program.actions.map(action => {
            match action {
              WriteRow(index) => ({ "write": Json(index) } : Json)
              QueryRows(table, predicates, rows, seq) =>
                {
                  "query": Json(table),
                  "seq": Json(seq.to_string()),
                  "rows": Json(rows.map(row)),
                  "predicate": Json(
                    predicates.map(term => {
                      (
                        {
                          "column": Json(term.column),
                          "op": Json(term.op),
                          "value": cell(term.value),
                        } : Json)
                    }),
                  ),
                }
              Mark(instance) => { "mark": Json(instance) }
              Undo(instance) => { "undo": Json(instance) }
              Release(instance) => { "release": Json(instance) }
            }
          })
          (
            {
              "id": Json(program.id),
              "status": Json(
                match program.status {
                  Committed => "committed"
                  Aborted => "aborted"
                  Unknown => "unknown"
                },
              ),
              "actions": Json(actions),
            } : Json)
        }),
      ),
      "findings": Json(parsed.findings),
      "sourceEvidence": Json(parsed.source_evidence),
      "operations": Json(parsed.operations),
    } : Json).stringify()
}

///|
fn rps_families_v4() -> Array[HistoryV4] {
  let saved = rpg_rollback_body()
  saved.push(rpg_begin("B"))
  saved.push(rpg_write("B", "2", "removed", Some("u0"), action="delete"))
  saved.push(rpg_read("B", "2", None))
  saved.push(
    rpg_write("B", "2", "reinserted", Some("removed"), action="insert"),
  )
  saved.push(rpg_read("B", "2", Some("reinserted")))
  rpg_commit(saved, "B")
  [
    rpred_history(saved),
    rpred_history(rmt_changing_query()),
    rpred_history(rpg_skew_body()),
    rpred_history(rmt_stale_external()),
    rpred_history(rcl_direct_body("G1a")),
  ]
}

///|
test "relation shared graph 01 each projection reads an immutable full original graph" {
  for history in rps_families_v4() {
    let parsed = match history.payload {
      RelationSnapshot(parsed) => parsed
      _ => abort("relation fixture")
    }
    let parsed_before = rps_program_snapshot_v4(parsed)
    let options = model_options_v4(models=elle_core_models_v4()).unwrap()
    let facts = model_facts_v4(history).unwrap()
    let predicate = build_relation_predicate_graph_v4(history).unwrap()
    let source = model_other_source_v4(history, options)
    let orders = model_orders_v4(facts, source, options.max_source_checks)
    let shared = relation_predicate_scoped_graph_v4(predicate).unwrap()
    let before = rps_scoped_snapshot_v4(shared)
    for model in elle_core_models_v4() {
      let projection = if model == ElleRepeatableRead {
        "D-item-mixed"
      } else {
        model_projection_v4(model)
      }
      let context = model_context_v4(model)
      let cached = rm_graph_rule_v4(
        predicate, shared, source, orders, projection, context, options,
      )
      let separate = rm_graph_rule_v4(
        predicate,
        relation_predicate_scoped_graph_v4(predicate).unwrap(),
        source,
        orders,
        projection,
        context,
        options,
      )
      assert_eq(cached.evidence.stringify(), separate.evidence.stringify())
      assert_eq(cached.status, separate.status)
      assert_eq(rps_scoped_snapshot_v4(shared), before)
    }
    assert_eq(rps_program_snapshot_v4(parsed), parsed_before)
  }
}

///|
test "relation shared graph 02 separate rule budgets retain exact bytes on the shared graph" {
  let history = rpred_history(rpg_skew_body())
  let predicate = build_relation_predicate_graph_v4(history).unwrap()
  let shared = relation_predicate_scoped_graph_v4(predicate).unwrap()
  let before = rps_scoped_snapshot_v4(shared)
  for maximum in [0, 1, 4, 100000] {
    let options = model_options_v4(
      models=elle_core_models_v4(),
      max_states=maximum,
      max_edge_checks=maximum,
    ).unwrap()
    let source = model_other_source_v4(history, options)
    let orders = model_orders_v4(
      model_facts_v4(history).unwrap(),
      source,
      options.max_source_checks,
    )
    for projection in ["W", "I", "D-item-mixed", "D", "Ext(I,A)", "G-single"] {
      let cached = rm_graph_rule_v4(
        predicate,
        shared,
        source,
        orders,
        projection,
        ScopedDataOnly,
        options,
      )
      let separate = rm_graph_rule_v4(
        predicate,
        relation_predicate_scoped_graph_v4(predicate).unwrap(),
        source,
        orders,
        projection,
        ScopedDataOnly,
        options,
      )
      assert_eq(cached.evidence.stringify(), separate.evidence.stringify())
      assert_eq(rps_scoped_snapshot_v4(shared), before)
    }
  }
}

///|
test "relation shared graph 03 original completion programs are unchanged across full model calls" {
  for history in rps_families_v4() {
    let parsed = match history.payload {
      RelationSnapshot(parsed) => parsed
      _ => abort("relation fixture")
    }
    let before = rps_program_snapshot_v4(parsed)
    let facts = model_facts_v4(history).unwrap()
    let options = model_options_v4(models=elle_core_models_v4()).unwrap()
    for realtime_known in [true, false] {
      let first = relation_model_classification_v4_json(
        classify_relation_models_v4(facts, options, realtime_known~).unwrap(),
      ).stringify()
      assert_eq(rps_program_snapshot_v4(parsed), before)
      let second = relation_model_classification_v4_json(
        classify_relation_models_v4(facts, options, realtime_known~).unwrap(),
      ).stringify()
      assert_eq(first, second)
      assert_eq(rps_program_snapshot_v4(parsed), before)
    }
  }
}
