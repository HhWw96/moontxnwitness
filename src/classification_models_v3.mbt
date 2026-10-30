///|
priv struct ClassificationModelV3Options {
  models : Array[String]
  category_options : ClassificationV3Options
  normalization_options : Json
}

///|
priv struct ClassificationModelV3Graph {
  normalized : Json
  transactions : Array[Transaction]
  edges : Array[Edge]
  sources : Map[Edge, Array[Json]]
  validity_gaps : Array[Json]
  history : History?
  list_parsed : ListV3Parsed?
  complete : Bool
  mut reason : String
}

///|
fn classification_models_v3_names() -> Array[String] {
  [
    "adya-pl-1-v1", "adya-pl-2-v1", "adya-pl-2.99-v1", "elle-generalized-si-v1",
    "adya-pl-3-v1", "strict-pl-ss-v1",
  ]
}

///|
fn classification_models_v3_requested(
  text : String,
  options_text : String,
) -> Bool {
  try {
    let options = object_fields(
      guarded_json(options_text, limit=8192),
      "model options",
    )
    if options.contains("models") {
      return true
    }
    let root = object_fields(
      guarded_json(text, limit=33554432),
      "classification source",
    )
    root.get("format") == Some(Json("moontxnwitness-classification-source/v1"))
  } catch {
    _ => false
  }
}

///|
fn classification_models_v3_options(
  text : String,
) -> ClassificationModelV3Options raise {
  let fields = object_fields(
    guarded_json(text, limit=8192),
    "model classification options",
  )
  known_fields(
    fields,
    ["models", "maxStates", "maxEdgeChecks", "normalizationOptions"],
    "model classification options",
  )
  let models = match fields.get("models") {
    None => classification_models_v3_names()
    Some(Array(items)) => {
      let result : Array[String] = []
      for item in items {
        let name = identifier(item, "model definition")
        if !classification_models_v3_names().contains(name) ||
          result.contains(name) {
          fail("Unknown or duplicate isolation model definition")
        }
        result.push(name)
      }
      if result.is_empty() {
        fail("At least one isolation model is required")
      }
      result
    }
    _ => fail("models must be an array")
  }
  let category_fields : Map[String, Json] = Map([])
  for key in ["maxStates", "maxEdgeChecks"] {
    match fields.get(key) {
      Some(value) => category_fields[key] = value
      None => ()
    }
  }
  let normalization_options = fields.get_or_default(
    "normalizationOptions",
    Json::object(Map([])),
  )
  let normalization_fields = object_fields(
    normalization_options, "normalizationOptions",
  )
  known_fields(normalization_fields, ["sqlProof"], "normalizationOptions")
  let _ = v3_sql_proof_requested(normalization_fields)
  {
    models,
    category_options: classification_v3_options(
      Json::object(category_fields).stringify(),
    ),
    normalization_options,
  }
}

///|
fn classification_models_v3_options_json(
  options : ClassificationModelV3Options,
) -> Json {
  {
    "models": Json(options.models),
    "maxStates": Json(options.category_options.max_states),
    "maxEdgeChecks": Json(options.category_options.max_edge_checks),
    "normalizationOptions": options.normalization_options,
  }
}

///|
fn classification_models_v3_rule(
  status : String,
  reason : String,
  evidence : Json,
) -> Json {
  { "status": Json(status), "reason": Json(reason), "evidence": evidence }
}

///|
fn classification_models_v3_register(
  normalized : Json,
) -> ClassificationModelV3Graph raise {
  let result : ClassificationModelV3Graph = {
    normalized,
    transactions: [],
    edges: [],
    sources: Map([]),
    validity_gaps: [],
    history: None,
    list_parsed: None,
    complete: false,
    reason: "capture-coverage-or-required-version-order-incomplete",
  }
  let n = object_fields(normalized, "normalized")
  let observations = presence_capture_array(
    required(n, "observations", "normalized"),
    "observations",
  )
  let operation_count = observations
    .filter(raw => {
      let kind = object_fields_unchecked_v3(raw).get("kind")
      kind == Some(Json("read")) || kind == Some(Json("write"))
    })
    .length()
  let transaction_count = presence_capture_array(
    required(n, "transactions", "normalized"),
    "transactions",
  ).length()
  if transaction_count > 128 || operation_count > 4096 {
    result.reason = "register-classification-structure-limit"
    return result
  }
  if n.get("status") != Some(Json("ready")) {
    return result
  }
  let history = match
    parse_history_optimized(required(n, "history", "normalized").stringify()) {
    Ok(value) => value
    Err(message) => fail(message)
  }
  let report = analyze_internal(history, false, complete_search=false)
  let complete = !report.graph.edge_budget_exceeded &&
    !report.findings.any(f => {
      f.severity == "error" || f.severity == "uncertainty"
    })
  {
    ..result,
    transactions: history.transactions,
    edges: report.edges,
    history: Some(history),
    complete,
    reason: if complete {
      "complete-captured-version-orders"
    } else {
      "dependency-or-required-order-incomplete"
    },
  }
}

///|
fn classification_models_v3_add_list_edge(
  edges : Array[Edge],
  sources : Map[Edge, Array[Json]],
  edge : Edge,
  source : Json,
) -> Bool {
  if edge.from == edge.to {
    return true
  }
  match sources.get(edge) {
    Some(existing) => {
      if !existing.contains(source) {
        existing.push(source)
      }
      true
    }
    None => {
      if edges.length() >= 50000 {
        return false
      }
      edges.push(edge)
      sources[edge] = [source]
      true
    }
  }
}

