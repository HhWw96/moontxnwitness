///|
priv struct ClassificationV3Options {
  categories : Array[String]
  max_states : Int
  max_edge_checks : Int
}

///|
priv struct ClassificationV3Budget {
  max_states : Int
  max_edge_checks : Int
  mut states : Int
  mut edge_checks : Int
  mut limited : Bool
  mut reason : String
}

///|
fn classification_v3_options(text : String) -> ClassificationV3Options raise {
  let fields = object_fields(
    guarded_json(text, limit=4096),
    "classification options",
  )
  known_fields(
    fields,
    ["categories", "maxStates", "maxEdgeChecks"],
    "classification options",
  )
  let categories = match fields.get("categories") {
    None => ["G0", "G1c", "G2-item"]
    Some(Array(items)) => {
      let result : Array[String] = []
      for item in items {
        let name = identifier(item, "category")
        if !["G0", "G1c", "G2-item"].contains(name) || result.contains(name) {
          fail(
            "Classification categories must be unique G0, G1c or G2-item labels",
          )
        }
        result.push(name)
      }
      if result.is_empty() {
        fail("At least one classification category is required")
      }
      result
    }
    _ => fail("categories must be an array")
  }
  fn budget(
    fields : Map[String, Json],
    key : String,
    maximum : Int,
  ) -> Int raise {
    match fields.get(key) {
      None => maximum
      Some(Number(n, ..)) if n >= 0.0 &&
        n <= maximum.to_double() &&
        n.to_int().to_double() == n => n.to_int()
      _ => fail(key + " must be an integer in 0.." + maximum.to_string())
    }
  }
  {
    categories,
    max_states: budget(fields, "maxStates", 100000),
    max_edge_checks: budget(fields, "maxEdgeChecks", 1000000),
  }
}

///|
fn classification_v3_options_json(options : ClassificationV3Options) -> Json {
  {
    "categories": options.categories.to_json(),
    "maxStates": options.max_states.to_json(),
    "maxEdgeChecks": options.max_edge_checks.to_json(),
  }
}

///|
fn classification_v3_failure(status : String, message : String) -> Json {
  {
    "schemaVersion": 3,
    "tool": "MoonTxnWitness",
    "version": version().to_json(),
    "kind": "isolation-classification",
    "algorithm": "v3-register-category-1",
    "status": status.to_json(),
    "acceptsIsolationModels": false,
    "error": message.to_json(),
  }
}

///|
fn classification_v3_charge_edge(budget : ClassificationV3Budget) -> Bool {
  if budget.edge_checks >= budget.max_edge_checks {
    budget.limited = true
    budget.reason = "edge-check-budget"
    false
  } else {
    budget.edge_checks += 1
    true
  }
}

///|
fn classification_v3_charge_state(budget : ClassificationV3Budget) -> Bool {
  if budget.states >= budget.max_states {
    budget.limited = true
    budget.reason = "state-budget"
    false
  } else {
    budget.states += 1
    true
  }
}

///|
fn classification_v3_seed(kind : Dependency, category : String) -> Bool {
  match category {
    "G0" => kind == WW
    "G1c" => kind == WW || kind == WR
    "G2-item" | "SSG2-item" => kind == RW
    "SSG1c" => kind == RT
    _ => false
  }
}

///|
fn classification_v3_allowed(kind : Dependency, category : String) -> Bool {
  match category {
    "G0" => kind == WW
    "G1c" => kind == WW || kind == WR
    "G2-item" => kind == WW || kind == WR || kind == RW
    "SSG1c" => kind == WW || kind == WR || kind == RT
    "SSG2-item" => true
    _ => false
  }
}

///|
/// Search each category's required edge independently. A BFS from that edge's
/// target back to its source yields a simple directed cycle containing it.
/// No category is inferred solely from the globally shortest cycle.
fn classification_v3_cycle(
  transactions : Array[Transaction],
  edges : Array[Edge],
  graph : GraphIndex,
  category : String,
  budget : ClassificationV3Budget,
) -> Array[Edge] {
  let size = transactions.length()
  let seen = Array::make(size, 0)
  let parent = Array::make(size, -1)
  let queue = Array::make(size, 0)
  let mut epoch = 0
  for seed_index, seed in edges {
    if !classification_v3_charge_edge(budget) {
      return []
    }
    if !classification_v3_seed(seed.kind, category) {
      continue
    }
    epoch += 1
    let start = graph.targets[seed_index]
    let target = graph.sources[seed_index]
    queue[0] = start
    seen[start] = epoch
    let mut head = 0
    let mut tail = 1
    while head < tail {
      if !classification_v3_charge_state(budget) {
        return []
      }
      let vertex = queue[head]
      head += 1
      for edge_index in graph.adj[vertex] {
        if !classification_v3_charge_edge(budget) {
          return []
        }
        let edge = edges[edge_index]
        if !classification_v3_allowed(edge.kind, category) {
          continue
        }
        let next = graph.targets[edge_index]
        if next == target {
          let backward = [edge]
          let mut current = vertex
          while current != start {
            let previous = parent[current]
            backward.push(edges[previous])
            current = graph.sources[previous]
          }
          backward.rev_in_place()
          let result = [seed]
          for item in backward {
            result.push(item)
          }
          return result
        }
        if seen[next] != epoch {
          seen[next] = epoch
          parent[next] = edge_index
          queue[tail] = next
          tail += 1
        }
      }
    }
  }
  []
}

