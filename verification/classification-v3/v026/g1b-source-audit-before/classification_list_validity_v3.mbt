///| Validate a list observation before it supplies dependency or direct-rule
/// evidence. An append-only read must preserve the captured immutable initial
/// prefix; a missing/reordered prefix is a source/model applicability gap.
fn classification_models_v3_list_validity(parsed : ListV3Parsed) -> Array[Json] {
  let gaps : Array[Json] = []
  for finding in parsed.findings {
    let fields = object_fields_unchecked_v3(finding)
    if ["item_key_mismatch".to_json(), "item_value_mismatch".to_json(), "duplicate_list_item".to_json()].contains(fields.get_or_default("code", Json::null())) {
      gaps.push(finding)
    }
  }
  for program in parsed.programs {
    if program.status != Committed { continue }
    for action in program.actions {
      match action {
        ReadList(key, observed, seq) => {
          match parsed.initial.get(key) {
            Some(initial) => {
              let mut valid = observed.length() >= initial.length()
              if valid {
                for index, item in initial {
                  if observed[index] != item { valid = false; break }
                }
              }
              if !valid {
                gaps.push({
                  "code": "list_initial_prefix_invalid",
                  "tx": program.id.to_json(),
                  "readSeq": seq.to_double().to_json(),
                  "key": key.to_json(),
                  "initialPrefixIds": initial.map(item => parsed.items[item].id).to_json(),
                  "observedIds": observed.map(item => if item >= 0 { parsed.items[item].id } else { "<missing-source>" }).to_json(),
                  "scope": "This read cannot supply list WR/RW/WW or direct-rule evidence. It does not itself identify an isolation anomaly.",
                })
              }
            }
            None => () // Existing capture coverage already records missing initial state.
          }
        }
        _ => ()
      }
    }
  }
  gaps
}