///|
fn classification_models_v3_list_edge(
  from : String,
  to : String,
  kind : Dependency,
  key : String,
  first : String,
  last : String,
) -> Edge {
  {
    from,
    to,
    kind,
    key: Some(key),
    from_op: None,
    to_op: None,
    from_version: Some(first),
    to_version: Some(last),
    reason: match kind {
      WW =>
        "Complete ordered list observation orders these unique append identities"
      WR =>
        "The complete list read contains this unique committed append identity"
      _ => "The complete list read omits this committed append identity"
    },
  }
}

///|
fn classification_models_v3_list(
  text : String,
  normalized : Json,
) -> ClassificationModelV3Graph raise {
  let parsed = list_v3_parse(text)
  let within_direct_capacity = parsed.programs
    .filter(program => program.status == Committed)
    .length() <=
    6 &&
    parsed.operations <= 128
  let validity_gaps = if within_direct_capacity {
    classification_models_v3_list_validity(parsed)
  } else {
    []
  }
  let invalid_reads : Map[String, Bool] = Map([])
  for gap in validity_gaps {
    invalid_reads[object_fields_unchecked_v3(gap).at("readSeq").stringify()] = true
  }
  let result : ClassificationModelV3Graph = {
    normalized,
    transactions: [],
    edges: [],
    sources: Map([]),
    validity_gaps,
    history: None,
    list_parsed: Some(parsed),
    complete: false,
    reason: "list-profile-or-required-order-incomplete",
  }
  let events = presence_capture_array(
    required(
      object_fields(normalized, "normalized"),
      "observations",
      "normalized",
    ),
    "observations",
  )
  let committed = parsed.programs.filter(p => p.status == Committed)
  if committed.length() > 6 || parsed.operations > 128 {
    result.reason = "list-classification-exact-capacity-6-128"
    return result
  }
  let transactions : Array[Transaction] = []
  for program in parsed.programs {
    transactions.push({
      id: program.id,
      status: program.status,
      ops: [],
      start: None,
      end: None,
    })
  }
  let complete_capture = object_fields_unchecked_v3(normalized).get("status") ==
    Some(Json("ready"))
  if !complete_capture || !parsed.findings.is_empty() {
    return {
      ..result,
      transactions,
      reason: "list-source-facts-incomplete-or-direct-anomaly",
    }
  }
  if events.any(raw => {
      let kind = object_fields_unchecked_v3(raw).get("kind")
      kind == Some(Json("savepoint")) ||
      kind == Some(Json("rollback_to")) ||
      kind == Some(Json("release"))
    }) {
    return {
      ..result,
      transactions,
      reason: "list-classification-savepoints-not-supported",
    }
  }
  let outcomes : Map[String, TxStatus] = Map([])
  for program in parsed.programs {
    outcomes[program.id] = program.status
  }
  let ids : Map[String, Int32] = Map([])
  let active : Array[Int32] = []
  let per_tx_key : Map[String, Map[String, Bool]] = Map([])
  for index, item in parsed.items {
    ids[item.id] = index
    match item.tx {
      Some(tx) if outcomes.get(tx) == Some(Committed) => {
        let keys = per_tx_key.get_or_default(tx, Map([]))
        if keys.contains(item.key) {
          return {
            ..result,
            transactions,
            reason: "list-classification-multiple-appends-per-transaction-key-not-supported",
          }
        }
        keys[item.key] = true
        per_tx_key[tx] = keys
        active.push(index)
      }
      _ => ()
    }
  }
  let edges : Array[Edge] = []
  let sources : Map[Edge, Array[Json]] = Map([])
  let item_index : Map[Int32, Int32] = Map([])
  for index, item in active {
    item_index[item] = index
  }
  let order = Array::make(active.length() * active.length(), false)
  let mut operations = 0
  let mut complete = validity_gaps.is_empty()
  for raw in events {
    let fields = object_fields(raw, "event")
    if fields.get("kind") != Some(Json("list_read")) {
      continue
    }
    let reader = identifier(required(fields, "tx", "list_read"), "tx")
    if outcomes.get(reader) != Some(Committed) {
      continue
    }
    let key = identifier(required(fields, "key", "list_read"), "key")
    let read_seq = required(fields, "seq", "list_read")
    // Incomplete/invalid source observations never generate even partial edges.
    // Independent valid reads remain eligible for a reliable cycle witness.
    if invalid_reads.contains(read_seq.stringify()) {
      continue
    }
    let values = presence_capture_array(
      required(fields, "items", "list_read"),
      "items",
    )
    let observed : Array[Int32] = []
    for value in values {
      observed.push(
        ids.at(
          identifier(
            required(object_fields(value, "item"), "id", "item"),
            "item.id",
          ),
        ),
      )
    }
    let present : Map[Int32, Bool] = Map([])
    for index in observed {
      present[index] = true
    }
    for index in active {
      operations += 1
      if operations > 1000000 {
        return {
          ..result,
          transactions,
          edges,
          sources,
          reason: "list-dependency-construction-budget",
        }
      }
      let item = parsed.items[index]
      if item.key != key {
        continue
      }
      let writer = item.tx.unwrap()
      let edge = if present.contains(index) {
        classification_models_v3_list_edge(
          writer,
          reader,
          WR,
          key,
          item.id,
          item.id,
        )
      } else {
        classification_models_v3_list_edge(
          reader,
          writer,
          RW,
          key,
          "list-read-" + read_seq.stringify(),
          item.id,
        )
      }
      if !classification_models_v3_add_list_edge(edges, sources, edge, {
          "readSeq": read_seq,
          "appendSeq": Json(item.seq.to_double()),
          "itemId": Json(item.id),
        }) {
        complete = false
      }
    }
    for left in 0..<observed.length() {
      let first_index = observed[left]
      if !item_index.contains(first_index) {
        continue
      }
      let first = parsed.items[first_index]
      for right in (left + 1)..<observed.length() {
        operations += 1
        if operations > 1000000 {
          return {
            ..result,
            transactions,
            edges,
            sources,
            reason: "list-dependency-construction-budget",
          }
        }
        let last_index = observed[right]
        if !item_index.contains(last_index) {
          continue
        }
        let last = parsed.items[last_index]
        let a = item_index.at(first_index)
        let b = item_index.at(last_index)
        order[a * active.length() + b] = true
        let edge = classification_models_v3_list_edge(
          first.tx.unwrap(),
          last.tx.unwrap(),
          WW,
          key,
          first.id,
          last.id,
        )
        if !classification_models_v3_add_list_edge(edges, sources, edge, {
            "orderedByReadSeq": read_seq,
            "fromAppendSeq": Json(first.seq.to_double()),
            "toAppendSeq": Json(last.seq.to_double()),
            "fromItem": Json(first.id),
            "toItem": Json(last.id),
          }) {
          complete = false
        }
      }
    }
  }
  // Only observed list order is used. No transaction order or guessed append
  // order is inserted to make model checks finish.
  for middle in 0..<active.length() {
    for from in 0..<active.length() {
      for to in 0..<active.length() {
        if order[from * active.length() + middle] &&
          order[middle * active.length() + to] {
          order[from * active.length() + to] = true
        }
      }
    }
  }
  for a in 0..<active.length() {
    for b in (a + 1)..<active.length() {
      if parsed.items[active[a]].key == parsed.items[active[b]].key &&
        !order[a * active.length() + b] &&
        !order[b * active.length() + a] {
        complete = false
      }
    }
  }
  {
    ..result,
    transactions,
    edges,
    sources,
    complete,
    reason: if complete {
      "complete-observed-list-order"
    } else {
      "list-required-order-or-read-validity-incomplete"
    },
  }
}

