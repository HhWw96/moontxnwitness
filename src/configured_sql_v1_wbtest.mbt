///|
fn sp37_config() -> SQLConfigV1 {
  parse_sql_config_v1(
    "{\"format\": \"moontxnwitness-configured-sql/v1\", \"tables\": [{\"schema\": \"ledger\", \"table\": \"accounts\", \"primaryKey\": \"account_no\", \"columns\": [{\"name\": \"account_no\", \"type\": \"int64\", \"comparison\": null}, {\"name\": \"balance\", \"type\": \"int64\", \"comparison\": null}, {\"name\": \"active\", \"type\": \"bool\", \"comparison\": null}, {\"name\": \"label\", \"type\": \"text\", \"comparison\": \"postgres-c-utf8-v1\"}], \"model\": \"relation-set-v1\"}, {\"schema\": \"app\", \"table\": \"flags\", \"primaryKey\": \"feature_key\", \"columns\": [{\"name\": \"feature_key\", \"type\": \"text\", \"comparison\": \"postgres-c-utf8-v1\"}, {\"name\": \"enabled\", \"type\": \"bool\", \"comparison\": null}], \"model\": \"relation-set-v1\"}, {\"schema\": \"App-X\", \"table\": \"Customer.Space\", \"primaryKey\": \"User ID\", \"columns\": [{\"name\": \"User ID\", \"type\": \"text\", \"comparison\": \"postgres-c-utf8-v1\"}, {\"name\": \"quota\", \"type\": \"int64\", \"comparison\": null}, {\"name\": \"live\", \"type\": \"bool\", \"comparison\": null}, {\"name\": \"zone\", \"type\": \"text\", \"comparison\": \"postgres-c-utf8-v1\"}, {\"name\": \"score\", \"type\": \"int64\", \"comparison\": null}, {\"name\": \"note\", \"type\": \"text\", \"comparison\": \"postgres-c-utf8-v1\"}], \"model\": \"relation-set-v1\"}], \"defaultSchema\": \"ledger\", \"limits\": {\"max_sql_bytes\": 65536, \"max_tokens\": 8192, \"max_ast_nodes\": 4096, \"max_nesting\": 64, \"max_terms\": 128, \"max_insert_rows\": 128, \"max_text_bytes\": 65536}}",
  ).unwrap()
}

///|
fn sp37_normalize(
  sql : String,
  parameters : String,
  options~ : SQLVerificationOptionsV1 = sql_verification_options_v1(),
) -> Json raise {
  sql_candidate_check_v1_json(
    normalize_sql_candidate_v1(
      sp37_config(),
      sql,
      sql_json_v1(parameters, 1048576),
      options~,
    ),
  )
}

///|
test "sql37 real Python 01 table0-select" {
  let report = sp37_normalize(
    "SELECT \"account_no\",\"balance\",\"active\",\"label\" FROM \"ledger\".\"accounts\" WHERE \"account_no\"=%s",
    "[17]",
  )
  assert_eq(v4_test_at(report, ["status"]), Json("recognized"))
  assert_eq(
    v3_dislock_sha256(
      sql_canonical_v1(v4_test_at(report, ["expectedCandidate"])),
    ),
    "65f99f8c3ea8c57b2aac035df4214be707f3c38d946e8afa9f182ee3adae065d",
  )
  assert_eq(v4_test_at(report, ["captureFactsProduced"]), Json(false))
}

///|
test "sql37 real Python 02 table0-insert" {
  let report = sp37_normalize(
    "INSERT INTO \"ledger\".\"accounts\"(\"account_no\",\"balance\",\"active\",\"label\") VALUES(%s,%s,%s,%s) RETURNING \"account_no\",\"balance\",\"active\",\"label\"",
    "[17, 17, true, \"值🙂\"]",
  )
  assert_eq(v4_test_at(report, ["status"]), Json("recognized"))
  assert_eq(
    v3_dislock_sha256(
      sql_canonical_v1(v4_test_at(report, ["expectedCandidate"])),
    ),
    "5e340174c272fc7c95c3739825fcebc8164f518c15051d5efaae9059e59e565e",
  )
  assert_eq(v4_test_at(report, ["captureFactsProduced"]), Json(false))
}