///|
fn classification_v3_observation_sources(
  normalized : Json,
  transaction : String,
  operation : Operation,
) -> Array[Json] {
  let result : Array[Json] = []
  let observations = match
    object_fields_unchecked_v3(normalized).get("observations") {
    Some(Array(items)) => items
    _ => []
  }
  for raw in observations {
    let fields = object_fields_unchecked_v3(raw)
    if fields.get("tx") == Some(transaction.to_json()) &&
      fields.get("kind") == Some(op_label(operation.kind).to_json()) &&
      fields.get("key") == Some(operation.key.to_json()) &&
      fields.get("version") == Some(operation.version.to_json()) {
      match fields.get("seq") {
        Some(seq) => result.push(seq)
        None => ()
      }
    }
  }
  result
}

///|
fn classification_v3_witness(
  normalized : Json,
  history : History,
  edges : Array[Edge],
) -> Json {
  let by_id : Map[String, Transaction] = Map([])
  for transaction in history.transactions {
    by_id[transaction.id] = transaction
  }
  let proof = edges.map(edge => {
    let from_sources = match edge.from_op {
      Some(index) =>
        classification_v3_observation_sources(
          normalized,
          edge.from,
          by_id.at(edge.from).ops[index],
        )
      None => []
    }
    let to_sources = match edge.to_op {
      Some(index) =>
        classification_v3_observation_sources(
          normalized,
          edge.to,
          by_id.at(edge.to).ops[index],
        )
      None => []
    }
    let order = match edge.key {
      Some(key) => history.version_orders.get_or_default(key, []).to_json()
      None => Json::null()
    }
    (
      {
        "edge": edge_json(edge),
        "fromObservationSeq": from_sources.to_json(),
        "toObservationSeq": to_sources.to_json(),
        "capturedVersionOrder": order,
      } : Json)
  })
  {
    "kind": "category-dependency-cycle",
    "specificCategory": if edges.all(edge => edge.kind == WW) {
      "G0".to_json()
    } else if edges.any(edge => edge.kind == RT) {
      "realtime-cycle".to_json()
    } else if edges.any(edge => edge.kind == RW) {
      "G2-item".to_json()
    } else {
      "G1c".to_json()
    },
    "edges": proof.to_json(),
    "minimality": "a simple cycle for this category; no global or category-shortest claim",
    "sourceScope": "all matching original observations plus the captured predecessor version chain; input assertions are not database authentication",
  }
}

///|
fn classification_v3_implications(category : String) -> Array[String] {
  match category {
    "G0" => ["G0", "G1c", "G1"]
    "G1c" => ["G1c", "G1"]
    "G2-item" => ["G2-item", "G2"]
    _ => []
  }
}

