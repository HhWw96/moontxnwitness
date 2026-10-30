///|
/// Validate a list observation before it supplies dependency or direct-rule
/// evidence. Full-version checks require the captured immutable initial prefix
/// and each external producer's append prefix. An independent matching aborted
/// item can still establish G1a despite a separate list-shape gap.
fn classification_models_v3_list_validity(parsed : ListV3Parsed) -> Array[Json] {
  let gaps : Array[Json] = []
  let producers : Map[String, Map[String, Array[Int32]]] = Map([])
  let positions : Map[Int32, Int32] = Map([])
  for producer in parsed.programs {
    // Reverted append provenance needs a separate contract; do not infer a
    // flat prefix through a savepoint or rollback boundary.
    if producer.actions.any(action => {
        match action {
          Mark(_) | Undo(_) | Release(_) => true
          _ => false
        }
      }) {
      continue
    }
    let keys : Map[String, Array[Int32]] = Map([])
    for action in producer.actions {
      match action {
        Append(key, item) => {
          let sequence = keys.get_or_default(key, [])
          positions[item] = sequence.length()
          sequence.push(item)
          keys[key] = sequence
        }
        _ => ()
      }
    }
    producers[producer.id] = keys
  }
  for finding in parsed.findings {
    let fields = object_fields_unchecked_v3(finding)
    if [
        Json("item_key_mismatch"),
        Json("item_value_mismatch"),
        Json("duplicate_list_item"),
      ].contains(fields.get_or_default("code", Json::null())) {
      gaps.push(finding)
    }
  }
  for program in parsed.programs {
    if program.status != Committed {
      continue
    }
    for action in program.actions {
      match action {
        ReadList(key, observed, seq) => {
          match parsed.initial.get(key) {
            Some(initial) => {
              let mut valid = observed.length() >= initial.length()
              if valid {
                for index, item in initial {
                  if observed[index] != item {
                    valid = false
                    break
                  }
                }
              }
              if !valid {
                gaps.push({
                  "code": "list_initial_prefix_invalid",
                  "tx": Json(program.id),
                  "readSeq": Json(seq.to_double()),
                  "key": Json(key),
                  "initialPrefixIds": Json(
                    initial.map(item => parsed.items[item].id),
                  ),
                  "observedIds": Json(
                    observed.map(item => {
                      if item >= 0 {
                        parsed.items[item].id
                      } else {
                        "<missing-source>"
                      }
                    }),
                  ),
                  "scope": "This read cannot supply list WR/RW/WW or complete-version G1b/INT evidence. A separately matching aborted item can still prove G1a; this shape gap is not itself an isolation anomaly.",
                })
              }
            }
            None => () // Existing capture coverage already records missing initial state.
          }
          let counts : Map[String, Int32] = Map([])
          let broken : Map[String, Bool] = Map([])
          for item in observed {
            if item < 0 {
              continue
            }
            let source = parsed.items[item]
            if source.key != key {
              continue
            }
            match source.tx {
              Some(writer) if writer != program.id && producers.contains(writer) => {
                let expected = counts.get_or_default(writer, 0)
                if positions.get(item) != Some(expected) {
                  broken[writer] = true
                }
                counts[writer] = expected + 1
              }
              _ => ()
            }
          }
          for producer in parsed.programs {
            if !broken.contains(producer.id) {
              continue
            }
            let written = producers.at(producer.id).get_or_default(key, [])
            let external = observed.filter(item => {
              item >= 0 &&
              parsed.items[item].key == key &&
              parsed.items[item].tx == Some(producer.id)
            })
            gaps.push({
              "code": "list_external_producer_prefix_invalid",
              "tx": Json(program.id),
              "readSeq": Json(seq.to_double()),
              "key": Json(key),
              "writer": Json(producer.id),
              "writerAppendIds": Json(
                written.map(item => parsed.items[item].id),
              ),
              "observedWriterAppendIds": Json(
                external.map(item => parsed.items[item].id),
              ),
              "scope": "The external producer subsequence is not its captured append prefix; no graph or complete-version G1b/INT claim may use this read. Independently matching aborted elements remain eligible for G1a.",
            })
          }
        }
        _ => ()
      }
    }
  }
  gaps
}
