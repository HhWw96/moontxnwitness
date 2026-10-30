///|
/// Successful entries are exemptions from a SQL coverage gap, never source
/// authentication. The caller must still validate the full v3 lifecycle.
priv struct V3DislockSQLProof {
  verified_statements : Map[Int64, Bool]
  verified_facts : Map[Int64, Bool]
  verified_profiles : Map[String, Bool]
  gaps : Array[Json]
}

///|
priv struct V3DislockVersion {
  key : String
  present : Bool
  owner : Json
  expire_at : Json
  source : Int64
}

///|
priv struct V3DislockStatement {
  seq : Int64
  tx : String
  mapping : String
  parameters : Array[Json]
  facts : Array[Map[String, Json]]
  rows : Array[Array[Json]]
  row_sequences : Array[Int64]
  mut complete : Bool
}

///|
fn v3_dislock_text(value : Json, path : String) -> String raise {
  match value {
    String(text) => text
    _ => fail(path + " must be text")
  }
}

///|
fn v3_dislock_assert(condition : Bool, message : String) -> Unit raise {
  if !condition {
    fail(message)
  }
}

///|
fn v3_dislock_utf8(text : String) -> Array[UInt32] {
  let bytes : Array[UInt32] = []
  for ch in text.iter() {
    let n = ch.to_uint()
    if n <= 0x7fU {
      bytes.push(n)
    } else if n <= 0x7ffU {
      bytes.push(0xc0U | (n >> 6))
      bytes.push(0x80U | (n & 63U))
    } else if n <= 0xffffU {
      bytes.push(0xe0U | (n >> 12))
      bytes.push(0x80U | ((n >> 6) & 63U))
      bytes.push(0x80U | (n & 63U))
    } else {
      bytes.push(0xf0U | (n >> 18))
      bytes.push(0x80U | ((n >> 12) & 63U))
      bytes.push(0x80U | ((n >> 6) & 63U))
      bytes.push(0x80U | (n & 63U))
    }
  }
  bytes
}

///|
fn v3_dislock_ror(value : UInt32, count : Int32) -> UInt32 {
  (value >> count) | (value << (32 - count))
}

///|
/// SHA-256 only binds captured text to its declared digest; it does not attest
/// that PostgreSQL executed that text. Inputs here are bounded source/DDL.
fn v3_dislock_sha256(text : String) -> String {
  let bytes = v3_dislock_utf8(text)
  let bit_length = bytes.length().to_int64() * 8L
  bytes.push(128U)
  while bytes.length() % 64 != 56 {
    bytes.push(0U)
  }
  for i in 0..<8 {
    bytes.push(
      ((bit_length >> ((7 - i) * 8)) & 255L).to_int().reinterpret_as_uint(),
    )
  }
  let h : Array[UInt32] = [
    0x6a09e667U, 0xbb67ae85U, 0x3c6ef372U, 0xa54ff53aU, 0x510e527fU, 0x9b05688cU,
    0x1f83d9abU, 0x5be0cd19U,
  ]
  let k : Array[UInt32] = [
    0x428a2f98U, 0x71374491U, 0xb5c0fbcfU, 0xe9b5dba5U, 0x3956c25bU, 0x59f111f1U,
    0x923f82a4U, 0xab1c5ed5U, 0xd807aa98U, 0x12835b01U, 0x243185beU, 0x550c7dc3U,
    0x72be5d74U, 0x80deb1feU, 0x9bdc06a7U, 0xc19bf174U, 0xe49b69c1U, 0xefbe4786U,
    0x0fc19dc6U, 0x240ca1ccU, 0x2de92c6fU, 0x4a7484aaU, 0x5cb0a9dcU, 0x76f988daU,
    0x983e5152U, 0xa831c66dU, 0xb00327c8U, 0xbf597fc7U, 0xc6e00bf3U, 0xd5a79147U,
    0x06ca6351U, 0x14292967U, 0x27b70a85U, 0x2e1b2138U, 0x4d2c6dfcU, 0x53380d13U,
    0x650a7354U, 0x766a0abbU, 0x81c2c92eU, 0x92722c85U, 0xa2bfe8a1U, 0xa81a664bU,
    0xc24b8b70U, 0xc76c51a3U, 0xd192e819U, 0xd6990624U, 0xf40e3585U, 0x106aa070U,
    0x19a4c116U, 0x1e376c08U, 0x2748774cU, 0x34b0bcb5U, 0x391c0cb3U, 0x4ed8aa4aU,
    0x5b9cca4fU, 0x682e6ff3U, 0x748f82eeU, 0x78a5636fU, 0x84c87814U, 0x8cc70208U,
    0x90befffaU, 0xa4506cebU, 0xbef9a3f7U, 0xc67178f2U,
  ]
  for block in 0..<(bytes.length() / 64) {
    let w : Array[UInt32] = Array::make(64, 0U)
    for i in 0..<16 {
      let j = block * 64 + i * 4
      w[i] = (bytes[j] << 24) |
        (bytes[j + 1] << 16) |
        (bytes[j + 2] << 8) |
        bytes[j + 3]
    }
    for i in 16..<64 {
      let x = w[i - 15]
      let y = w[i - 2]
      let s0 = v3_dislock_ror(x, 7) ^ v3_dislock_ror(x, 18) ^ (x >> 3)
      let s1 = v3_dislock_ror(y, 17) ^ v3_dislock_ror(y, 19) ^ (y >> 10)
      w[i] = w[i - 16] + s0 + w[i - 7] + s1
    }
    let mut a = h[0]
    let mut b = h[1]
    let mut c = h[2]
    let mut d = h[3]
    let mut e = h[4]
    let mut f = h[5]
    let mut g = h[6]
    let mut z = h[7]
    for i in 0..<64 {
      let s1 = v3_dislock_ror(e, 6) ^
        v3_dislock_ror(e, 11) ^
        v3_dislock_ror(e, 25)
      let ch = (e & f) ^ (e.lnot() & g)
      let t1 = z + s1 + ch + k[i] + w[i]
      let s0 = v3_dislock_ror(a, 2) ^
        v3_dislock_ror(a, 13) ^
        v3_dislock_ror(a, 22)
      let maj = (a & b) ^ (a & c) ^ (b & c)
      let t2 = s0 + maj
      z = g
      g = f
      f = e
      e = d + t1
      d = c
      c = b
      b = a
      a = t1 + t2
    }
    h[0] += a
    h[1] += b
    h[2] += c
    h[3] += d
    h[4] += e
    h[5] += f
    h[6] += g
    h[7] += z
  }
  let out = StringBuilder()
  let alphabet = "0123456789abcdef"
  for word in h {
    for i in 0..<8 {
      out.write_char(
        alphabet[((word >> ((7 - i) * 4)) & 15U).reinterpret_as_int()]
        .to_int()
        .unsafe_to_char(),
      )
    }
  }
  out.to_string()
}

///|
fn v3_dislock_quote(text : String) -> String raise {
  let units = text.code_units()
  let mut at = 0
  while at < units.length() {
    let unit = units[at].to_int()
    if unit >= 0xd800 && unit <= 0xdbff {
      if at + 1 >= units.length() ||
        units[at + 1] < 0xdc00 ||
        units[at + 1] > 0xdfff {
        fail("PostgreSQL UTF-8 identifiers cannot contain unpaired surrogates")
      }
      at += 2
    } else {
      if unit >= 0xdc00 && unit <= 0xdfff {
        fail("PostgreSQL UTF-8 identifiers cannot contain unpaired surrogates")
      }
      at += 1
    }
  }
  let bytes = v3_dislock_utf8(text)
  v3_dislock_assert(
    bytes.length() > 0 && bytes.length() <= 63 && !bytes.contains(0U),
    "PostgreSQL identifier exceeds the fixed profile",
  )
  "\"" + text.replace_all(old="\"", new="\"\"") + "\""
}

///|
fn v3_dislock_digit(text : String, start : Int32, count : Int32) -> Int32 raise {
  let mut n = 0
  if start < 0 || start + count > text.length() {
    fail("Truncated timestamp")
  }
  for i in start..<(start + count) {
    let c = text[i].to_int()
    if c < 48 || c > 57 {
      fail("Timestamp requires decimal digits")
    }
    n = n * 10 + c - 48
  }
  n
}