///|
fn classification_v3_analysis(
  text : String,
  options_text : String,
) -> Json raise {
  if orm_utf8_size(text) > 8388608 {
    fail("Classification trace exceeds 8 MiB UTF-8")
  }
  let options = classification_v3_options(options_text)
  let original = guarded_json(text, limit=8388608)
  let input_fields = object_fields(original, "trace")
  let model = input_fields.get_or_default(
    "dataModel",
    "point-register-v1".to_json(),
  )
  let normalized = guarded_json(normalize_capture_v3_json(text), limit=33554432)
  let n = object_fields(normalized, "normalized")
  let rules : Map[String, Json] = Map([])
  let dependencies : Array[Json] = []
  let implied : Array[String] = []
  let mut status = "checked-compatible"
  let mut graph_complete = false
  let mut structural_reason = ""
  let mut history : History? = None
  let mut inferred : Report? = None
  if model != "point-register-v1".to_json() {
    status = "unsupported"
    structural_reason = "Only point-register-v1 is supported by this classification algorithm"
  } else if n.get("status") == Some("invalid".to_json()) {
    status = "invalid"
    structural_reason = "Invalid capture"
  } else if n.get("status") != Some("ready".to_json()) {
    status = "inconclusive"
    structural_reason = "Capture coverage is incomplete; no version-order completion is performed"
  } else {
    let h = match
      parse_history_optimized(required(n, "history", "normalized").stringify()) {
      Ok(value) => value
      Err(message) => fail("Invalid classification projection: " + message)
    }
    let raw_operations = match n.get("observations") {
      Some(Array(items)) =>
        items
        .filter(item => {
          let kind = object_fields_unchecked_v3(item).get("kind")
          kind == Some("read".to_json()) || kind == Some("write".to_json())
        })
        .length()
      _ => 0
    }
    if h.transactions.length() > 128 || raw_operations > 4096 {
      status = "inconclusive"
      structural_reason = "Classification structural limit: 128 transactions and 4096 operations"
    } else {
      let report = analyze_internal(h, false, complete_search=false)
      history = Some(h)
      inferred = Some(report)
      graph_complete = !report.graph.edge_budget_exceeded &&
        !report.findings.any(f => {
          f.severity == "error" || f.severity == "uncertainty"
        })
      for edge in report.edges {
        dependencies.push(edge_json(edge))
      }
      if !graph_complete {
        structural_reason = "Dependency graph or required version-order facts are incomplete"
      }
    }
  }
  match (history, inferred) {
    (Some(h), Some(report)) => {
      let graph = adjacency(h.transactions, report.edges)
      for category in options.categories {
        let budget : ClassificationV3Budget = {
          max_states: options.max_states,
          max_edge_checks: options.max_edge_checks,
          states: 0,
          edge_checks: 0,
          limited: false,
          reason: "complete",
        }
        let cycle = classification_v3_cycle(
          h.transactions,
          report.edges,
          graph,
          category,
          budget,
        )
        let rule_status = if !cycle.is_empty() {
          "refuted"
        } else if budget.limited || !graph_complete {
          "unknown"
        } else {
          "checked-compatible"
        }
        if rule_status == "refuted" {
          status = "refuted"
          let proved_category = if category == "G1c" &&
            cycle.all(edge => edge.kind == WW) {
            "G0"
          } else {
            category
          }
          for name in classification_v3_implications(proved_category) {
            if !implied.contains(name) {
              implied.push(name)
            }
          }
        } else if rule_status == "unknown" && status != "refuted" {
          status = "inconclusive"
        }
        rules[category] = {
          "status": rule_status.to_json(),
          "reason": (if budget.limited {
            budget.reason
          } else if !graph_complete {
            structural_reason
          } else {
            "complete"
          }).to_json(),
          "states": budget.states.to_json(),
          "edgeChecks": budget.edge_checks.to_json(),
          "evidence": if cycle.is_empty() {
            Json::null()
          } else {
            classification_v3_witness(normalized, h, cycle)
          },
        }
      }
    }
    _ =>
      for category in options.categories {
        rules[category] = {
          "status": (if status == "unsupported" {
            "unsupported"
          } else {
            "unknown"
          }).to_json(),
          "reason": structural_reason.to_json(),
          "states": 0,
          "edgeChecks": 0,
          "evidence": Json::null(),
        }
      }
  }
  {
    "schemaVersion": 3,
    "tool": "MoonTxnWitness",
    "version": version().to_json(),
    "kind": "isolation-classification",
    "algorithm": "v3-register-category-1",
    "dataModel": model,
    "status": status.to_json(),
    "acceptsIsolationModels": false,
    "scope": "requested point-register dependency-cycle categories only; checked-compatible is not acceptance of an isolation model or certification of a database",
    "sourceTraceText": text.to_json(),
    "normalized": normalized,
    "dependencies": dependencies.to_json(),
    "dependencyGraphComplete": graph_complete.to_json(),
    "rules": rules.to_json(),
    "impliedAnomalies": implied.to_json(),
    "execution": {
      "classificationOptions": classification_v3_options_json(options),
      "limits": {
        "transactions": 128,
        "operations": 4096,
        "edges": 50000,
        "statesPerCategory": options.max_states.to_json(),
        "edgeChecksPerCategory": options.max_edge_checks.to_json(),
      },
      "versionOrderCompletion": false,
    },
  }
}

