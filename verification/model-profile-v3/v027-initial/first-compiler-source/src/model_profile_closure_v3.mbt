///|
/// Close sources using actual committed effects. This neither guesses a
/// serialization order nor turns final database values into initial versions.
fn model_closure_v3(config : ModelProfileConfigV3, source : ModelProfileWindowV3, effects : Array[Json]) -> Unit raise {
  orm_set_equal(source.ledger.to_json(), effects, "All and only actual committed observed effects")
  let consumed : Map[Int, Bool] = Map([])
  if config.is_list {
    let final_rows : Array[Json] = []
    let identities : Array[Json] = []
    let seen_ids : Map[String, Bool] = Map([])
    for key in config.keys {
      let mut current : Array[Json] = []
      for _ in 0..<(effects.length() + 1) {
        let mut next = -1
        for i, effect in effects {
          if orm_get(effect, "key") != key.to_json() || consumed.contains(i) { continue }
          let items = orm_array(orm_get(effect, "items"))
          if items.length() != current.length() + 1 { continue }
          let mut prefix_equal = true
          for j in 0..<current.length() {
            if items[j] != current[j] { prefix_equal = false }
          }
          if prefix_equal {
            orm_assert(next < 0, "No competing append-source successor")
            next = i
          }
        }
        if next < 0 { break }
        let effect = effects[next]
        let item = model_list_item_v3(orm_get(effect, "item"))
        let id = orm_text(orm_get(item, "id"))
        orm_assert(!seen_ids.contains(id), "Committed append identity is globally unique")
        seen_ids[id] = true
        let items = orm_array(orm_get(effect, "items"))
        orm_assert(items[items.length() - 1] == item, "Append source is exactly its actual final tail")
        identities.push({ "id": id.to_json(), "key": key.to_json(), "value": orm_get(item, "value") })
        consumed[next] = true
        current = items
      }
      final_rows.push({ "key": key.to_json(), "items": current.to_json() })
    }
    orm_set_equal(source.final_rows.to_json(), final_rows, "Complete final native list snapshot")
    orm_set_equal(source.final_state.to_json(), identities, "Actual unique append-identity state")
  } else {
    let initial : Map[String, Json] = Map([])
    for row in source.initial { initial[orm_text(orm_get(row, "key"))] = row }
    let final_rows : Array[Json] = []
    let final_state : Array[Json] = []
    let versions : Map[String, Bool] = Map([])
    for row in source.initial {
      let version = orm_uuid(orm_get(row, "version"))
      orm_assert(!versions.contains(version), "Globally unique initial source version")
      versions[version] = true
    }
    for effect in effects {
      let version = orm_uuid(orm_get(effect, "version"))
      orm_assert(!versions.contains(version), "Committed write version is globally unique")
      versions[version] = true
    }
    for key in config.keys {
      let mut current = if initial.contains(key) { orm_get(initial[key], "version") } else { Json::null() }
      let mut present = initial.contains(key)
      let mut values = if present { orm_get(initial[key], "values") } else { Json::null() }
      for _ in 0..<(effects.length() + 1) {
        let mut next = -1
        for i, effect in effects {
          if orm_get(effect, "key") == key.to_json() && orm_get(effect, "predecessor") == current && !consumed.contains(i) {
            orm_assert(next < 0, "Actual committed version chain cannot fork")
            next = i
          }
        }
        if next < 0 { break }
        let effect = effects[next]
        orm_equal(orm_get(effect, "oldPresent"), present.to_json(), "Actual predecessor presence")
        current = orm_get(effect, "version")
        present = match orm_get(effect, "newPresent") { True => true; False => false; _ => fail("Typed actual effect presence") }
        values = orm_get(effect, "values")
        consumed[next] = true
      }
      final_state.push({ "key": key.to_json(), "version": current, "present": present.to_json() })
      if present { final_rows.push({ "key": key.to_json(), "version": current, "values": values }) }
    }
    orm_set_equal(source.final_rows.to_json(), final_rows, "Complete final native relation snapshot")
    orm_set_equal(source.final_state.to_json(), final_state, "Actual final live/tombstone source state")
  }
  orm_assert(consumed.length() == effects.length(), "Every committed effect has its original initialized predecessor closure")
}