///|
/// Aware Python datetime encoding only: Gregorian years 1..9999, six or fewer
/// fractional digits and minute timezone offsets. No lexical date comparison.
fn v3_dislock_time(value : Json) -> Int64 raise {
  let typed = object_fields(value, "aware datetime")
  known_fields(typed, ["captureType", "value"], "aware datetime")
  v3_dislock_assert(
    required(typed, "captureType", "datetime") == Json("datetime"),
    "Expected typed aware datetime",
  )
  let t = v3_dislock_text(
    required(typed, "value", "datetime"),
    "datetime.value",
  )
  if t.length() < 25 || t.length() > 32 {
    fail("Unsupported aware datetime encoding")
  }
  if t[4] != 45 || t[7] != 45 || t[10] != 32 || t[13] != 58 || t[16] != 58 {
    fail("Unsupported aware datetime separators")
  }
  let year = v3_dislock_digit(t, 0, 4)
  let month = v3_dislock_digit(t, 5, 2)
  let day = v3_dislock_digit(t, 8, 2)
  let hour = v3_dislock_digit(t, 11, 2)
  let minute = v3_dislock_digit(t, 14, 2)
  let second = v3_dislock_digit(t, 17, 2)
  let leap = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0)
  let months = [
    31,
    if leap {
      29
    } else {
      28
    },
    31,
    30,
    31,
    30,
    31,
    31,
    30,
    31,
    30,
    31,
  ]
  if year < 1 ||
    month < 1 ||
    month > 12 ||
    day < 1 ||
    day > months[month - 1] ||
    hour > 23 ||
    minute > 59 ||
    second > 59 {
    fail("Invalid aware datetime calendar fields")
  }
  let mut pos = 19
  let mut micros = 0
  if t[pos] == 46 {
    pos += 1
    let start = pos
    while pos < t.length() && t[pos] >= 48 && t[pos] <= 57 {
      pos += 1
    }
    let digits = pos - start
    if digits < 1 || digits > 6 {
      fail("Unsupported datetime precision")
    }
    micros = v3_dislock_digit(t, start, digits)
    for _ in digits..<6 {
      micros *= 10
    }
  }
  if pos + 6 != t.length() || (t[pos] != 43 && t[pos] != 45) || t[pos + 3] != 58 {
    fail("A minute timezone offset is required")
  }
  let oh = v3_dislock_digit(t, pos + 1, 2)
  let om = v3_dislock_digit(t, pos + 4, 2)
  if oh > 23 || om > 59 {
    fail("Invalid timezone offset")
  }
  let offset = (oh * 60 + om) * (if t[pos] == 43 { 1 } else { -1 })
  let y = year - 1
  let mut days = y * 365 + y / 4 - y / 100 + y / 400 + day - 1
  for i in 0..<(month - 1) {
    days += months[i]
  }
  (
    days.to_int64() * 86400L +
    (hour * 3600 + minute * 60 + second - offset * 60).to_int64()
  ) *
  1000000L +
  micros.to_int64()
}

///|
fn v3_dislock_ttl(value : Json) -> Int64 raise {
  let n = match value {
    Number(n, ..) if n >= -31536000.0 && n <= 31536000.0 => n
    _ => fail("Lease TTL exceeds the finite one-year Number profile")
  }
  let product = n * 1000000.0
  let truncated = product.to_int64()
  let remainder = product - truncated.to_double()
  let rounded = if remainder > 0.5 || (remainder == 0.5 && truncated % 2L != 0L) {
    truncated + 1L
  } else if remainder < -0.5 || (remainder == -0.5 && truncated % 2L != 0L) {
    truncated - 1L
  } else {
    truncated
  }
  rounded
}

///|
fn v3_dislock_oid(value : Json) -> Unit raise {
  match value {
    Number(n, ..) if n > 0.0 &&
      n <= 4294967295.0 &&
      n.to_int64().to_double() == n => ()
    _ => fail("A real PostgreSQL OID is required")
  }
}

///|
fn v3_dislock_substitute(
  template : String,
  schema : String,
  table : String,
) -> String raise {
  template
  .replace_all(old="\"__SCHEMA__\"", new=v3_dislock_quote(schema))
  .replace_all(old="\"__TABLE__\"", new=v3_dislock_quote(table))
}

///|
fn v3_dislock_source(
  short : String,
  schema : String,
  table : String,
) -> String raise {
  let template = match short {
    "before" =>
      "\n\nDECLARE previous uuid; was_present boolean;\nBEGIN\n  IF TG_OP='DELETE' THEN RAISE EXCEPTION 'dislock v3 profile does not support DELETE'; END IF;\n  IF NEW.key IS NULL OR NEW.value IS NULL OR NEW.expire_at IS NULL THEN RETURN NEW; END IF;\n  IF TG_OP='UPDATE' AND NEW.key IS DISTINCT FROM OLD.key THEN RAISE EXCEPTION 'dislock v3 key mutation unsupported'; END IF;\n  SELECT token,present INTO previous,was_present FROM \"__SCHEMA__\".\"_mtw_v3_state\" WHERE key=NEW.key FOR UPDATE;\n  IF NOT FOUND THEN RAISE EXCEPTION 'dislock v3 key outside declared domain'; END IF;\n  IF TG_OP='UPDATE' AND (NOT was_present OR previous IS DISTINCT FROM OLD.\"_mtw_v3_version\") THEN\n    RAISE EXCEPTION 'dislock v3 predecessor state mismatch';\n  END IF;\n  NEW.\"_mtw_v3_version\":=pg_catalog.gen_random_uuid();\n  INSERT INTO \"__SCHEMA__\".\"_mtw_v3_candidates\"(token,key,predecessor,action,owner,expire_at)\n    VALUES(NEW.\"_mtw_v3_version\",NEW.key,previous,TG_OP,NEW.value,NEW.expire_at);\n  RETURN NEW;\nEND\n\n"
    "after" =>
      "\n\nDECLARE previous uuid; candidate_key text; candidate_action text; changed integer;\nBEGIN\n  SELECT predecessor,key,action INTO STRICT previous,candidate_key,candidate_action\n    FROM \"__SCHEMA__\".\"_mtw_v3_candidates\" WHERE token=NEW.\"_mtw_v3_version\";\n  IF candidate_key IS DISTINCT FROM NEW.key OR candidate_action<>TG_OP THEN\n    RAISE EXCEPTION 'dislock v3 candidate does not match actual effect';\n  END IF;\n  UPDATE \"__SCHEMA__\".\"_mtw_v3_state\" SET token=NEW.\"_mtw_v3_version\",present=true WHERE key=NEW.key AND token=previous;\n  GET DIAGNOSTICS changed=ROW_COUNT;\n  IF changed<>1 THEN RAISE EXCEPTION 'dislock v3 actual effect source mismatch'; END IF;\n  INSERT INTO \"__SCHEMA__\".\"_mtw_v3_effects\"(token,key,predecessor,action,owner,expire_at)\n    VALUES(NEW.\"_mtw_v3_version\",NEW.key,previous,TG_OP,NEW.value,NEW.expire_at);\n  RETURN NEW;\nEND\n\n"
    "predecessor" =>
      "\n\nDECLARE previous text; matches integer;\nBEGIN\n  SELECT pg_catalog.count(*)::integer,pg_catalog.min(predecessor::text)\n    INTO matches,previous FROM \"__SCHEMA__\".\"_mtw_v3_candidates\" WHERE token=p_token::uuid;\n  IF matches<>1 THEN RAISE EXCEPTION 'dislock v3 unique immutable candidate missing'; END IF;\n  RETURN previous;\nEND\n\n"
    _ => fail("Unknown installation source")
  }
  v3_dislock_substitute(template, schema, table)
}