///|
test "sql37 real Python 03 table0-update" {
  let report = sp37_normalize(
    "UPDATE \"ledger\".\"accounts\" SET \"balance\"=%s WHERE \"account_no\"=%s RETURNING \"account_no\",\"balance\",\"active\",\"label\"",
    "[17, 17]",
  )
  assert_eq(v4_test_at(report, ["status"]), Json("recognized"))
  assert_eq(
    v3_dislock_sha256(
      sql_canonical_v1(v4_test_at(report, ["expectedCandidate"])),
    ),
    "d72215125ec373201b838423998b419549b82bca405f5d8cf6665f6883ccc955",
  )
  assert_eq(v4_test_at(report, ["captureFactsProduced"]), Json(false))
}

///|
test "sql37 real Python 04 table0-delete" {
  let report = sp37_normalize(
    "DELETE FROM \"ledger\".\"accounts\" WHERE \"account_no\"=%s RETURNING \"account_no\",\"balance\",\"active\",\"label\"",
    "[17]",
  )
  assert_eq(v4_test_at(report, ["status"]), Json("recognized"))
  assert_eq(
    v3_dislock_sha256(
      sql_canonical_v1(v4_test_at(report, ["expectedCandidate"])),
    ),
    "fc6ce72e2d5fc23a05a2fc1c6ea4462bb5ee7364cd1428a25976dd0c5da0eab5",
  )
  assert_eq(v4_test_at(report, ["captureFactsProduced"]), Json(false))
}

///|
test "sql37 real Python 05 table1-select" {
  let report = sp37_normalize(
    "SELECT \"feature_key\",\"enabled\" FROM \"app\".\"flags\" WHERE \"feature_key\"=%s",
    "[\"值🙂\"]",
  )
  assert_eq(v4_test_at(report, ["status"]), Json("recognized"))
  assert_eq(
    v3_dislock_sha256(
      sql_canonical_v1(v4_test_at(report, ["expectedCandidate"])),
    ),
    "eb950611f2273b48959cb76cf7ee003fff1369027e07514b6c7d4dc2e9be0fa6",
  )
  assert_eq(v4_test_at(report, ["captureFactsProduced"]), Json(false))
}

///|
test "sql37 real Python 06 table1-insert" {
  let report = sp37_normalize(
    "INSERT INTO \"app\".\"flags\"(\"feature_key\",\"enabled\") VALUES(%s,%s) RETURNING \"feature_key\",\"enabled\"",
    "[\"值🙂\", true]",
  )
  assert_eq(v4_test_at(report, ["status"]), Json("recognized"))
  assert_eq(
    v3_dislock_sha256(
      sql_canonical_v1(v4_test_at(report, ["expectedCandidate"])),
    ),
    "6a806993e5685b9a0097eb36bf3f140fc73556d2f99020321f03d821958ba028",
  )
  assert_eq(v4_test_at(report, ["captureFactsProduced"]), Json(false))
}

///|
test "sql37 real Python 07 table1-update" {
  let report = sp37_normalize(
    "UPDATE \"app\".\"flags\" SET \"enabled\"=%s WHERE \"feature_key\"=%s RETURNING \"feature_key\",\"enabled\"",
    "[true, \"值🙂\"]",
  )
  assert_eq(v4_test_at(report, ["status"]), Json("recognized"))
  assert_eq(
    v3_dislock_sha256(
      sql_canonical_v1(v4_test_at(report, ["expectedCandidate"])),
    ),
    "ac3d49ae20a379e213cf33bf307f9bf7292b263b36d7687ed360177fef4b6d4d",
  )
  assert_eq(v4_test_at(report, ["captureFactsProduced"]), Json(false))
}

///|
test "sql37 real Python 08 table1-delete" {
  let report = sp37_normalize(
    "DELETE FROM \"app\".\"flags\" WHERE \"feature_key\"=%s RETURNING \"feature_key\",\"enabled\"",
    "[\"值🙂\"]",
  )
  assert_eq(v4_test_at(report, ["status"]), Json("recognized"))
  assert_eq(
    v3_dislock_sha256(
      sql_canonical_v1(v4_test_at(report, ["expectedCandidate"])),
    ),
    "f6f0c6fe8784a0ca14402ed5d5896544a741b6ab8c50d6467b813b63e9d1756e",
  )
  assert_eq(v4_test_at(report, ["captureFactsProduced"]), Json(false))
}