///|
fn classification_v3_diagnostic(
  text : String,
  options_text : String,
  status : String,
  message : String,
) -> String {
  let result = classification_v3_failure(status, message)
  let fields = object_fields_unchecked_v3(result)
  if orm_utf8_size(text) <= 8388608 && orm_utf8_size(options_text) <= 8192 {
    fields["sourceTraceText"] = text.to_json()
    fields["execution"] = {
      "classificationOptionsText": options_text.to_json(),
    }
  }
  result.stringify(indent=2)
}

///|
fn classification_v3_dispatch_json(
  text : String,
  options_text : String,
  allow_models : Bool,
) -> String {
  try {
    let report = if allow_models &&
      classification_models_v3_requested(text, options_text) {
      classification_models_v3_analysis(text, options_text)
    } else {
      classification_v3_analysis(text, options_text)
    }
    let encoded = report.stringify(indent=2)
    if orm_utf8_size(encoded) > 33554432 {
      classification_v3_diagnostic(
        text, options_text, "inconclusive", "Classification report exceeds 32 MiB UTF-8; no partial category evidence is accepted",
      )
    } else {
      encoded
    }
  } catch {
    e =>
      classification_v3_diagnostic(text, options_text, "invalid", e.to_string())
  }
}

///|
pub fn classify_v3_json(text : String, options_text : String) -> String {
  classification_v3_dispatch_json(text, options_text, true)
}

///|
pub fn verify_classification_v3_json(
  text : String,
  report_text : String,
) -> String {
  try {
    if orm_utf8_size(report_text) > 33554432 {
      fail("Classification report byte budget")
    }
    let supplied = guarded_json(report_text, limit=33554432)
    let fields = object_fields(supplied, "classification report")
    let category_algorithm = fields.get("algorithm") ==
      Some("v3-register-category-1".to_json())
    // Released 0.2.5 only defined register categories. Its options, including
    // rejected model options, must never dispatch into newer model semantics.
    let released_category = fields.get("version") == Some("0.2.5".to_json()) &&
      category_algorithm
    let current_engine = fields.get("version") == Some(version().to_json())
    if !released_category &&
      !(current_engine &&
      (
        category_algorithm ||
        fields.get("algorithm") == Some("v3-isolation-model-1".to_json())
      )) {
      fail("Unsupported classification engine or algorithm")
    }
    let execution = object_fields(
      required(fields, "execution", "classification report"),
      "execution",
    )
    let options = match execution.get("classificationOptions") {
      Some(value) => value.stringify()
      None =>
        match required(execution, "classificationOptionsText", "execution") {
          String(value) => value
          _ => fail("Classification options text must be a string")
        }
    }
    let expected = guarded_json(
      classification_v3_dispatch_json(text, options, !released_category),
      limit=33554432,
    )
    if released_category {
      // Normalized facts are unversioned; every other field is compared exactly.
      object_fields_unchecked_v3(expected)["version"] = "0.2.5".to_json()
    }
    let valid = supplied == expected
    (
      {
        "valid": valid.to_json(),
        "scope": "every category, source observation, dependency, exact original trace text, budget and counter is recomputed; not database authentication",
        "reason": (if valid {
          "Classification reproduced"
        } else {
          "Classification differs from recomputation"
        }).to_json(),
      } : Json).stringify(indent=2)
  } catch {
    _ =>
      (
        {
          "valid": false,
          "reason": "Malformed, unsupported or oversized classification report",
        } : Json).stringify(indent=2)
  }
}

///|
fn classification_v3_rule_refuted(report : Json, category : String) -> Bool {
  let rules = object_fields_unchecked_v3(
    object_fields_unchecked_v3(report).get_or_default("rules", Json::null()),
  )
  object_fields_unchecked_v3(rules.get_or_default(category, Json::null())).get(
    "status",
  ) ==
  Some("refuted".to_json())
}