///|
fn v3_dislock_sql(
  mapping : String,
  schema : String,
  table : String,
) -> (String, String, Int32, Array[String], Array[Int32]) raise {
  let (original, executed, business, names, types) = match mapping {
    "dislock.acquire-schedule/1" =>
      (
        "\n        INSERT INTO \"__SCHEMA__\".\"__TABLE__\" (key, value, expire_at)\n        VALUES (%s, %s, %s)\n        ON CONFLICT (key) DO UPDATE\n        SET value = EXCLUDED.value,\n            expire_at = EXCLUDED.expire_at\n        WHERE \"__SCHEMA__\".\"__TABLE__\".expire_at <= NOW()\n        RETURNING key, expire_at;\n        ",
        "\n        INSERT INTO \"__SCHEMA__\".\"__TABLE__\" (key, value, expire_at)\n        VALUES (%s, %s, %s)\n        ON CONFLICT (key) DO UPDATE\n        SET value = EXCLUDED.value,\n            expire_at = EXCLUDED.expire_at\n        WHERE \"__SCHEMA__\".\"__TABLE__\".expire_at <= NOW()\n        RETURNING key, expire_at,OLD.\"_mtw_v3_version\"::text,NEW.\"_mtw_v3_version\"::text,OLD.value,OLD.expire_at,NOW(),\"__SCHEMA__\".\"_mtw_v3_predecessor\"(NEW.\"_mtw_v3_version\"::text),CASE WHEN OLD.key IS NULL THEN 'INSERT' ELSE 'UPDATE' END;\n        ",
        2,
        ["key", "expire_at"],
        [25, 1184],
      )
    "dislock.acquire-run/1" =>
      (
        "\n        INSERT INTO \"__SCHEMA__\".\"__TABLE__\" (key, value, expire_at)\n        VALUES (%s, %s, NOW() + (%s * INTERVAL '1 second'))\n        ON CONFLICT (key) DO UPDATE\n        SET value = EXCLUDED.value,\n            expire_at = EXCLUDED.expire_at\n        WHERE \"__SCHEMA__\".\"__TABLE__\".expire_at <= NOW()\n        RETURNING key, expire_at;\n        ",
        "\n        INSERT INTO \"__SCHEMA__\".\"__TABLE__\" (key, value, expire_at)\n        VALUES (%s, %s, NOW() + (%s * INTERVAL '1 second'))\n        ON CONFLICT (key) DO UPDATE\n        SET value = EXCLUDED.value,\n            expire_at = EXCLUDED.expire_at\n        WHERE \"__SCHEMA__\".\"__TABLE__\".expire_at <= NOW()\n        RETURNING key, expire_at,OLD.\"_mtw_v3_version\"::text,NEW.\"_mtw_v3_version\"::text,OLD.value,OLD.expire_at,NOW(),\"__SCHEMA__\".\"_mtw_v3_predecessor\"(NEW.\"_mtw_v3_version\"::text),CASE WHEN OLD.key IS NULL THEN 'INSERT' ELSE 'UPDATE' END;\n        ",
        2,
        ["key", "expire_at"],
        [25, 1184],
      )
    "dislock.read-current/1" =>
      (
        "\n        SELECT expire_at, value\n        FROM \"__SCHEMA__\".\"__TABLE__\"\n        WHERE key = %s;\n        ",
        "\n        SELECT expire_at, value,\"_mtw_v3_version\"::text\n        FROM \"__SCHEMA__\".\"__TABLE__\"\n        WHERE key = %s;\n        ",
        2,
        ["expire_at", "value"],
        [1184, 25],
      )
    "dislock.renew/1" =>
      (
        "\n        UPDATE \"__SCHEMA__\".\"__TABLE__\"\n        SET expire_at = NOW() + (%s * INTERVAL '1 second')\n        WHERE key = %s\n          AND value = %s\n        RETURNING expire_at;\n        ",
        "\n        UPDATE \"__SCHEMA__\".\"__TABLE__\"\n        SET expire_at = NOW() + (%s * INTERVAL '1 second')\n        WHERE key = %s\n          AND value = %s\n        RETURNING expire_at,OLD.\"_mtw_v3_version\"::text,NEW.\"_mtw_v3_version\"::text,OLD.value,OLD.expire_at,NOW();\n        ",
        1,
        ["expire_at"],
        [1184],
      )
    "dislock.expire/1" =>
      (
        "\n        UPDATE \"__SCHEMA__\".\"__TABLE__\"\n        SET expire_at = NOW()\n        WHERE key = %s\n          AND value = %s\n        RETURNING key;\n        ",
        "\n        UPDATE \"__SCHEMA__\".\"__TABLE__\"\n        SET expire_at = NOW()\n        WHERE key = %s\n          AND value = %s\n        RETURNING key,OLD.\"_mtw_v3_version\"::text,NEW.\"_mtw_v3_version\"::text,OLD.value,OLD.expire_at,NOW();\n        ",
        1,
        ["key"],
        [25],
      )
    "dislock.server-now/1" =>
      ("SELECT NOW();", "SELECT NOW();", 1, ["now"], [1184])
    _ => fail("Unsupported frozen dislock mapping")
  }
  (
    v3_dislock_substitute(original, schema, table),
    v3_dislock_substitute(executed, schema, table),
    business,
    names,
    types,
  )
}

///|
fn v3_dislock_ascii_json(text : String) -> String {
  let out = StringBuilder()
  out.write_char('"')
  let hex = "0123456789abcdef"
  for unit in text.code_units() {
    let n = unit.to_int()
    match n {
      34 => out.write_string("\\\"")
      92 => out.write_string("\\\\")
      8 => out.write_string("\\b")
      9 => out.write_string("\\t")
      10 => out.write_string("\\n")
      12 => out.write_string("\\f")
      13 => out.write_string("\\r")
      _ =>
        if n < 32 || n >= 127 {
          out.write_string("\\u")
          for shift in [12, 8, 4, 0] {
            out.write_char(hex[(n >> shift) & 15].to_int().unsafe_to_char())
          }
        } else {
          out.write_char(n.unsafe_to_char())
        }
    }
  }
  out.write_char('"')
  out.to_string()
}

///|
fn v3_dislock_ddl(schema : String, table : String) -> Array[String] raise {
  let q = v3_dislock_quote(schema) + "."
  let target = q + v3_dislock_quote(table)
  let version = "\"_mtw_v3_version\""
  let ddl = [
    "CREATE TABLE " +
    q +
    "\"_mtw_v3_installation\"(nonce uuid PRIMARY KEY,table_oid oid NOT NULL)",
    "CREATE TABLE " +
    q +
    "\"_mtw_v3_state\"(key text PRIMARY KEY,token uuid NOT NULL UNIQUE,present boolean NOT NULL)",
    "CREATE TABLE " +
    q +
    "\"_mtw_v3_candidates\"(token uuid PRIMARY KEY,key text NOT NULL,predecessor uuid NOT NULL,action text NOT NULL,owner text NOT NULL,expire_at timestamptz NOT NULL)",
    "CREATE TABLE " +
    q +
    "\"_mtw_v3_effects\"(token uuid PRIMARY KEY,key text NOT NULL,predecessor uuid NOT NULL UNIQUE,action text NOT NULL,owner text NOT NULL,expire_at timestamptz NOT NULL)",
    "ALTER TABLE " + target + " ADD COLUMN " + version + " uuid",
    "UPDATE " + target + " SET " + version + "=pg_catalog.gen_random_uuid()",
    "ALTER TABLE " + target + " ALTER COLUMN " + version + " SET NOT NULL",
  ]
  for name in ["before", "after", "predecessor"] {
    let source = v3_dislock_source(name, schema, table)
    let mut number = 0
    let mut delimiter = "$mtw$"
    while source.contains(delimiter) {
      number += 1
      delimiter = "$mtw" + number.to_string() + "$"
    }
    let signature = if name == "predecessor" { "p_token text" } else { "" }
    let result = if name == "predecessor" { "text" } else { "trigger" }
    ddl.push(
      "CREATE FUNCTION " +
      q +
      v3_dislock_quote("_mtw_v3_" + name) +
      "(" +
      signature +
      ") RETURNS " +
      result +
      " LANGUAGE plpgsql VOLATILE SECURITY INVOKER SET search_path=pg_catalog AS " +
      delimiter +
      source +
      delimiter,
    )
  }
  ddl.push(
    "CREATE TRIGGER \"_mtw_v3_before\" BEFORE INSERT OR UPDATE OR DELETE ON " +
    target +
    " FOR EACH ROW EXECUTE FUNCTION " +
    q +
    "\"_mtw_v3_before\"()",
  )
  ddl.push(
    "CREATE TRIGGER \"_mtw_v3_after\" AFTER INSERT OR UPDATE ON " +
    target +
    " FOR EACH ROW EXECUTE FUNCTION " +
    q +
    "\"_mtw_v3_after\"()",
  )
  ddl
}