///|
test "sql37 real Python 09 table2-select" {
  let report = sp37_normalize(
    "SELECT \"User ID\",\"quota\",\"live\",\"zone\",\"score\",\"note\" FROM \"App-X\".\"Customer.Space\" WHERE \"User ID\"=%s",
    "[\"值🙂\"]",
  )
  assert_eq(v4_test_at(report, ["status"]), Json("recognized"))
  assert_eq(
    v3_dislock_sha256(
      sql_canonical_v1(v4_test_at(report, ["expectedCandidate"])),
    ),
    "20ed143f7570317beaa4b7400419c8a29806b863cca38e2e2ee80a57f38765f4",
  )
  assert_eq(v4_test_at(report, ["captureFactsProduced"]), Json(false))
}

///|
test "sql37 real Python 10 table2-insert" {
  let report = sp37_normalize(
    "INSERT INTO \"App-X\".\"Customer.Space\"(\"User ID\",\"quota\",\"live\",\"zone\",\"score\",\"note\") VALUES(%s,%s,%s,%s,%s,%s) RETURNING \"User ID\",\"quota\",\"live\",\"zone\",\"score\",\"note\"",
    "[\"值🙂\", 17, true, \"值🙂\", 17, \"值🙂\"]",
  )
  assert_eq(v4_test_at(report, ["status"]), Json("recognized"))
  assert_eq(
    v3_dislock_sha256(
      sql_canonical_v1(v4_test_at(report, ["expectedCandidate"])),
    ),
    "f216ced8d2a4a09fb7426d9154848ef4a7786d07e915a91b4ca69c784f35ee56",
  )
  assert_eq(v4_test_at(report, ["captureFactsProduced"]), Json(false))
}

///|
test "sql37 real Python 11 table2-update" {
  let report = sp37_normalize(
    "UPDATE \"App-X\".\"Customer.Space\" SET \"quota\"=%s WHERE \"User ID\"=%s RETURNING \"User ID\",\"quota\",\"live\",\"zone\",\"score\",\"note\"",
    "[17, \"值🙂\"]",
  )
  assert_eq(v4_test_at(report, ["status"]), Json("recognized"))
  assert_eq(
    v3_dislock_sha256(
      sql_canonical_v1(v4_test_at(report, ["expectedCandidate"])),
    ),
    "cb4b457fb01a8f97fe905bacc493f189322d5b1eef0a4bc1f6eae42d0b2fc2b4",
  )
  assert_eq(v4_test_at(report, ["captureFactsProduced"]), Json(false))
}

///|
test "sql37 real Python 12 table2-delete" {
  let report = sp37_normalize(
    "DELETE FROM \"App-X\".\"Customer.Space\" WHERE \"User ID\"=%s RETURNING \"User ID\",\"quota\",\"live\",\"zone\",\"score\",\"note\"",
    "[\"值🙂\"]",
  )
  assert_eq(v4_test_at(report, ["status"]), Json("recognized"))
  assert_eq(
    v3_dislock_sha256(
      sql_canonical_v1(v4_test_at(report, ["expectedCandidate"])),
    ),
    "b2a5d158562c7cb5b874e29374bdf2bcf134f64b820cb96f015cc6b34da0a2e2",
  )
  assert_eq(v4_test_at(report, ["captureFactsProduced"]), Json(false))
}

///|
test "sql37 real Python 13 range-and-named" {
  let report = sp37_normalize(
    "SELECT a.account_no AS \"Result ID\",a.balance FROM LEDGER.ACCOUNTS a WHERE (a.balance >= %(Min)s AND a.balance < %(Max)s) AND a.active=%(Live)s ORDER BY a.account_no DESC",
    "{\"Min\": -7, \"Max\": 42, \"Live\": true}",
  )
  assert_eq(v4_test_at(report, ["status"]), Json("recognized"))
  assert_eq(
    v3_dislock_sha256(
      sql_canonical_v1(v4_test_at(report, ["expectedCandidate"])),
    ),
    "13b7243a79e2e682d32d8ac8e2e25cc8274f69a141c78525d53673847eb139db",
  )
  assert_eq(v4_test_at(report, ["captureFactsProduced"]), Json(false))
}