///|
/// Reduction preserves the requested category, not just an arbitrary serial
/// violation. Every deletion re-normalizes source facts and reruns that search.
pub fn reduce_classification_v3_json(
  text : String,
  options_text : String,
) -> String {
  try {
    let options = object_fields(
      guarded_json(options_text, limit=8192),
      "classification reduction options",
    )
    known_fields(
      options,
      ["category", "maxChecks", "classificationOptions"],
      "classification reduction options",
    )
    let category = identifier(
      required(options, "category", "reduction"),
      "category",
    )
    if !["G0", "G1c", "G2-item"].contains(category) {
      fail("Unsupported reduction category")
    }
    let max_checks = match options.get("maxChecks") {
      None => 256
      Some(Number(n, ..)) if n >= 0.0 &&
        n <= 256.0 &&
        n.to_int().to_double() == n => n.to_int()
      _ => fail("maxChecks must be an integer in 0..256")
    }
    let classification_options = options
      .get_or_default("classificationOptions", Json::object(Map([])))
      .stringify()
    let parsed_options = classification_v3_options(classification_options)
    if !parsed_options.categories.contains(category) {
      fail("Reduction category is not requested by classificationOptions")
    }
    let mut trace = guarded_json(text, limit=8388608)
    let mut trace_text = text
    let mut report = guarded_json(
      classify_v3_json(trace_text, classification_options),
      limit=33554432,
    )
    let eligible = classification_v3_rule_refuted(report, category)
    let mut checks = 0
    let removed : Array[String] = []
    let mut origins : Array[Json] = []
    let initial_events = match object_fields(trace, "trace").get("events") {
      Some(Array(items)) => items
      _ => fail("Missing events")
    }
    for event in initial_events {
      origins.push(required(object_fields(event, "event"), "seq", "event"))
    }
    let mut minimal = false
    let mut unknown_candidate = false
    if eligible {
      let mut changed = true
      while changed && checks < max_checks {
        changed = false
        let normalized = object_fields(
          required(object_fields(report, "report"), "normalized", "report"),
          "normalized",
        )
        let transactions = match
          required(normalized, "transactions", "normalized") {
          Array(items) => items
          _ => fail("Missing normalized transactions")
        }
        let mut completed_pass = true
        let mut pass_unknown = false
        for transaction in transactions {
          if checks >= max_checks {
            completed_pass = false
            break
          }
          let id = identifier(
            required(
              object_fields(transaction, "transaction"),
              "id",
              "transaction",
            ),
            "transaction.id",
          )
          let (candidate, relative_origins) = v3_without_transaction(trace, id)
          let candidate_text = candidate.stringify()
          checks += 1
          let candidate_report = guarded_json(
            classify_v3_json(candidate_text, classification_options),
            limit=33554432,
          )
          if classification_v3_rule_refuted(candidate_report, category) {
            let old_events = match object_fields(trace, "trace").at("events") {
              Array(items) => items
              _ => []
            }
            let old_origin : Map[String, Json] = Map([])
            for index, event in old_events {
              old_origin[object_fields(event, "event").at("seq").stringify()] = origins[index]
            }
            origins = relative_origins.map(seq => old_origin.at(seq.stringify()))
            trace = candidate
            trace_text = candidate_text
            report = candidate_report
            removed.push(id)
            changed = true
            completed_pass = false
            break
          }
          let candidate_fields = object_fields_unchecked_v3(candidate_report)
          let candidate_normalized = object_fields_unchecked_v3(
            candidate_fields.get_or_default("normalized", Json::null()),
          )
          let candidate_coverage = object_fields_unchecked_v3(
            candidate_normalized.get_or_default("coverage", Json::null()),
          )
          let candidate_rules = object_fields_unchecked_v3(
            candidate_fields.get_or_default("rules", Json::null()),
          )
          let candidate_rule = object_fields_unchecked_v3(
            candidate_rules.get_or_default(category, Json::null()),
          )
          // A proven source gap is outside this reduction predicate. A complete
          // candidate with an exhausted search must not establish minimality.
          if candidate_coverage.get("complete") == Some(true.to_json()) &&
            candidate_rule.get("status") == Some("unknown".to_json()) {
            pass_unknown = true
          }
          if !candidate_fields.contains("normalized") {
            pass_unknown = true
          }
        }
        if completed_pass {
          minimal = !pass_unknown
          unknown_candidate = pass_unknown
        }
      }
    }
    (
      {
        "schemaVersion": 3,
        "tool": "MoonTxnWitness",
        "version": version().to_json(),
        "algorithm": "v3-classification-source-checked-single-delete-1",
        "category": category.to_json(),
        "predicate": "the requested category has a source-verified counterexample",
        "status": (if !eligible {
          "not-refuted"
        } else if unknown_candidate {
          "inconclusive"
        } else if !minimal {
          "budget"
        } else if removed.is_empty() {
          "unchanged"
        } else {
          "reduced"
        }).to_json(),
        "checks": checks.to_json(),
        "maxChecks": max_checks.to_json(),
        "oneMinimal": minimal.to_json(),
        "removed": removed.to_json(),
        "retainedOriginalSeq": origins.to_json(),
        "reducedCapture": trace,
        "reducedTraceText": trace_text.to_json(),
        "report": report,
        "classificationOptions": classification_v3_options_json(parsed_options),
      } : Json).stringify(indent=2)
  } catch {
    e => classification_v3_failure("invalid", e.to_string()).stringify(indent=2)
  }
}
