///|
fn model_needed_graph_rules_v4(
  models : Array[ElleModelV4],
) -> Map[String, Bool] {
  let needed : Map[String, Bool] = Map([])
  let mark = fn(projection, context) {
    needed[model_graph_key_v4(projection, context)] = true
  }
  for model in models {
    let projection = model_projection_v4(model)
    let own_context = model_context_v4(model)
    mark("W", ScopedDataOnly)
    mark(projection, own_context)
    if projection != "W" {
      mark("I", ScopedDataOnly)
    }
    if projection == "Ext(I,A)" || projection == "D" {
      mark("Ext(I,A)", own_context)
    }
    for token in model_literal_obligations_v4(model) {
      let context = model_context_for_token_v4(token)
      match token {
        "G0" | "G0-process" | "G0-realtime" | "PL-1-cycle-exists" =>
          mark("W", context)
        "G1"
        | "G1-process"
        | "G1-realtime"
        | "G1c"
        | "G1c-process"
        | "G1c-realtime"
        | "PL-2-cycle-exists" => mark("I", context)
        "G2-item" | "PL-2.99-cycle-exists" => {
          mark("I+Ai", ScopedDataOnly)
          mark("I", ScopedDataOnly)
        }
        "G2" | "G2-process" | "G2-realtime" | "PL-3-cycle-exists" => {
          mark("D", context)
          mark("I", context)
        }
        "G-single" | "G-monotonic" | "G-cursor" | "lost-update" => {
          mark("I", ScopedDataOnly)
          mark("G-single", ScopedDataOnly)
          if token == "G-cursor" || token == "lost-update" {
            mark("I+Ai", ScopedDataOnly)
          }
        }
        "G-nonadjacent" | "G-nonadjacent-process" | "G-nonadjacent-realtime" =>
          mark("G-nonadjacent", context)
        "G-SI" | "G-SIb" | "G-MSR" | "PL-SI-cycle-exists" =>
          mark("Ext(I,A)", ScopedDataOnly)
        "G-update" => {
          mark("D", ScopedDataOnly)
          mark("I", ScopedDataOnly)
        }
        "PL-SS-cycle-exists" => {
          mark("D", ScopedWithRealtime)
          mark("I", ScopedWithRealtime)
        }
        "strong-session-PL-1-cycle-exists" => mark("W", ScopedWithProcess)
        "strong-PL-1-cycle-exists" => mark("W", ScopedWithRealtime)
        "strong-session-PL-2-cycle-exists" => mark("I", ScopedWithProcess)
        "strong-PL-2-cycle-exists" => mark("I", ScopedWithRealtime)
        "strong-session-serializable-cycle-exists" => {
          mark("D", ScopedWithProcess)
          mark("I", ScopedWithProcess)
        }
        "strong-session-snapshot-isolation-cycle-exists" =>
          mark("Ext(I,A)", ScopedWithProcess)
        "strong-snapshot-isolation-cycle-exists" =>
          mark("Ext(I,A)", ScopedWithRealtime)
        _ => ()
      }
    }
  }
  needed
}