///|
fn classification_models_v3_witness(
  graph : ClassificationModelV3Graph,
  cycle : Array[Edge],
) -> Json {
  match graph.history {
    Some(history) => {
      let result = classification_v3_witness(graph.normalized, history, cycle)
      object_fields_unchecked_v3(result)["realTimeSources"] = Json(
        cycle
        .filter(e => e.kind == RT)
        .map(edge => {
          (
            {
              "edge": edge_json(edge),
              "sources": Json(graph.sources.get_or_default(edge, [])),
            } : Json)
        }),
      )
      result
    }
    None =>
      {
        "kind": "source-checked-list-dependency-cycle",
        "edges": Json(
          cycle.map(edge => {
            (
              {
                "edge": edge_json(edge),
                "sources": Json(graph.sources.get_or_default(edge, [])),
              } : Json)
          }),
        ),
        "minimality": "simple cycle for the requested category; no shortest claim",
        "sourceScope": "explicit complete list observations and unique append identities; not SQL authenticity",
      }
  }
}

///|
fn classification_models_v3_direct(
  graph : ClassificationModelV3Graph,
  data_model : String,
) -> Map[String, Json] raise {
  let n = object_fields(graph.normalized, "normalized")
  let ready = n.get("status") == Some(Json("ready"))
  let result : Map[String, Json] = Map([])
  let capacity_exceeded = graph.reason ==
    "register-classification-structure-limit" ||
    graph.reason == "list-classification-exact-capacity-6-128"
  for name in ["G1a", "G1b", "INT"] {
    result[name] = classification_models_v3_rule(
      if ready && !capacity_exceeded {
        "checked-compatible"
      } else {
        "unknown"
      },
      if capacity_exceeded {
        graph.reason
      } else if ready {
        "complete-source-check"
      } else {
        "capture-coverage-incomplete"
      },
      Json::null(),
    )
  }
  if capacity_exceeded {
    return result
  }
  if n.get("status") == Some(Json("invalid")) {
    return result
  }
  if data_model == "append-list-v1" {
    match graph.list_parsed {
      Some(parsed) => {
        let invalid_reads : Map[String, Bool] = Map([])
        let source_mismatches : Map[String, Map[String, Bool]] = Map([])
        let by_item : Map[String, Int32] = Map([])
        for index, item in parsed.items {
          by_item[item.id] = index
        }
        for gap in graph.validity_gaps {
          invalid_reads[object_fields_unchecked_v3(gap)
          .at("readSeq")
          .stringify()] = true
        }
        for finding in parsed.findings {
          let fields = object_fields(finding, "list finding")
          if [
              Json("item_key_mismatch"),
              Json("item_value_mismatch"),
              Json("duplicate_list_item"),
            ].contains(fields.get_or_default("code", Json::null())) {
            let read_id = required(fields, "readSeq", "list finding").stringify()
            invalid_reads[read_id] = true
            if fields.get("code") != Some(Json("duplicate_list_item")) {
              let mismatches = source_mismatches.get_or_default(
                read_id,
                Map([]),
              )
              mismatches[identifier(
                required(fields, "itemId", "list finding"),
                "item identity",
              )] = true
              source_mismatches[read_id] = mismatches
            }
          }
        }
        if !invalid_reads.is_empty() {
          for name in ["G1a", "G1b", "INT"] {
            result[name] = classification_models_v3_rule(
              "unknown",
              "list-read-identity-value-or-initial-prefix-invalid",
              Json::null(),
            )
          }
        }
        for finding in parsed.findings {
          let fields = object_fields(finding, "list finding")
          let code = fields.get("code")
          if code == Some(Json("read_from_aborted_append")) {
            let read_seq = v3_capture_seq(
              required(fields, "readSeq", "list finding"),
              "read sequence",
            )
            let read_id = required(fields, "readSeq", "list finding").stringify()
            let item_id = identifier(
              required(fields, "itemId", "list finding"),
              "item identity",
            )
            match by_item.get(item_id) {
              Some(index) => {
                let item = parsed.items[index]
                if Json(item.key) == required(fields, "key", "list finding") &&
                  item.seq < read_seq &&
                  !source_mismatches
                  .get_or_default(read_id, Map([]))
                  .contains(item_id) {
                  result["G1a"] = classification_models_v3_rule(
                    "refuted",
                    "committed-list-read-from-aborted-append",
                    {
                      "finding": finding,
                      "source": parsed.source_evidence[index],
                      "writerOutcome": "aborted",
                      "applicability": "matching same-key unique item and value; independent of other list-shape gaps",
                    },
                  )
                }
              }
              None => ()
            }
          }
          if code == Some(Json("read_from_reverted_append")) {
            result["G1b"] = classification_models_v3_rule(
              "unknown", "reverted-list-effect-classification-not-supported", finding,
            )
          }
        }
        let unsupported_scopes = parsed.programs.any(program => {
          program.actions.any(action => {
            match action {
              Mark(_) | Undo(_) | Release(_) => true
              _ => false
            }
          })
        })
        if unsupported_scopes {
          result["G1b"] = classification_models_v3_rule(
            "unknown",
            "list-intermediate-savepoint-proof-not-supported",
            Json::null(),
          )
          result["INT"] = classification_models_v3_rule(
            "unknown",
            "list-internal-savepoint-proof-not-supported",
            Json::null(),
          )
        } else if ready {
          // A read fixes the full expected value. An append before any read
          // fixes only its suffix. This is the explicit list INT contract.
          for program in parsed.programs {
            if program.status != Committed {
              continue
            }
            let state : Map[String, Array[Int32]] = Map([])
            let full : Map[String, Bool] = Map([])
            for action in program.actions {
              match action {
                Append(key, item) => {
                  let current = state.get_or_default(key, []).copy()
                  current.push(item)
                  state[key] = current
                }
                ReadList(key, observed, seq) => {
                  if invalid_reads.contains(Json(seq.to_double()).stringify()) {
                    continue
                  }
                  match state.get(key) {
                    Some(expected) => {
                      let mut valid = observed.length() >= expected.length()
                      let offset = if full.get_or_default(key, false) {
                        if observed.length() != expected.length() {
                          valid = false
                        }
                        0
                      } else {
                        observed.length() - expected.length()
                      }
                      if valid {
                        for index, item in expected {
                          if observed[offset + index] != item {
                            valid = false
                            break
                          }
                        }
                      }
                      if !valid {
                        result["INT"] = classification_models_v3_rule(
                          "refuted",
                          "list-read-disagrees-with-most-recent-internal-state",
                          {
                            "tx": Json(program.id),
                            "readSeq": Json(seq.to_double()),
                            "expectedIds": Json(
                              expected.map(i => parsed.items[i].id),
                            ),
                            "expectedComplete": Json(
                              full.get_or_default(key, false),
                            ),
                            "observedIds": Json(
                              observed.map(i => parsed.items[i].id),
                            ),
                          },
                        )
                      }
                    }
                    None => ()
                  }
                  state[key] = observed.copy()
                  full[key] = true
                  // Append is a transformation of the entire list value. Only
                  // the actual last observed append identifies the read version;
                  // containing another writer's earlier item is not G1b.
                  if !observed.is_empty() {
                    let last = observed[observed.length() - 1]
                    if last >= 0 {
                      let last_item = parsed.items[last]
                      for producer in parsed.programs {
                        if last_item.tx != Some(producer.id) ||
                          producer.id == program.id ||
                          producer.status == Unknown {
                          continue
                        }
                        let produced : Array[Int32] = []
                        for producer_action in producer.actions {
                          match producer_action {
                            Append(producer_key, item) if producer_key == key =>
                              produced.push(item)
                            _ => ()
                          }
                        }
                        if produced.contains(last) &&
                          produced[produced.length() - 1] != last &&
                          last_item.seq < seq {
                          result["G1b"] = classification_models_v3_rule(
                            "refuted",
                            "external-list-read-ends-in-nonfinal-append",
                            {
                              "tx": Json(program.id),
                              "writer": Json(producer.id),
                              "readSeq": Json(seq.to_double()),
                              "lastObservedItem": Json(last_item.id),
                              "source": parsed.source_evidence[last],
                              "writerOutcome": Json(
                                if producer.status == Committed {
                                  "committed"
                                } else {
                                  "aborted"
                                },
                              ),
                              "writerFinalAppendIds": Json(
                                produced.map(i => parsed.items[i].id),
                              ),
                              "observedIds": Json(
                                observed.map(i => parsed.items[i].id),
                              ),
                              "applicability": "complete source-valid list value, actual last item from a confirmed external non-final same-key append",
                            },
                          )
                        }
                      }
                    }
                  }
                }
                _ => ()
              }
            }
          }
        }
        if graph.complete &&
          object_fields_unchecked_v3(result.at("G1b")).get("status") !=
          Some(Json("refuted")) {
          result["G1b"] = classification_models_v3_rule(
            "checked-compatible",
            "single-append-per-transaction-key-profile",
            Json::null(),
          )
        }
      }
      None => ()
    }
    return result
  }
  let coverage = object_fields(
    required(n, "coverage", "normalized"),
    "coverage",
  )
  let gaps = presence_capture_array(
    required(coverage, "gaps", "coverage"),
    "gaps",
  )
  // These gaps represent the very source/overlay anomalies checked here. Lost
  // records, an unproven writer scope or unmapped SQL cannot establish a proof.
  if gaps.any(gap => {
      let code = object_fields_unchecked_v3(gap).get("code")
      code != Some(Json("unsafe_read_source")) &&
      code != Some(Json("own_read_mismatch")) &&
      code != Some(Json("unsafe_write_source"))
    }) {
    return result
  }
  let effects = presence_capture_array(
    required(n, "effects", "normalized"),
    "effects",
  )
  let transactions = presence_capture_array(
    required(n, "transactions", "normalized"),
    "transactions",
  )
  let outcomes : Map[String, Json] = Map([])
  let finals : Map[String, Map[String, Bool]] = Map([])
  for raw in transactions {
    let tx = object_fields(raw, "transaction")
    let id = identifier(required(tx, "id", "transaction"), "id")
    outcomes[id] = required(tx, "status", "transaction")
    let versions : Map[String, Bool] = Map([])
    for
      seq in presence_capture_array(
        required(tx, "finalWrites", "transaction"),
        "finalWrites",
      ) {
      versions[seq.stringify()] = true
    }
    finals[id] = versions
  }
  let by_version : Map[String, Json] = Map([])
  let by_seq : Map[String, Json] = Map([])
  let revoked_at : Map[String, Array[Json]] = Map([])
  for effect in effects {
    let fields = object_fields(effect, "effect")
    by_version[identifier(required(fields, "version", "effect"), "version")] = effect
    by_seq[required(fields, "seq", "effect").stringify()] = effect
    match fields.get("revertedBy") {
      Some(value) if value != Json::null() => {
        let group = revoked_at.get_or_default(value.stringify(), [])
        group.push(effect)
        revoked_at[value.stringify()] = group
      }
      _ => ()
    }
  }
  let own_effects : Map[String, Map[String, Array[Json]]] = Map([])
  let external_reads : Map[String, Map[String, Json]] = Map([])
  for
    raw in presence_capture_array(
      required(n, "observations", "normalized"),
      "observations",
    ) {
    let read = object_fields(raw, "observation")
    if read.get("kind") == Some(Json("write")) {
      let tx = identifier(required(read, "tx", "write"), "tx")
      let key = identifier(required(read, "key", "write"), "key")
      let keys = own_effects.get_or_default(tx, Map([]))
      let stack = keys.get_or_default(key, [])
      stack.push(by_seq.at(required(read, "seq", "write").stringify()))
      keys[key] = stack
      own_effects[tx] = keys
      continue
    }
    if read.get("kind") == Some(Json("rollback_to")) {
      let group = revoked_at.get_or_default(
        required(read, "seq", "rollback").stringify(),
        [],
      )
      for index in 0..<group.length() {
        let effect = object_fields(
          group[group.length() - 1 - index],
          "revoked effect",
        )
        let tx = identifier(required(effect, "tx", "effect"), "tx")
        let key = identifier(required(effect, "key", "effect"), "key")
        let stack = own_effects.at(tx).at(key)
        let _ = stack.pop()
      }
      continue
    }
    if read.get("kind") != Some(Json("read")) {
      continue
    }
    let reader = identifier(required(read, "tx", "read"), "read.tx")
    if outcomes.get(reader) != Some(Json("committed")) {
      continue
    }
    let read_seq = v3_capture_seq(required(read, "seq", "read"), "read.seq")
    let key = required(read, "key", "read")
    let version = identifier(required(read, "version", "read"), "read.version")
    let key_name = identifier(key, "read.key")
    let stack = own_effects
      .get_or_default(reader, Map([]))
      .get_or_default(key_name, [])
    let own = if stack.is_empty() {
      Json::null()
    } else {
      stack[stack.length() - 1]
    }
    if own != Json::null() {
      if object_fields_unchecked_v3(own).get("version") != Some(Json(version)) {
        result["INT"] = classification_models_v3_rule(
          "refuted",
          "read-does-not-observe-current-own-write",
          { "read": raw, "currentOwnWrite": own },
        )
      }
    } else {
      let previous = external_reads.get_or_default(reader, Map([]))
      match previous.get(key_name) {
        Some(before) if object_fields_unchecked_v3(before).get("version") !=
          Some(Json(version)) =>
          result["INT"] = classification_models_v3_rule(
            "refuted",
            "repeated-external-read-changes-without-an-own-write",
            { "previousRead": before, "read": raw },
          )
        _ => ()
      }
      previous[key_name] = raw
      external_reads[reader] = previous
    }
    match by_version.get(version) {
      Some(effect) => {
        let source = object_fields(effect, "effect")
        let writer = identifier(required(source, "tx", "effect"), "effect.tx")
        let seq = v3_capture_seq(
          required(source, "seq", "effect"),
          "effect.seq",
        )
        if writer == reader || seq >= read_seq {
          continue
        }
        if outcomes.get(writer) == Some(Json("aborted")) {
          result["G1a"] = classification_models_v3_rule(
            "refuted",
            "committed-read-from-confirmed-aborted-writer",
            { "read": raw, "sourceEffect": effect, "writerOutcome": "aborted" },
          )
        }
        if outcomes.get(writer) == Some(Json("committed")) &&
          !finals.at(writer).contains(Json(seq.to_double()).stringify()) {
          if source.get("revertedBy") == Some(Json::null()) {
            result["G1b"] = classification_models_v3_rule(
              "refuted",
              "committed-read-from-overwritten-intermediate-write",
              {
                "read": raw,
                "sourceEffect": effect,
                "writerFinalWrites": Json(finals.at(writer).keys().collect()),
              },
            )
          } else if object_fields_unchecked_v3(result.at("G1b")).get("status") !=
            Some(Json("refuted")) {
            result["G1b"] = classification_models_v3_rule(
              "unknown", "revoked-effect-classification-not-supported", effect,
            )
          }
        }
      }
      None => ()
    }
  }
  result
}