///|
fn v3_dislock_simple_identifier(text : String) -> Bool {
  !text.is_empty() &&
  text
  .iter()
  .all(c => (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_') &&
  !(text[0] >= 48 && text[0] <= 57)
}

///|
fn v3_dislock_metadata(
  profile : Map[String, Json],
  schema : String,
  table : String,
) -> Unit raise {
  let m = object_fields(
    required(profile, "metadata", "SQL profile"),
    "metadata",
  )
  v3_dislock_assert(
    required(m, "versionColumn", "metadata") == Json("_mtw_v3_version"),
    "Unexpected provenance column",
  )
  let nonce = presence_capture_uuid(
    required(m, "installationNonce", "metadata"),
    "installation nonce",
  )
  let oid = required(m, "tableOid", "metadata")
  v3_dislock_oid(oid)
  let server = required(m, "serverVersion", "metadata")
  match server {
    Number(n, ..) if n >= 180000.0 &&
      n < 190000.0 &&
      n.to_int().to_double() == n => ()
    _ => fail("The frozen profile requires actual PostgreSQL 18 metadata")
  }
  let marker = object_fields(required(m, "marker", "metadata"), "marker")
  known_fields(marker, ["nonce", "tableOid"], "marker")
  v3_dislock_assert(
    required(marker, "nonce", "marker") == Json(nonce) &&
    required(marker, "tableOid", "marker") == oid,
    "Installation marker differs from actual nonce/relation",
  )
  let objects : Map[String, Bool] = Map([])
  for name in ["before", "after", "predecessor"] {
    let f = object_fields(required(m, name, "metadata"), name)
    let source = v3_dislock_source(name, schema, table)
    v3_dislock_assert(
      required(f, "source", name) == Json(source),
      "Installed function source differs from the frozen source",
    )
    v3_dislock_assert(
      required(f, "sourceSha256", name) == Json(v3_dislock_sha256(source)),
      "Installed source digest does not bind its raw source",
    )
    let catalog = required(f, "functionCatalog", name)
    let expected_catalog : Json = [
      Json(schema),
      Json("_mtw_v3_" + name),
      Json(source),
      false,
      "v",
      ["search_path=pg_catalog"],
      Json(if name == "predecessor" { 1 } else { 0 }),
      Json(if name == "predecessor" { "text" } else { "trigger" }),
      "plpgsql",
    ]
    v3_dislock_assert(
      catalog == expected_catalog,
      "Function namespace/name/security/volatility/config/arguments/result/language differs from the frozen profile",
    )
    let function_oid = required(f, "functionOid", name)
    v3_dislock_oid(function_oid)
    let identity = function_oid.stringify()
    v3_dislock_assert(
      !objects.contains(identity),
      "Owned function OIDs must be distinct",
    )
    objects[identity] = true
    if name != "predecessor" {
      let trigger_oid = required(f, "triggerOid", name)
      v3_dislock_oid(trigger_oid)
      let identity = trigger_oid.stringify()
      v3_dislock_assert(
        !objects.contains("trigger:" + identity),
        "Owned trigger OIDs must be distinct",
      )
      objects["trigger:" + identity] = true
      v3_dislock_assert(
        required(f, "triggerType", name) ==
        Json(if name == "before" { 31 } else { 21 }) &&
        required(f, "enabled", name) == Json("O") &&
        required(f, "argumentsHex", name) == Json(""),
        "Owned trigger event/enable/arguments changed",
      )
      let actual = v3_dislock_text(
        required(f, "triggerDefinition", name),
        "trigger definition",
      )
      let event = if name == "before" {
        "BEFORE INSERT OR DELETE OR UPDATE"
      } else {
        "AFTER INSERT OR UPDATE"
      }
      let quoted = "CREATE TRIGGER " +
        v3_dislock_quote("_mtw_v3_" + name) +
        " " +
        event +
        " ON " +
        v3_dislock_quote(schema) +
        "." +
        v3_dislock_quote(table) +
        " FOR EACH ROW EXECUTE FUNCTION " +
        v3_dislock_quote(schema) +
        "." +
        v3_dislock_quote("_mtw_v3_" + name) +
        "()"
      let simple = "CREATE TRIGGER _mtw_v3_" +
        name +
        " " +
        event +
        " ON " +
        schema +
        "." +
        table +
        " FOR EACH ROW EXECUTE FUNCTION " +
        schema +
        "._mtw_v3_" +
        name +
        "()"
      v3_dislock_assert(
        actual == quoted ||
        (
          v3_dislock_simple_identifier(schema) &&
          v3_dislock_simple_identifier(table) &&
          actual == simple
        ),
        "Owned trigger definition differs from the fixed profile",
      )
    }
  }
  let ddl = v3_dislock_ddl(schema, table)
  let encoded = "[" + ddl.map(v3_dislock_ascii_json).join(",") + "]"
  v3_dislock_assert(
    required(m, "installationDdlSha256", "metadata") ==
    Json(v3_dislock_sha256(encoded)),
    "Installation DDL digest differs from the exact generated DDL",
  )
}

///|
fn v3_dislock_source_equal(
  source : V3DislockVersion,
  key : String,
  owner : Json,
  expire : Json,
) -> Unit raise {
  v3_dislock_assert(
    source.key == key &&
    source.present &&
    source.owner == owner &&
    v3_dislock_time(source.expire_at) == v3_dislock_time(expire),
    "Same-statement OLD/read fields differ from their observed source version",
  )
}

///|
fn v3_dislock_fact(
  fact : Map[String, Json],
  statement : V3DislockStatement,
  kind : String,
  key : String,
  row : Int32,
) -> Map[String, Json] raise {
  v3_dislock_assert(
    required(fact, "kind", "fact") == Json(kind) &&
    required(fact, "tx", "fact") == Json(statement.tx) &&
    required(fact, "statement", "fact") == Json(statement.seq.to_double()) &&
    required(fact, "mappingId", "fact") == Json(statement.mapping),
    "Fact kind/transaction/statement/mapping binding mismatch",
  )
  let evidence = object_fields(
    required(fact, "evidence", "fact"),
    "fact evidence",
  )
  v3_dislock_assert(
    row < statement.row_sequences.length() &&
    v3_capture_seq(required(fact, "seq", "fact"), "fact.seq") >
    statement.row_sequences[row],
    "A mapped fact must follow its actual delivered server row",
  )
  v3_dislock_assert(
    required(evidence, "serverRow", "evidence") == Json(row),
    "Fact serverRow must be its cumulative actual row ordinal",
  )
  if kind == "condition" {
    v3_dislock_assert(
      required(evidence, "key", "evidence") == Json(key),
      "Condition key differs from SQL parameters",
    )
  } else {
    v3_dislock_assert(
      required(fact, "key", "fact") == Json(key),
      "Fact key differs from SQL parameters",
    )
  }
  evidence
}

///|
fn v3_dislock_params(mapping : String, raw : Json) -> Array[Json] raise {
  if mapping == "dislock.server-now/1" {
    v3_dislock_assert(
      raw == Json::null() || raw == Json::array([]),
      "Server NOW has no parameters",
    )
    return []
  }
  let p = presence_capture_array(raw, "parameters")
  let size = if mapping == "dislock.read-current/1" {
    1
  } else if mapping == "dislock.expire/1" {
    2
  } else {
    3
  }
  v3_dislock_assert(
    p.length() == size,
    "Exact positional parameter count required",
  )
  let key_index = if mapping == "dislock.renew/1" { 1 } else { 0 }
  let _ = identifier(p[key_index], "lease key")
  if mapping != "dislock.read-current/1" {
    let owner_index = if mapping == "dislock.renew/1" { 2 } else { 1 }
    let _ = v3_dislock_text(p[owner_index], "lease owner")
  }
  if mapping == "dislock.acquire-schedule/1" {
    let _ = v3_dislock_time(p[2])
  }
  if mapping == "dislock.acquire-run/1" {
    let _ = v3_dislock_ttl(p[2])
  }
  if mapping == "dislock.renew/1" {
    let _ = v3_dislock_ttl(p[0])
  }
  p
}

///|
fn v3_dislock_confirmed_abort(
  event : Map[String, Json],
  request : Int64?,
) -> Bool raise {
  if request is None {
    return true
  }
  let proof = match event.get("commitResponse") {
    None => return false
    Some(v) => object_fields(v, "COMMIT response")
  }
  v3_dislock_assert(
    required(proof, "request", "COMMIT response") ==
    Json(request.unwrap().to_double()),
    "COMMIT response request binding mismatch",
  )
  if proof.contains("commandTag") {
    known_fields(proof, ["request", "commandTag"], "COMMIT response")
    v3_dislock_assert(
      required(proof, "commandTag", "COMMIT response") == Json("ROLLBACK"),
      "Only actual COMMIT ROLLBACK confirms abortion",
    )
  } else {
    known_fields(
      proof,
      ["request", "sqlstate", "diagnosticSqlstate", "transactionStatus"],
      "COMMIT response",
    )
    let state = required(proof, "sqlstate", "COMMIT response")
    v3_dislock_assert(
      (state == Json("40001") || state == Json("40P01")) &&
      required(proof, "diagnosticSqlstate", "COMMIT response") == state &&
      required(proof, "transactionStatus", "COMMIT response") == Json("IDLE"),
      "Missing reliable server abort response",
    )
  }
  true
}

///|
/// A separate effect journal retains same-TX intermediate writes and discards
/// only explicitly rolled-back scopes. The outer normalizer owns full lifecycle
/// legality; no client ACK or UUID is used as a commit ordering fact.
fn v3_dislock_outcomes(
  events : Array[Json],
) -> (Map[String, String], Map[Int64, Bool]) raise {
  let outcomes : Map[String, String] = Map([])
  let writes : Map[String, Array[Int64]] = Map([])
  let scopes : Map[String, Array[(String, Int32)]] = Map([])
  let requests : Map[String, Int64] = Map([])
  let revoked : Map[Int64, Bool] = Map([])
  for raw in events {
    let e = object_fields(raw, "event")
    let kind = v3_dislock_text(required(e, "kind", "event"), "kind")
    if kind == "snapshot" {
      continue
    }
    let tx = identifier(required(e, "tx", "event"), "tx")
    let seq = v3_capture_seq(required(e, "seq", "event"), "seq")
    if kind == "begin" {
      outcomes[tx] = "unknown"
      writes[tx] = []
      scopes[tx] = []
      continue
    }
    if !writes.contains(tx) {
      fail("SQL proof lacks a transaction begin")
    }
    let tx_writes = writes.get(tx).unwrap()
    let tx_scopes = scopes.get(tx).unwrap()
    match kind {
      "write" => tx_writes.push(seq)
      "savepoint" =>
        tx_scopes.push(
          (
            identifier(required(e, "instance", "savepoint"), "instance"),
            tx_writes.length(),
          ),
        )
      "rollback_to" | "release" => {
        let instance = identifier(required(e, "instance", kind), "instance")
        let mut at = -1
        for index, scope in tx_scopes {
          if scope.0 == instance {
            at = index
          }
        }
        if at < 0 {
          fail("SQL proof lacks a live savepoint")
        }
        if kind == "rollback_to" {
          while tx_writes.length() > tx_scopes[at].1 {
            revoked[tx_writes.pop().unwrap()] = true
          }
        }
        let keep = if kind == "rollback_to" { at + 1 } else { at }
        while tx_scopes.length() > keep {
          let _ = tx_scopes.pop()
        }
      }
      "commit_request" => requests[tx] = seq
      "commit_ok" => outcomes[tx] = "committed"
      "rollback_ok" =>
        if v3_dislock_confirmed_abort(e, requests.get(tx)) {
          outcomes[tx] = "aborted"
          for seq in tx_writes {
            revoked[seq] = true
          }
        }
      _ => ()
    }
  }
  (outcomes, revoked)
}

///|
priv struct V3DislockSourceCheck {
  version : String
  key : String
  owner : Json
  expire_at : Json
  present : Bool
  before : Int64
}

///|
/// Complete installation/source claims require a complete observation window.
/// A separate lifecycle gap cannot replace these local proof prerequisites.
fn v3_dislock_source_window(root : Map[String, Json]) -> Array[Json] raise {
  let scope = object_fields(required(root, "scope", "trace"), "scope")
  v3_dislock_assert(
    required(scope, "exclusiveWriters", "scope") == Json(true),
    "Complete SQL provenance requires the declared exclusive writer scope",
  )
  let gaps = presence_capture_array(required(root, "gaps", "trace"), "gaps")
  v3_dislock_assert(
    gaps.is_empty(),
    "An explicit capture gap prevents a complete SQL source profile",
  )
  let events = presence_capture_array(
    required(root, "events", "trace"),
    "events",
  )
  v3_dislock_assert(
    !events.is_empty(),
    "A complete SQL profile needs its initial snapshot",
  )
  for index, raw in events {
    let event = object_fields(raw, "event")
    v3_dislock_assert(
      required(event, "seq", "event") == Json(index + 1),
      "Every SQL observation must have its original contiguous sequence number",
    )
  }
  let first = object_fields(events[0], "initial snapshot")
  v3_dislock_assert(
    required(first, "kind", "initial snapshot") == Json("snapshot") &&
    required(first, "consistent", "initial snapshot") == Json(true),
    "The first observation must be the consistent captured snapshot at sequence one",
  )
  events
}

///|
fn v3_dislock_prove_profile(
  root : Map[String, Json],
  profile : Map[String, Json],
) -> V3DislockSQLProof raise {
  let events = v3_dislock_source_window(root)
  let schema = identifier(required(profile, "schema", "SQL profile"), "schema")
  let table = identifier(required(profile, "table", "SQL profile"), "table")
  v3_dislock_assert(
    schema.has_prefix("mtw_provenance_"),
    "Only the controlled provenance schema is supported",
  )
  v3_dislock_metadata(profile, schema, table)
  let known : Map[String, Bool] = Map([])
  for
    key in presence_capture_array(
      required(profile, "knownKeys", "SQL profile"),
      "knownKeys",
    ) {
    let key = identifier(key, "lease key")
    v3_dislock_assert(!known.contains(key), "Known keys must be unique")
    known[key] = true
  }
  v3_dislock_assert(
    known.length() > 0 && known.length() <= 128,
    "Declare 1..128 fixed lease keys",
  )
  let snapshot = events.filter(raw => {
    object_fields_unchecked_v3(raw).get("kind") == Some(Json("snapshot"))
  })
  v3_dislock_assert(
    snapshot.length() == 1,
    "The profile needs exactly one initial snapshot",
  )
  let snapshot_fields = object_fields(snapshot[0], "snapshot")
  let snapshot_seq = v3_capture_seq(
    required(snapshot_fields, "seq", "snapshot"),
    "snapshot.seq",
  )
  let initial = object_fields(
    required(snapshot_fields, "initial", "snapshot"),
    "snapshot.initial",
  )
  let versions : Map[String, V3DislockVersion] = Map([])
  let initialized : Map[String, Bool] = Map([])
  let initial_state = presence_capture_array(
    required(profile, "initialState", "SQL profile"),
    "initialState",
  )
  for raw in initial_state {
    let row = object_fields(raw, "initial state")
    known_fields(
      row,
      ["key", "version", "present", "owner", "expireAt"],
      "initial state",
    )
    let key = identifier(required(row, "key", "initial state"), "key")
    let token = presence_capture_uuid(
      required(row, "version", "initial state"),
      "version",
    )
    let present = presence_capture_bool(
      required(row, "present", "initial state"),
      "present",
    )
    let owner = required(row, "owner", "initial state")
    let expire = required(row, "expireAt", "initial state")
    v3_dislock_assert(
      known.contains(key) &&
      !initialized.contains(key) &&
      initial.get(key) == Some(Json(token)) &&
      !versions.contains(token),
      "Initial state must cover each declared key/token exactly once",
    )
    if present {
      let _ = v3_dislock_text(owner, "initial owner")
      let _ = v3_dislock_time(expire)
    } else {
      v3_dislock_assert(
        owner == Json::null() && expire == Json::null(),
        "Absent initial versions cannot invent owner/expiry",
      )
    }
    initialized[key] = true
    versions[token] = {
      key,
      present,
      owner,
      expire_at: expire,
      source: snapshot_seq,
    }
  }
  v3_dislock_assert(
    initialized.length() == known.length(),
    "Initial state is incomplete",
  )
  v3_dislock_catalog(profile, initial_state)
  let statements : Map[Int64, V3DislockStatement] = Map([])
  let statement_order : Array[Int64] = []
  for raw in events {
    let e = object_fields(raw, "event")
    if e.get("kind") != Some(Json("statement")) {
      continue
    }
    let mapping = match e.get("mappingId") {
      Some(String(s)) if s.has_prefix("dislock.") => s
      _ => continue
    }
    let seq = v3_capture_seq(required(e, "seq", "statement"), "statement.seq")
    let sql = v3_dislock_sql(mapping, schema, table)
    v3_dislock_assert(
      required(e, "sql", "statement") == Json(sql.0) &&
      required(e, "executedSql", "statement") == Json(sql.1),
      "Frozen original/executed SQL mismatch",
    )
    let parameters = v3_dislock_params(
      mapping,
      required(e, "parameters", "statement"),
    )
    let tx = identifier(required(e, "tx", "statement"), "statement.tx")
    v3_dislock_assert(!statements.contains(seq), "Duplicate SQL statement seq")
    statements[seq] = {
      seq,
      tx,
      mapping,
      parameters,
      facts: [],
      rows: [],
      row_sequences: [],
      complete: false,
    }
    statement_order.push(seq)
  }
  for raw in events {
    let e = object_fields(raw, "event")
    let kind = v3_dislock_text(required(e, "kind", "event"), "event.kind")
    if !["rows", "read", "write", "condition"].contains(kind) {
      continue
    }
    let ref_seq = match e.get("statement") {
      Some(value) => v3_capture_seq(value, "statement reference")
      None => {
        let key = match e.get("key") {
          Some(String(key)) => key
          _ => ""
        }
        v3_dislock_assert(
          !known.contains(key),
          "Declared SQL profile operations require same-statement provenance",
        )
        continue
      }
    }
    let statement = match statements.get(ref_seq) {
      Some(s) => s
      None => continue
    }
    let seq = v3_capture_seq(required(e, "seq", "event"), "event.seq")
    v3_dislock_assert(
      seq > ref_seq && required(e, "tx", "event") == Json(statement.tx),
      "SQL observation must bind its preceding same-transaction statement",
    )
    if kind != "rows" {
      statement.facts.push(e)
      continue
    }
    v3_dislock_assert(
      !statement.complete && !e.contains("error"),
      "Failed or repeated-EOF statement cannot be proved",
    )
    let delivered = presence_capture_array(
      required(e, "rows", "rows"),
      "delivered rows",
    )
    let server = presence_capture_array(
      required(e, "serverRows", "rows"),
      "server rows",
    )
    v3_dislock_assert(
      delivered.length() == server.length(),
      "Actual/delivered batch lengths differ",
    )
    let shape = v3_dislock_sql(statement.mapping, schema, table)
    let columns = presence_capture_array(
      required(e, "columns", "rows"),
      "columns",
    )
    v3_dislock_assert(
      columns.length() == shape.2,
      "Business column count changed",
    )
    for index, column in columns {
      let c = object_fields(column, "column")
      known_fields(c, ["name", "typeCode"], "column")
      v3_dislock_assert(
        required(c, "name", "column") == Json(shape.3[index]) &&
        required(c, "typeCode", "column") == Json(shape.4[index]),
        "Business column name/type differs from the frozen SQL",
      )
    }
    for index, row in server {
      let actual = presence_capture_array(row, "server row")
      let prefix = presence_capture_array(delivered[index], "delivered row")
      v3_dislock_assert(
        prefix.length() == shape.2 && actual.length() >= shape.2,
        "Returned tuple arity mismatch",
      )
      for i in 0..<shape.2 {
        v3_dislock_assert(
          prefix[i] == actual[i],
          "Business results must be the actual server row prefix",
        )
      }
      statement.rows.push(actual)
      statement.row_sequences.push(seq)
    }
    v3_dislock_assert(
      statement.rows.length() <= 1,
      "Frozen point SQL returned multiple rows",
    )
    statement.complete = presence_capture_bool(
      required(e, "complete", "rows"),
      "rows.complete",
    )
  }
  let checks : Array[V3DislockSourceCheck] = []
  let written : Map[String, Json] = Map([])
  let write_sequences : Map[String, Int64] = Map([])
  let write_transactions : Map[String, String] = Map([])
  let tx_now : Map[String, Int64] = Map([])
  let verified_statements : Map[Int64, Bool] = Map([])
  let verified_facts : Map[Int64, Bool] = Map([])
  for seq in statement_order {
    let statement = statements.get(seq).unwrap()
    v3_dislock_assert(statement.complete, "SQL result was not fully delivered")
    // Zero rows may be absence or a failed owner/time guard. Without a reliable
    // same-statement source snapshot it cannot be flattened into a point read.
    v3_dislock_assert(
      statement.rows.length() == 1,
      "Zero-row SQL lacks a complete same-statement predicate source",
    )
    let row = statement.rows[0]
    let p = statement.parameters
    let mapping = statement.mapping
    let facts = statement.facts
    if mapping == "dislock.server-now/1" {
      v3_dislock_assert(
        row.length() == 1 && facts.is_empty(),
        "NOW must return exactly its original timestamp and no invented key facts",
      )
      let now = v3_dislock_time(row[0])
      match tx_now.get(statement.tx) {
        Some(old) =>
          v3_dislock_assert(old == now, "NOW changed within one transaction")
        None => tx_now[statement.tx] = now
      }
    } else {
      let key_index = if mapping == "dislock.renew/1" { 1 } else { 0 }
      let key = identifier(p[key_index], "lease key")
      v3_dislock_assert(
        known.contains(key),
        "Lease key is outside the frozen profile domain",
      )
      if mapping == "dislock.read-current/1" {
        v3_dislock_assert(
          row.length() == 3 && facts.length() == 1,
          "Point read needs its actual token and exactly one read fact",
        )
        let token = presence_capture_uuid(row[2], "read token")
        let _ = v3_dislock_time(row[0])
        let _ = v3_dislock_text(row[1], "read owner")
        let proof = v3_dislock_fact(facts[0], statement, "read", key, 0)
        known_fields(proof, ["serverRow"], "read evidence")
        v3_dislock_assert(
          required(facts[0], "version", "read fact") == Json(token),
          "Read version differs from same-statement server token",
        )
        checks.push({
          version: token,
          key,
          owner: row[1],
          expire_at: row[0],
          present: true,
          before: v3_capture_seq(
            required(facts[0], "seq", "read fact"),
            "read seq",
          ),
        })
      } else {
        let upsert = mapping == "dislock.acquire-schedule/1" ||
          mapping == "dislock.acquire-run/1"
        v3_dislock_assert(
          row.length() == (if upsert { 9 } else { 6 }),
          "Unexpected actual mutation RETURNING shape",
        )
        let offset = if upsert { 1 } else { 0 }
        let old_token = row[1 + offset]
        let new_token = presence_capture_uuid(
          row[2 + offset],
          "actual NEW token",
        )
        let old_owner = row[3 + offset]
        let old_expire = row[4 + offset]
        let server_now = row[5 + offset]
        let now = v3_dislock_time(server_now)
        match tx_now.get(statement.tx) {
          Some(old) =>
            v3_dislock_assert(old == now, "NOW changed within one transaction")
          None => tx_now[statement.tx] = now
        }
        let action = if upsert {
          v3_dislock_text(row[8], "actual action")
        } else {
          "UPDATE"
        }
        v3_dislock_assert(
          action == "INSERT" || action == "UPDATE",
          "Mutation action must be an actual I/U effect",
        )
        let predecessor = if upsert {
          presence_capture_uuid(row[7], "actual immutable predecessor")
        } else {
          presence_capture_uuid(old_token, "actual OLD token")
        }
        if upsert {
          v3_dislock_assert(
            row[0] == Json(key),
            "Returned key differs from parameters",
          )
        }
        if action == "INSERT" {
          v3_dislock_assert(
            upsert &&
            old_token == Json::null() &&
            old_owner == Json::null() &&
            old_expire == Json::null(),
            "INSERT must not invent an OLD row",
          )
        } else {
          v3_dislock_assert(
            old_token == Json(predecessor),
            "UPDATE predecessor must be the actual OLD token",
          )
          let _ = v3_dislock_text(old_owner, "actual OLD owner")
          let _ = v3_dislock_time(old_expire)
          if upsert {
            v3_dislock_assert(
              v3_dislock_time(old_expire) <= now,
              "Acquisition claimed an unexpired conflict row",
            )
          } else {
            v3_dislock_assert(
              old_owner == p[if mapping == "dislock.renew/1" { 2 } else { 1 }],
              "Actual owner predicate did not match bound owner",
            )
          }
        }
        let new_owner = if upsert { p[1] } else { old_owner }
        let new_expire = if mapping == "dislock.expire/1" {
          server_now
        } else {
          row[if upsert { 1 } else { 0 }]
        }
        if mapping == "dislock.acquire-schedule/1" {
          v3_dislock_assert(
            v3_dislock_time(new_expire) == v3_dislock_time(p[2]),
            "Scheduled expiry differs from bound timestamp",
          )
        } else if mapping == "dislock.expire/1" {
          v3_dislock_assert(
            row[0] == Json(key),
            "Expire RETURNING key differs from bound key",
          )
        } else {
          let ttl = v3_dislock_ttl(p[if upsert { 2 } else { 0 }])
          v3_dislock_assert(
            v3_dislock_time(new_expire) == now + ttl,
            "Expiry differs from actual transaction NOW plus bound interval",
          )
        }
        let expected_facts = if action == "INSERT" { 1 } else { 2 }
        v3_dislock_assert(
          facts.length() == expected_facts,
          "Mutation facts are incomplete or include invented reads",
        )
        let write = facts[0]
        let proof = v3_dislock_fact(write, statement, "write", key, 0)
        known_fields(proof, ["serverRow", "action"], "write evidence")
        v3_dislock_assert(
          required(proof, "action", "write evidence") == Json(action) &&
          required(write, "version", "write") == Json(new_token) &&
          required(write, "predecessor", "write") == Json(predecessor),
          "Write identity/action/predecessor differs from actual RETURNING",
        )
        let write_seq = v3_capture_seq(
          required(write, "seq", "write"),
          "write seq",
        )
        v3_dislock_assert(
          new_token != predecessor && !versions.contains(new_token),
          "Mutation must create a fresh global token",
        )
        versions[new_token] = {
          key,
          present: true,
          owner: new_owner,
          expire_at: new_expire,
          source: write_seq,
        }
        write_sequences[new_token] = write_seq
        write_transactions[new_token] = statement.tx
        written[new_token] = {
          "key": Json(key),
          "version": Json(new_token),
          "predecessor": Json(predecessor),
          "action": Json(action),
          "owner": new_owner,
          "expireAt": new_expire,
        }
        checks.push({
          version: predecessor,
          key,
          owner: old_owner,
          expire_at: old_expire,
          present: action != "INSERT",
          before: write_seq,
        })
        if action != "INSERT" {
          let condition = facts[1]
          let condition_proof = v3_dislock_fact(
            condition, statement, "condition", key, 0,
          )
          known_fields(
            condition_proof,
            [
              "serverRow", "key", "owner", "oldOwner", "oldExpireAt", "serverNow",
              "oldToken", "newToken", "action",
            ],
            "condition evidence",
          )
          let owner = if upsert {
            p[1]
          } else {
            p[if mapping == "dislock.renew/1" { 2 } else { 1 }]
          }
          let predicate = if upsert { "lease-expired" } else { "owner-equals" }
          v3_dislock_assert(
            required(condition, "predicate", "condition") == Json(predicate) &&
            required(condition, "matched", "condition") == Json(true) &&
            required(condition, "sourceVersion", "condition") ==
            Json(predecessor),
            "Condition fact differs from the real SQL predicate",
          )
          for
            pair in [
              ("owner", owner),
              ("oldOwner", old_owner),
              ("oldExpireAt", old_expire),
              ("serverNow", server_now),
              ("oldToken", old_token),
              ("newToken", Json(new_token)),
              ("action", Json(action)),
            ] {
            v3_dislock_assert(
              required(condition_proof, pair.0, "condition evidence") == pair.1,
              "Condition evidence differs from bound parameters/actual OLD/NEW/NOW",
            )
          }
        }
      }
    }
    verified_statements[seq] = true
    for fact in facts {
      verified_facts[v3_capture_seq(required(fact, "seq", "fact"), "fact.seq")] = true
    }
  }
  for check in checks {
    let source = match versions.get(check.version) {
      Some(source) => source
      None => fail("Same-statement provenance refers to an unknown source")
    }
    v3_dislock_assert(
      source.source < check.before &&
      source.key == check.key &&
      source.present == check.present,
      "Missing/future/mismatched row source",
    )
    if check.present {
      v3_dislock_source_equal(source, check.key, check.owner, check.expire_at)
    } else {
      v3_dislock_assert(
        source.owner == Json::null() && source.expire_at == Json::null(),
        "INSERT predecessor is not a captured absence",
      )
    }
  }
  let (outcomes, revoked) = v3_dislock_outcomes(events)
  let expected_ledger : Map[String, Json] = Map([])
  for token, row in written {
    let seq = write_sequences.get(token).unwrap()
    let tx = write_transactions.get(token).unwrap()
    if outcomes.get(tx) == Some("committed") && !revoked.contains(seq) {
      expected_ledger[token] = row
    }
  }
  let actual_ledger = presence_capture_array(
    required(profile, "effectLedger", "profile"),
    "effectLedger",
  )
  v3_dislock_assert(
    actual_ledger.length() == expected_ledger.length(),
    "Actual committed effect ledger is missing/unexpected writes",
  )
  let ledger_seen : Map[String, Bool] = Map([])
  for raw in actual_ledger {
    let row = object_fields(raw, "effect ledger row")
    known_fields(
      row,
      ["key", "version", "predecessor", "action", "owner", "expireAt"],
      "effect ledger row",
    )
    let token = presence_capture_uuid(
      required(row, "version", "effect ledger row"),
      "ledger token",
    )
    v3_dislock_assert(
      !ledger_seen.contains(token) && expected_ledger.get(token) == Some(raw),
      "Actual effect ledger differs from observed committed unreverted effects",
    )
    ledger_seen[token] = true
  }
  let profiles : Map[String, Bool] = Map([])
  profiles[Json([Json("dislock-f9946f0-v3/1"), Json(schema), Json(table)]).stringify()] = true
  {
    verified_statements,
    verified_facts,
    verified_profiles: profiles,
    gaps: [],
  }
}

///|
fn v3_dislock_sql_proof(root : Map[String, Json]) -> V3DislockSQLProof raise {
  let empty : V3DislockSQLProof = {
    verified_statements: Map([]),
    verified_facts: Map([]),
    verified_profiles: Map([]),
    gaps: [],
  }
  let profiles = match root.get("sqlProfiles") {
    None => return empty
    Some(value) => presence_capture_array(value, "sqlProfiles")
  }
  let selected = profiles.filter(value => {
    object_fields_unchecked_v3(value).get("profile") ==
    Some(Json("dislock-f9946f0-v3/1"))
  })
  if selected.is_empty() {
    return empty
  }
  if selected.length() != 1 {
    empty.gaps.push(
      capture_gap(
        "dislock_multiple_profiles", "The current fixed SQL proof supports one controlled dislock installation",
      ),
    )
    return empty
  }
  v3_dislock_prove_profile(root, object_fields(selected[0], "dislock profile")) catch {
    error => {
      empty.gaps.push(capture_gap("dislock_sql_proof_gap", error.to_string()))
      empty
    }
  }
}

///|
/// Independent semantic diagnostic; successful matching does not authenticate
/// that the input came from a database. It grants no normalization exemptions.
pub fn dislock_sql_v3_proof_json(text : String) -> String {
  try {
    let root = object_fields(guarded_json(text, limit=8388608), "trace")
    let lifecycle = object_fields(
      guarded_json(normalize_register_capture_v3_json(text), limit=33554432),
      "v3 lifecycle",
    )
    if required(lifecycle, "status", "v3 lifecycle") == Json("invalid") {
      fail(
        "Invalid v3 structure/lifecycle cannot receive SQL verification claims",
      )
    }
    let proof = v3_dislock_sql_proof(root)
    let statements : Array[Int64] = []
    let facts : Array[Int64] = []
    let profiles : Array[String] = []
    for seq, _ in proof.verified_statements {
      statements.push(seq)
    }
    for seq, _ in proof.verified_facts {
      facts.push(seq)
    }
    for name, _ in proof.verified_profiles {
      profiles.push(name)
    }
    statements.sort()
    facts.sort()
    profiles.sort()
    let result : Json = {
      "algorithm": "dislock-f9946f0-sql-proof-1",
      "analysisCoverageAccepted": false,
      "verifiedStatements": Json(statements.map(seq => seq.to_double())),
      "verifiedFacts": Json(facts.map(seq => seq.to_double())),
      "verifiedProfiles": Json(profiles),
      "gaps": Json(proof.gaps),
      "scope": "Semantic coherence of fixed SQL, source/catalog observations and actual effect ledgers; no database authenticity claim or automatic coverage exemption.",
    }
    result.stringify(indent=2)
  } catch {
    error => {
      let result : Json = {
        "algorithm": "dislock-f9946f0-sql-proof-1",
        "analysisCoverageAccepted": false,
        "verifiedStatements": [],
        "verifiedFacts": [],
        "verifiedProfiles": [],
        "gaps": [capture_gap("invalid_dislock_sql_proof", error.to_string())],
        "scope": "Malformed input cannot grant SQL coverage exemptions.",
      }
      result.stringify(indent=2)
    }
  }
}

///|
fn v3_dislock_constraint(kind : String, column : Int32) -> Json {
  [Json(kind), [Json(column)], true, true, false, false]
}

///|
fn v3_dislock_catalog_entry(
  raw : Json,
  columns : Json,
  semantic : Array[Json],
  triggers : Array[Json],
  relation_oids : Map[String, Bool],
  expected_oid : Json?,
) -> Unit raise {
  let e = object_fields(raw, "catalog entry")
  known_fields(
    e,
    [
      "relation", "columns", "constraints", "userTriggerOids", "unsafeEffects", "indexCount",
    ],
    "catalog entry",
  )
  let relation = presence_capture_array(
    required(e, "relation", "catalog"),
    "relation",
  )
  v3_dislock_assert(
    relation.length() == 5,
    "Catalog relation tuple must have all five observed fields",
  )
  v3_dislock_oid(relation[0])
  match expected_oid {
    Some(oid) =>
      v3_dislock_assert(relation[0] == oid, "Catalog relation OID changed")
    None => ()
  }
  let id = relation[0].stringify()
  v3_dislock_assert(
    !relation_oids.contains(id),
    "Owned metadata/business relations must be distinct",
  )
  relation_oids[id] = true
  v3_dislock_assert(
    relation[1] == Json("r") &&
    relation[2] == Json(false) &&
    relation[3] == Json(false) &&
    relation[4] == Json("p"),
    "Ordinary permanent tables without RLS are required",
  )
  v3_dislock_assert(
    required(e, "columns", "catalog") == columns,
    "Catalog columns/types/NOT NULL/generated/identity changed",
  )
  let n = presence_capture_array(columns, "expected columns").length()
  let expected = semantic.copy()
  for col in 1..<(n + 1) {
    expected.push(v3_dislock_constraint("n", col))
  }
  let observed = presence_capture_array(
    required(e, "constraints", "catalog"),
    "constraints",
  )
  v3_dislock_assert(
    observed.length() == expected.length(),
    "Unexpected/missing catalog constraints",
  )
  let seen : Map[String, Bool] = Map([])
  for row in observed {
    let identity = row.stringify()
    v3_dislock_assert(
      expected.contains(row) && !seen.contains(identity),
      "Catalog constraints differ or contain duplicates",
    )
    seen[identity] = true
  }
  let actual_triggers = presence_capture_array(
    required(e, "userTriggerOids", "catalog"),
    "userTriggerOids",
  )
  v3_dislock_assert(
    actual_triggers.length() == triggers.length(),
    "Unexpected/missing user triggers",
  )
  let trigger_seen : Map[String, Bool] = Map([])
  for trigger in actual_triggers {
    v3_dislock_oid(trigger)
    let id = trigger.stringify()
    v3_dislock_assert(
      triggers.contains(trigger) && !trigger_seen.contains(id),
      "User trigger identity differs from the verified trigger list",
    )
    trigger_seen[id] = true
  }
  v3_dislock_assert(
    required(e, "indexCount", "catalog") == Json(semantic.length()),
    "Unregistered indexes are unsupported",
  )
  let effects = object_fields(
    required(e, "unsafeEffects", "catalog"),
    "unsafeEffects",
  )
  let names = [
    "foreignKeys", "rewriteRules", "checkConstraints", "exclusionConstraints", "generatedColumns",
    "expressionIndexes", "partialIndexes", "customTypes", "inheritance", "nondeterministicCollations",
    "customIndexOperators", "nonBtreeIndexes", "nondeterministicIndexCollations",
  ]
  known_fields(effects, names, "unsafeEffects")
  for name in names {
    v3_dislock_assert(
      required(effects, name, "unsafeEffects") == Json(0),
      "Catalog feature can execute unobserved SQL or change the fixed model",
    )
  }
}

///|
fn v3_dislock_catalog(
  profile : Map[String, Json],
  initial_state : Array[Json],
) -> Unit raise {
  let metadata = object_fields(
    required(profile, "metadata", "profile"),
    "metadata",
  )
  let catalog = object_fields(
    required(metadata, "catalog", "metadata"),
    "catalog",
  )
  known_fields(catalog, ["business", "owned"], "catalog")
  let before = object_fields(required(metadata, "before", "metadata"), "before")
  let after = object_fields(required(metadata, "after", "metadata"), "after")
  let table_oid = required(metadata, "tableOid", "metadata")
  let relation_oids : Map[String, Bool] = Map([])
  let columns : Json = [
    ["key", "text", true, "", ""],
    ["value", "text", true, "", ""],
    ["expire_at", "timestamp with time zone", true, "", ""],
    ["_mtw_v3_version", "uuid", true, "", ""],
  ]
  v3_dislock_catalog_entry(
    required(catalog, "business", "catalog"),
    columns,
    [v3_dislock_constraint("p", 1)],
    [
      required(before, "triggerOid", "before"),
      required(after, "triggerOid", "after"),
    ],
    relation_oids,
    Some(table_oid),
  )
  let owned = object_fields(required(catalog, "owned", "catalog"), "owned")
  known_fields(
    owned,
    ["installation", "state", "candidates", "effects"],
    "owned",
  )
  for name in ["installation", "state", "candidates", "effects"] {
    let columns : Json = match name {
      "installation" => [["nonce", "uuid", true], ["table_oid", "oid", true]]
      "state" =>
        [
          ["key", "text", true],
          ["token", "uuid", true],
          ["present", "boolean", true],
        ]
      _ =>
        [
          ["token", "uuid", true],
          ["key", "text", true],
          ["predecessor", "uuid", true],
          ["action", "text", true],
          ["owner", "text", true],
          ["expire_at", "timestamp with time zone", true],
        ]
    }
    let semantic = [v3_dislock_constraint("p", 1)]
    if name == "state" {
      semantic.push(v3_dislock_constraint("u", 2))
    }
    if name == "effects" {
      semantic.push(v3_dislock_constraint("u", 3))
    }
    v3_dislock_catalog_entry(
      required(owned, name, "owned"),
      columns,
      semantic,
      [],
      relation_oids,
      None,
    )
  }
  let window = presence_capture_array(
    required(metadata, "initializationWindow", "metadata"),
    "initializationWindow",
  )
  v3_dislock_assert(
    window.length() == 5,
    "Initialization lock/snapshot/commit window must be complete",
  )
  let expected : Array[Json] = [
    { "kind": "begin", "commandTag": "BEGIN" },
    {
      "kind": "lock",
      "tableOid": table_oid,
      "mode": "ACCESS EXCLUSIVE",
      "commandTag": "LOCK TABLE",
    },
    { "kind": "catalog", "tableOid": table_oid },
    { "kind": "snapshot", "rows": Json(initial_state) },
    { "kind": "commit", "commandTag": "COMMIT" },
  ]
  for i in 0..<5 {
    v3_dislock_assert(
      window[i] == expected[i],
      "Initialization window observations do not prove the controlled locked snapshot",
    )
  }
}