///|
test "sql37 real Python 14 comments-stars" {
  let report = sp37_normalize(
    "SELECT /* outer /* nested */ proof */ a.* FROM ledger.accounts AS a WHERE a.account_no=%s -- delivered later",
    "[3]",
  )
  assert_eq(v4_test_at(report, ["status"]), Json("recognized"))
  assert_eq(
    v3_dislock_sha256(
      sql_canonical_v1(v4_test_at(report, ["expectedCandidate"])),
    ),
    "86cef6d81bb70da795dee673211880e4c113d251ee8a69530cd8d4fb31aa783b",
  )
  assert_eq(v4_test_at(report, ["captureFactsProduced"]), Json(false))
}

///|
test "sql37 real Python 15 int64-maximum" {
  let report = sp37_normalize(
    "SELECT account_no FROM ledger.accounts WHERE account_no=%s", "[9223372036854775807]",
  )
  assert_eq(v4_test_at(report, ["status"]), Json("recognized"))
  assert_eq(
    v3_dislock_sha256(
      sql_canonical_v1(v4_test_at(report, ["expectedCandidate"])),
    ),
    "2338cb6d037517fec9930f0e81bb40dbf94359bbb4631b66b2446ef711e55fd5",
  )
  assert_eq(v4_test_at(report, ["captureFactsProduced"]), Json(false))
}

///|
test "sql37 real Python 16 int64-minimum" {
  let report = sp37_normalize(
    "SELECT account_no FROM ledger.accounts WHERE account_no=%s", "[-9223372036854775808]",
  )
  assert_eq(v4_test_at(report, ["status"]), Json("recognized"))
  assert_eq(
    v3_dislock_sha256(
      sql_canonical_v1(v4_test_at(report, ["expectedCandidate"])),
    ),
    "1055c2320c2c845a0315e9f5edc098c083f432e7e61122dabe9dc774067ca145",
  )
  assert_eq(v4_test_at(report, ["captureFactsProduced"]), Json(false))
}

///|
test "sql37 real Python 17 inline-literals" {
  let report = sp37_normalize(
    "SELECT account_no FROM ledger.accounts WHERE balance >= -9223372036854775808 AND active=true AND label='中''文'",
    "null",
  )
  assert_eq(v4_test_at(report, ["status"]), Json("recognized"))
  assert_eq(
    v3_dislock_sha256(
      sql_canonical_v1(v4_test_at(report, ["expectedCandidate"])),
    ),
    "cd86837820bc5f87878955e7ff7a2ba2f63e3724f83ba86614f81c63e43d126a",
  )
  assert_eq(v4_test_at(report, ["captureFactsProduced"]), Json(false))
}

///|
test "sql37 real Python 18 unicode-collate" {
  let report = sp37_normalize(
    "SELECT feature_key FROM app.flags WHERE feature_key COLLATE \"C\">=%s", "[\"𐀀\"]",
  )
  assert_eq(v4_test_at(report, ["status"]), Json("recognized"))
  assert_eq(
    v3_dislock_sha256(
      sql_canonical_v1(v4_test_at(report, ["expectedCandidate"])),
    ),
    "46fe114c19bdb0bc205a332f371495bff3910faf09c1ad4e77e057559cc677ab",
  )
  assert_eq(v4_test_at(report, ["captureFactsProduced"]), Json(false))
}

///|
test "sql37 real Python 19 multivalue-insert" {
  let report = sp37_normalize(
    "INSERT INTO app.flags(feature_key,enabled) VALUES(%s,%s),(%s,%s) RETURNING *",
    "[\"a\", true, \"b\", false]",
  )
  assert_eq(v4_test_at(report, ["status"]), Json("recognized"))
  assert_eq(
    v3_dislock_sha256(
      sql_canonical_v1(v4_test_at(report, ["expectedCandidate"])),
    ),
    "b4cae45b4ee70d95e00c0985c9eff1de52376c07f3f0b0ceb44336731df5399a",
  )
  assert_eq(v4_test_at(report, ["captureFactsProduced"]), Json(false))
}

