///|
fn relation_metadata_fixture_v4() -> Json {
  let body = [rpg_begin("R"), rpg_read("R", "1", None)]
  rpg_commit(body, "R")
  rpg_trace(body, empty=true)
}

///|
fn relation_metadata_event_v4(source : Json) -> Map[String, Json] {
  match object_fields_unchecked_v3(source).get("events") {
    Some(Array(events)) => object_fields_unchecked_v3(events[2])
    _ => abort("Missing fixture events")
  }
}

///|
fn relation_metadata_valid_v4(source : Json) -> Bool {
  match parse_history_v4(source.stringify()) {
    Ok(_) => true
    Err(_) => false
  }
}

///|
test "relation metadata 01 missing delivered-read time is an error rather than panic" {
  let source = relation_metadata_fixture_v4()
  assert_true(relation_metadata_valid_v4(source))
  let _ = relation_metadata_event_v4(source).remove("time")
  assert_true(!relation_metadata_valid_v4(source))
}

///|
test "relation metadata 02 missing delivered-read transaction is an error rather than panic" {
  let source = relation_metadata_fixture_v4()
  assert_true(relation_metadata_valid_v4(source))
  let _ = relation_metadata_event_v4(source).remove("tx")
  assert_true(!relation_metadata_valid_v4(source))
}

///|
test "relation metadata 03 missing write time is an error rather than panic" {
  let source = relation_metadata_fixture_v4()
  let event = relation_metadata_event_v4(source)
  event["kind"] = Json("row_write")
  let _ = event.remove("predicate")
  let _ = event.remove("rows")
  let _ = event.remove("complete")
  event["key"] = Json("1")
  event["action"] = Json("insert")
  event["version"] = Json("r1")
  event["predecessor"] = Json::null()
  event["values"] = { "value": "yes" }
  assert_true(relation_metadata_valid_v4(source))
  let _ = event.remove("time")
  assert_true(!relation_metadata_valid_v4(source))
}

///|
test "relation metadata 04 missing sequence and invalid time retain validation" {
  for field in ["seq", "time"] {
    let source = relation_metadata_fixture_v4()
    let event = relation_metadata_event_v4(source)
    if field == "seq" {
      let _ = event.remove(field)
    } else {
      event[field] = Json("invalid-time")
    }
    assert_true(!relation_metadata_valid_v4(source))
  }
}