///|
fn classification_models_v3_nonadj_dfs(
  graph : GraphIndex,
  edges : Array[Edge],
  vertex : Int32,
  target : Int32,
  previous_rw : Bool,
  seen : Array[Bool],
  path : Array[Int32],
  budget : ClassificationV3Budget,
) -> Array[Edge] {
  if !classification_v3_charge_state(budget) {
    return []
  }
  for index in graph.adj[vertex] {
    if !classification_v3_charge_edge(budget) {
      return []
    }
    let edge = edges[index]
    if edge.kind == RT || (previous_rw && edge.kind == RW) {
      continue
    }
    let next = graph.targets[index]
    if next == target {
      // The first edge is RW, so the closing edge must not also be RW.
      if edge.kind == RW {
        continue
      }
      let result = path.map(i => edges[i])
      result.push(edge)
      return result
    }
    if !seen[next] {
      seen[next] = true
      path.push(index)
      let found = classification_models_v3_nonadj_dfs(
        graph,
        edges,
        next,
        target,
        edge.kind == RW,
        seen,
        path,
        budget,
      )
      let _ = path.pop()
      seen[next] = false
      if !found.is_empty() || budget.limited {
        return found
      }
    }
  }
  []
}

///|
fn classification_models_v3_nonadj(
  transactions : Array[Transaction],
  edges : Array[Edge],
  graph : GraphIndex,
  budget : ClassificationV3Budget,
) -> Array[Edge] {
  for index, edge in edges {
    if !classification_v3_charge_edge(budget) {
      return []
    }
    if edge.kind != RW {
      continue
    }
    let seen = Array::make(transactions.length(), false)
    let source = graph.sources[index]
    let target = graph.targets[index]
    seen[source] = true
    seen[target] = true
    let found = classification_models_v3_nonadj_dfs(
      graph,
      edges,
      target,
      source,
      true,
      seen,
      [index],
      budget,
    )
    if !found.is_empty() || budget.limited {
      return found
    }
  }
  []
}