///|
test "sql37 real Python 20 named-case-sensitive" {
  let report = sp37_normalize(
    "SELECT account_no FROM accounts WHERE account_no=%(Who)s AND balance>=%(Who)s",
    "{\"Who\": 13}",
  )
  assert_eq(v4_test_at(report, ["status"]), Json("recognized"))
  assert_eq(
    v3_dislock_sha256(
      sql_canonical_v1(v4_test_at(report, ["expectedCandidate"])),
    ),
    "92d19adcfce75646f8dd7ba721ee5937817b0ae68d0a34e2b7b67ce356bccba1",
  )
  assert_eq(v4_test_at(report, ["captureFactsProduced"]), Json(false))
}

///|
test "sql37 real Python 21 literal-percent-with-no-params" {
  let report = sp37_normalize(
    "SELECT feature_key FROM app.flags WHERE feature_key='literal%s'", "null",
  )
  assert_eq(v4_test_at(report, ["status"]), Json("recognized"))
  assert_eq(
    v3_dislock_sha256(
      sql_canonical_v1(v4_test_at(report, ["expectedCandidate"])),
    ),
    "6e14b6bd2b29aab529da9099ca7b29cadbc1f7d1f4dc641d179d73ea67f46e48",
  )
  assert_eq(v4_test_at(report, ["captureFactsProduced"]), Json(false))
}

///|
test "sql37 22 independently supplied candidate must equal reconstructed fields" {
  let config = sp37_config()
  let report = sp37_normalize(
    "SELECT account_no FROM ledger.accounts WHERE account_no=%s", "[7]",
  )
  let candidate = v4_test_at(report, ["expectedCandidate"])
  assert_eq(
    v4_test_at(
      sql_candidate_check_v1_json(
        verify_sql_candidate_v1(
          config,
          "SELECT account_no FROM ledger.accounts WHERE account_no=%s",
          sql_json_v1("[7]", 100),
          candidate,
        ),
      ),
      ["status"],
    ),
    Json("matched"),
  )
  object_fields_unchecked_v3(candidate)["sqlSha256"] = Json("forged")
  assert_eq(
    v4_test_at(
      sql_candidate_check_v1_json(
        verify_sql_candidate_v1(
          config,
          "SELECT account_no FROM ledger.accounts WHERE account_no=%s",
          sql_json_v1("[7]", 100),
          candidate,
        ),
      ),
      ["valid"],
    ),
    Json(false),
  )
}

///|
test "sql37 23 same-type changed parameter value cannot reuse original binding claim" {
  let report = sp37_normalize(
    "SELECT account_no FROM ledger.accounts WHERE account_no=%s", "[7]",
  )
  let checked = sql_candidate_check_v1_json(
    verify_sql_candidate_v1(
      sp37_config(),
      "SELECT account_no FROM ledger.accounts WHERE account_no=%s",
      sql_json_v1("[8]", 100),
      v4_test_at(report, ["expectedCandidate"]),
    ),
  )
  assert_eq(v4_test_at(checked, ["valid"]), Json(false))
}

///|
test "sql37 24 exact check budget boundary and zero remain visible" {
  let source = "SELECT account_no FROM ledger.accounts WHERE account_no=%s"
  let report = sp37_normalize(source, "[7]")
  let count = match v4_test_at(report, ["execution", "checks"]) {
    Number(n, ..) => n.to_int()
    _ => -1
  }
  assert_eq(
    v4_test_at(
      sp37_normalize(
        source,
        "[7]",
        options=sql_verification_options_v1(max_checks=count),
      ),
      ["valid"],
    ),
    Json(true),
  )
  assert_eq(
    v4_test_at(
      sp37_normalize(
        source,
        "[7]",
        options=sql_verification_options_v1(max_checks=count - 1),
      ),
      ["status"],
    ),
    Json("unknown"),
  )
  assert_eq(
    v4_test_at(
      sp37_normalize(
        source,
        "[7]",
        options=sql_verification_options_v1(max_checks=0),
      ),
      ["status"],
    ),
    Json("unknown"),
  )
}

///|
test "sql37 25 unsupported syntax never becomes a fact" {
  for
    source in [
      "SELECT count(*) FROM ledger.accounts", "SELECT a.account_no FROM ledger.accounts a JOIN app.flags f ON a.label=f.feature_key",
      "SELECT account_no FROM ledger.accounts WHERE label=NULL", "SELECT account_no FROM ledger.accounts WHERE account_no=1 OR active=true",
      "SELECT account_no FROM ledger.accounts LIMIT 1", "SELECT account_no FROM ledger.accounts WHERE account_no=%(pk)s::UUID",
    ] {
    let report = sp37_normalize(source, "null")
    assert_eq(v4_test_at(report, ["valid"]), Json(false))
    assert_eq(v4_test_at(report, ["captureFactsProduced"]), Json(false))
  }
}

///|
test "sql37 26 parameter arity type precision and escaped duplicates rejected" {
  let source = "SELECT account_no FROM ledger.accounts WHERE account_no=%s"
  for
    parameters in [
      "[]", "[true]", "[1.0]", "[9223372036854775808]", "[null]", "[\"7\"]",
    ] {
    assert_eq(
      v4_test_at(sp37_normalize(source, parameters), ["valid"]),
      Json(false),
    )
  }
  let supplied = verify_configured_sql_v1_json(
    sp37_config().record.stringify(),
    source,
    "{\"x\":1,\"\\u0078\":2}",
    "{}",
    "{}",
  )
  assert_eq(v4_test_at(@json.parse(supplied), ["valid"]), Json(false))
}

///|
test "sql37 27 token SQL byte and conservative structure budgets" {
  let source = "SELECT account_no FROM ledger.accounts"
  assert_eq(
    v4_test_at(
      sp37_normalize(
        source,
        "null",
        options=sql_verification_options_v1(max_tokens=1),
      ),
      ["status"],
    ),
    Json("unknown"),
  )
  assert_eq(
    v4_test_at(
      sp37_normalize(
        source,
        "null",
        options=sql_verification_options_v1(max_sql_bytes=1),
      ),
      ["status"],
    ),
    Json("unknown"),
  )
}

///|
test "sql37 28 flags and type labels cannot authorize provenance" {
  let report = sp37_normalize("SELECT * FROM app.flags", "null")
  let candidate = v4_test_at(report, ["expectedCandidate"])
  let descriptor = object_fields_unchecked_v3(
    v4_test_at(candidate, ["descriptor"]),
  )
  descriptor["captureFactsProduced"] = Json(true)
  let checked = sql_candidate_check_v1_json(
    verify_sql_candidate_v1(
      sp37_config(),
      "SELECT * FROM app.flags",
      Json::null(),
      candidate,
    ),
  )
  assert_eq(v4_test_at(checked, ["valid"]), Json(false))
  assert_eq(v4_test_at(checked, ["actualDriverResultsVerified"]), Json(false))
}

///|
test "sql37 29 multiple table identities cannot collide through separators" {
  let text = "{\"format\":\"moontxnwitness-configured-sql/v1\",\"tables\":[{\"schema\":\"a.b\",\"table\":\"c\",\"primaryKey\":\"id\",\"columns\":[{\"name\":\"id\",\"type\":\"int64\"}]},{\"schema\":\"a\",\"table\":\"b.c\",\"primaryKey\":\"id\",\"columns\":[{\"name\":\"id\",\"type\":\"int64\"}]}]}"
  let config = parse_sql_config_v1(text).unwrap()
  let a = sql_candidate_check_v1_json(
    normalize_sql_candidate_v1(config, "SELECT id FROM \"a.b\".c", Json::null()),
  )
  let b = sql_candidate_check_v1_json(
    normalize_sql_candidate_v1(config, "SELECT id FROM a.\"b.c\"", Json::null()),
  )
  assert_eq(v4_test_at(a, ["valid"]), Json(true))
  assert_eq(v4_test_at(b, ["valid"]), Json(true))
  assert_false(
    v4_test_at(a, ["descriptor", "table"]) ==
    v4_test_at(b, ["descriptor", "table"]),
  )
}

///|
test "sql37 30 canonical uses lexical codepoints and C comparison matches independent UTF8 bytes" {
  assert_eq(
    sql_canonical_v1(({ "long-name": 1, "z": 2, "abc": 3 } : Json)),
    "{\"abc\":3,\"long-name\":1,\"z\":2}",
  )
  assert_true(compare_configured_c_text_v1("𐀀", "") > 0)
  for
    (a, b) in [
      ("𐀀", ""),
      ("abc", "ab"),
      ("中", "🙂"),
      ("é", "é"),
      ("", "a"),
    ] {
    let left = @utf8.encode(a[:])
    let right = @utf8.encode(b[:])
    let mut expected = 0
    let mut index = 0
    while index < left.length() && index < right.length() {
      if left[index] < right[index] {
        expected = -1
        break
      }
      if left[index] > right[index] {
        expected = 1
        break
      }
      index += 1
    }
    if expected == 0 {
      if left.length() < right.length() {
        expected = -1
      } else if left.length() > right.length() {
        expected = 1
      }
    }
    assert_eq(compare_configured_c_text_v1(a, b), expected)
  }
}