///|
fn classification_models_v3_requirements(name : String) -> Array[String] {
  match name {
    "adya-pl-1-v1" => ["G0"]
    "adya-pl-2-v1" => ["G0", "G1a", "G1b", "G1c"]
    "adya-pl-2.99-v1" => ["G0", "G1a", "G1b", "G1c", "G2-item"]
    "elle-generalized-si-v1" =>
      ["INT", "G0", "G1a", "G1b", "G1c", "G-nonadjacent"]
    "adya-pl-3-v1" => ["G0", "G1a", "G1b", "G1c", "G2-item"]
    _ => ["G0", "G1a", "G1b", "G1c", "G2-item", "SSG1c", "SSG2-item"]
  }
}

///|
// A model can be refuted by a more specific, actually proved phenomenon even
// when its own required-rule search exhausts its budget. Keep every original
// rule, counter and witness unchanged; this records only the logical provenance.
fn classification_models_v3_refutation_witness(
  rules : Map[String, Json],
  required_rule : String,
) -> Json? {
  for
    source_rule in [
      "G0", "G-nonadjacent", "G1a", "G1b", "G1c", "G2-item", "SSG1c", "SSG2-item",
      "INT",
    ] {
    match rules.get(source_rule) {
      Some(raw) => {
        let source = object_fields_unchecked_v3(raw)
        let evidence = source.get_or_default("evidence", Json::null())
        if source.get("status") != Some(Json("refuted")) ||
          evidence == Json::null() {
          continue
        }
        let specific = if source_rule == "G-nonadjacent" {
          "G-nonadjacent-item"
        } else if source_rule == "G1c" &&
          object_fields_unchecked_v3(evidence).get("specificCategory") ==
          Some(Json("G0")) {
          "G0"
        } else {
          source_rule
        }
        // This classifier supports only register/item and single-append list
        // graphs. Never infer ordinary G2-item from an RT-containing SSG cycle.
        let implications = if source_rule == "G-nonadjacent" {
          ["G-nonadjacent-item", "G-nonadjacent", "G2-item", "G2"]
        } else if source_rule == "G0" ||
          source_rule == "G1c" ||
          source_rule == "G2-item" {
          classification_v3_implications(specific)
        } else if source_rule == "G1a" || source_rule == "G1b" {
          [source_rule, "G1"]
        } else {
          [source_rule]
        }
        if implications.contains(required_rule) {
          return Some({
            "requiredRule": Json(required_rule),
            "provedBy": Json(source_rule),
            "specificAnomaly": Json(specific),
            "impliedAnomalies": Json(implications),
            "requiredRuleStatus": object_fields_unchecked_v3(
              rules.at(required_rule),
            ).get_or_default("status", Json("unknown")),
            "sourceRuleStatus": "refuted",
            "sourceEvidencePath": ["rules", Json(source_rule), "evidence"],
          })
        }
      }
      None => ()
    }
  }
  None
}

///|
fn classification_models_v3_analysis(
  text : String,
  options_text : String,
) -> Json raise {
  let options = classification_models_v3_options(options_text)
  let source = classification_source_v3(text)
  let root = object_fields(
    guarded_json(source.trace_text, limit=8388608),
    "trace",
  )
  let model = identifier(
    root.get_or_default("dataModel", Json("point-register-v1")),
    "dataModel",
  )
  let normalized = guarded_json(
    normalize_capture_v3_options_json(
      source.trace_text,
      options.normalization_options.stringify(),
    ),
    limit=33554432,
  )
  let n = object_fields(normalized, "normalized")
  if n.get("status") == Some(Json("invalid")) {
    fail("Invalid source capture")
  }
  let supported = model == "point-register-v1" || model == "append-list-v1"
  let graph = if model == "point-register-v1" {
    classification_models_v3_register(normalized)
  } else if model == "append-list-v1" {
    classification_models_v3_list(source.trace_text, normalized)
  } else {
    {
      normalized,
      transactions: [],
      edges: [],
      sources: Map([]),
      validity_gaps: [],
      history: None,
      list_parsed: None,
      complete: false,
      reason: "data-model-not-supported-by-isolation-classifier",
    }
  }
  let rules = if supported {
    classification_models_v3_direct(graph, model)
  } else {
    Map([])
  }
  let implied : Array[String] = []
  for name in ["G1a", "G1b", "INT"] {
    match rules.get(name) {
      Some(rule) if object_fields_unchecked_v3(rule).get("status") ==
        Some(Json("refuted")) => {
        implied.push(name)
        if name != "INT" && !implied.contains("G1") {
          implied.push("G1")
        }
      }
      _ => ()
    }
  }
  let graph_index = adjacency(graph.transactions, graph.edges)
  for category in ["G0", "G1c", "G2-item", "G-nonadjacent"] {
    let budget : ClassificationV3Budget = {
      max_states: options.category_options.max_states,
      max_edge_checks: options.category_options.max_edge_checks,
      states: 0,
      edge_checks: 0,
      limited: false,
      reason: "complete",
    }
    let cycle = if category == "G-nonadjacent" {
      classification_models_v3_nonadj(
        graph.transactions,
        graph.edges,
        graph_index,
        budget,
      )
    } else {
      classification_v3_cycle(
        graph.transactions,
        graph.edges,
        graph_index,
        category,
        budget,
      )
    }
    let rule_status = if !supported {
      "unsupported"
    } else if !cycle.is_empty() {
      "refuted"
    } else if budget.limited || !graph.complete {
      "unknown"
    } else {
      "checked-compatible"
    }
    let evidence = if cycle.is_empty() {
      Json::null()
    } else {
      classification_models_v3_witness(graph, cycle)
    }
    let fields = object_fields_unchecked_v3(
      classification_models_v3_rule(
        rule_status,
        if budget.limited {
          budget.reason
        } else {
          graph.reason
        },
        evidence,
      ),
    )
    fields["states"] = Json(budget.states)
    fields["edgeChecks"] = Json(budget.edge_checks)
    rules[category] = Json::object(fields)
    if rule_status == "refuted" {
      let implications = if category == "G-nonadjacent" {
        ["G-nonadjacent-item", "G-nonadjacent", "G2-item", "G2"]
      } else {
        classification_v3_implications(
          if category == "G1c" && cycle.all(edge => edge.kind == WW) {
            "G0"
          } else {
            category
          },
        )
      }
      for name in implications {
        if !implied.contains(name) {
          implied.push(name)
        }
      }
    }
  }
  if !supported {
    for name in ["G1a", "G1b", "INT"] {
      rules[name] = classification_models_v3_rule(
        "unsupported",
        graph.reason,
        Json::null(),
      )
    }
  }
  let intervals = classification_intervals_v3(source, normalized)
  let augmented_edges = graph.edges.copy()
  let augmented_sources : Map[Edge, Array[Json]] = Map([])
  for edge, proofs in graph.sources {
    augmented_sources[edge] = proofs
  }
  let tx_ids : Map[String, Bool] = Map([])
  for transaction in graph.transactions {
    tx_ids[transaction.id] = true
  }
  let mut strict_complete = graph.complete && intervals.complete
  for edge in intervals.edges {
    if augmented_edges.length() >= 50000 {
      strict_complete = false
      break
    }
    if !tx_ids.contains(edge.from) || !tx_ids.contains(edge.to) {
      strict_complete = false
      continue
    }
    augmented_edges.push(edge)
    augmented_sources[edge] = intervals.sources.at(edge)
  }
  let augmented = {
    ..graph,
    edges: augmented_edges,
    sources: augmented_sources,
    complete: strict_complete,
    reason: if strict_complete {
      "complete-real-time-augmented-graph"
    } else if !intervals.complete {
      intervals.reason
    } else {
      graph.reason
    },
  }
  let augmented_index = adjacency(augmented.transactions, augmented.edges)
  for category in ["SSG1c", "SSG2-item"] {
    let budget : ClassificationV3Budget = {
      max_states: options.category_options.max_states,
      max_edge_checks: options.category_options.max_edge_checks,
      states: 0,
      edge_checks: 0,
      limited: false,
      reason: "complete",
    }
    let cycle = classification_v3_cycle(
      augmented.transactions,
      augmented.edges,
      augmented_index,
      category,
      budget,
    )
    let rule_status = if !supported {
      "unsupported"
    } else if !cycle.is_empty() {
      "refuted"
    } else if budget.limited || !strict_complete {
      "unknown"
    } else {
      "checked-compatible"
    }
    let rule = classification_models_v3_rule(
      rule_status,
      if budget.limited {
        budget.reason
      } else {
        augmented.reason
      },
      if cycle.is_empty() {
        Json::null()
      } else {
        classification_models_v3_witness(augmented, cycle)
      },
    )
    let fields = object_fields_unchecked_v3(rule)
    fields["states"] = Json(budget.states)
    fields["edgeChecks"] = Json(budget.edge_checks)
    fields["definition"] = Json(
      if category == "SSG1c" {
        "a WW/WR/RT cycle containing a proven RT edge"
      } else {
        "a WW/WR/item-RW/RT cycle containing item RW; ordinary G2-item is included"
      },
    )
    rules[category] = rule
  }
  let model_results : Map[String, Json] = Map([])
  let mut overall = if supported { "checked-compatible" } else { "unsupported" }
  for name in options.models {
    let requirements = classification_models_v3_requirements(name)
    let refuted : Array[String] = []
    let refutation_witnesses : Array[Json] = []
    let unknown : Array[String] = []
    let unavailable : Array[String] = []
    for rule in requirements {
      let result = object_fields_unchecked_v3(rules.at(rule))
      let witness = classification_models_v3_refutation_witness(rules, rule)
      match witness {
        Some(proof) => {
          let source_rule = identifier(
            object_fields_unchecked_v3(proof).at("provedBy"),
            "provedBy",
          )
          if !refuted.contains(source_rule) {
            refuted.push(source_rule)
          }
          refutation_witnesses.push(proof)
        }
        None => ()
      }
      match result.get("status") {
        Some(String("refuted")) => if witness == None { unknown.push(rule) }
        Some(String("checked-compatible")) => ()
        Some(String("unsupported")) => unavailable.push(rule)
        _ => unknown.push(rule)
      }
    }
    let graph_status = if !refuted.is_empty() {
      "refuted"
    } else if !unavailable.is_empty() {
      "unsupported"
    } else if !unknown.is_empty() {
      "inconclusive"
    } else {
      "checked-compatible"
    }
    // Keep the frozen graph definition unchanged. Operational serial checks
    // additionally need an internally valid transaction program before graph
    // compatibility can be used; this is an applicability precondition, not a
    // new G1/G2 implication or a silent change to the original definition id.
    let needs_internal_precondition = name == "adya-pl-3-v1" ||
      name == "strict-pl-ss-v1"
    let internal = object_fields_unchecked_v3(rules.at("INT"))
    let internal_status = internal.get_or_default("status", Json("unknown"))
    let applicability = if !needs_internal_precondition {
      "not-required-by-this-profile"
    } else if internal_status == Json("checked-compatible") {
      "satisfied"
    } else if internal_status == Json("refuted") {
      "not-satisfied"
    } else {
      "unknown"
    }
    let status = if graph_status == "checked-compatible" &&
      needs_internal_precondition &&
      applicability != "satisfied" {
      "inconclusive"
    } else {
      graph_status
    }
    if status == "refuted" {
      overall = "refuted"
    } else if status != "checked-compatible" && overall != "refuted" {
      overall = if supported { "inconclusive" } else { "unsupported" }
    }
    model_results[name] = {
      "definition": Json(name),
      "status": Json(status),
      "graphStatus": Json(graph_status),
      "requiredRules": Json(requirements),
      "internalValidity": {
        "role": "applicability-precondition-for-operational-serial-checks",
        "status": Json(applicability),
        "rule": "INT",
        "evidence": internal.get_or_default("evidence", Json::null()),
      },
      "refutedBy": Json(refuted),
      "refutationWitnesses": Json(refutation_witnesses),
      "incompleteRules": Json(unknown),
      "unsupportedRules": Json(unavailable),
      "scope": "this supplied observed history and stated source facts only; not a database-wide isolation certification",
    }
  }
  {
    "schemaVersion": 3,
    "tool": "MoonTxnWitness",
    "version": Json(version()),
    "kind": "isolation-model-classification",
    "algorithm": "v3-isolation-model-1",
    "dataModel": Json(model),
    "status": Json(overall),
    "acceptsIsolationModels": true,
    "sourceTraceText": Json(source.trace_text),
    "normalized": normalized,
    "dependencies": Json(graph.edges.map(edge_json)),
    "realTimeDependencies": Json(
      augmented.edges.filter(e => e.kind == RT).map(edge_json),
    ),
    "dependencyGraphComplete": Json(graph.complete),
    "validityGaps": Json(graph.validity_gaps),
    "rules": Json(rules),
    "models": Json(model_results),
    "impliedAnomalies": Json(implied),
    "intervalEvidence": intervals.evidence,
    "scope": "versioned register or the declared single-append list graph profile; model refutations and required checks are separate; source hashes do not authenticate the collector",
    "execution": {
      "classificationOptions": classification_models_v3_options_json(options),
      "limits": {
        "registerTransactions": 128,
        "registerOperations": 4096,
        "listCommittedTransactions": 6,
        "listOperations": 128,
        "edges": 50000,
        "statesPerRule": Json(options.category_options.max_states),
        "edgeChecksPerRule": Json(options.category_options.max_edge_checks),
      },
      "versionOrderCompletion": false,
    },
  }
}