///|
test "sql37 31 duplicate config and unknown config properties rejected" {
  assert_true(
    parse_sql_config_v1(
      "{\"format\":\"x\",\"for\\u006dat\":\"x\",\"tables\":[]}",
    )
    is Err(_),
  )
  assert_true(
    parse_sql_config_v1(
      "{\"format\":\"moontxnwitness-configured-sql/v1\",\"tables\":[],\"trust\":true}",
    )
    is Err(_),
  )
}

///|
test "sql37 32 inline literal and RETURNING are not promoted to reads or server validation" {
  let report = sp37_normalize(
    "DELETE FROM app.flags WHERE enabled=false RETURNING *", "null",
  )
  assert_eq(v4_test_at(report, ["status"]), Json("recognized"))
  assert_eq(
    v4_test_at(report, ["descriptor", "returningIsPredicateRead"]),
    Json(false),
  )
  assert_eq(
    v4_test_at(report, ["descriptor", "databaseSyntaxValidated"]),
    Json(false),
  )
  assert_eq(v4_test_at(report, ["sourceWindowVerified"]), Json(false))
}

///|
test "sql37 33 named bind cannot impersonate keyword or quoted string an operator" {
  for
    source in [
      "SELECT account_no FROM ledger.accounts %(where)s account_no=1", "SELECT account_no FROM ledger.accounts WHERE account_no '=' 1",
    ] {
    assert_eq(
      v4_test_at(sp37_normalize(source, "null"), ["valid"]),
      Json(false),
    )
  }
}

///|
test "sql37 34 bare context value cannot impersonate configured column" {
  let config = parse_sql_config_v1(
    "{\"format\": \"moontxnwitness-configured-sql/v1\", \"tables\": [{\"schema\": \"s\", \"table\": \"t\", \"primaryKey\": \"id\", \"columns\": [{\"name\": \"id\", \"type\": \"int64\"}, {\"name\": \"current_user\", \"type\": \"text\", \"comparison\": \"postgres-c-utf8-v1\"}]}]}",
  ).unwrap()
  let invalid = sql_candidate_check_v1_json(
    normalize_sql_candidate_v1(
      config,
      "SELECT current_user FROM s.t",
      Json::null(),
    ),
  )
  let quoted = sql_candidate_check_v1_json(
    normalize_sql_candidate_v1(
      config,
      "SELECT \"current_user\" FROM s.t",
      Json::null(),
    ),
  )
  assert_eq(v4_test_at(invalid, ["valid"]), Json(false))
  assert_eq(v4_test_at(quoted, ["valid"]), Json(true))
}

///|
test "sql37 35 token cap excludes EOF and never reports over-limit stored tokens" {
  let source = "SELECT account_no FROM ledger.accounts"
  let report = sp37_normalize(source, "null")
  let count = match v4_test_at(report, ["execution", "tokens"]) {
    Number(n, ..) => n.to_int()
    _ => -1
  }
  assert_eq(
    v4_test_at(
      sp37_normalize(
        source,
        "null",
        options=sql_verification_options_v1(max_tokens=count),
      ),
      ["valid"],
    ),
    Json(true),
  )
  let limited = sp37_normalize(
    source,
    "null",
    options=sql_verification_options_v1(max_tokens=count - 1),
  )
  assert_eq(v4_test_at(limited, ["valid"]), Json(false))
  let stored = match v4_test_at(limited, ["execution", "tokens"]) {
    Number(n, ..) => n.to_int()
    _ => 1000000
  }
  assert_true(stored <= count - 1)
}

///|
test "sql37 36 huge integer spelling does not escape the literal-width contract" {
  assert_eq(
    v4_test_at(
      sp37_normalize(
        "SELECT account_no FROM ledger.accounts WHERE account_no=00000000000000000000",
        "null",
      ),
      ["valid"],
    ),
    Json(false),
  )
}
