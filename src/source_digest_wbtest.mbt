///|
test "source SHA preserves independently generated UTF-8 vectors" {
  let vectors = [
    ("", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
    ("abc", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"),
    (
      "源🙂é", "7f0536f6e53098e37b3556e2ff6b49351cf9ff7608a9800123f03bebe29d7b0a",
    ),
    (
      "e\u0301\u0000\r\n", "c229d758e71fe1272fa69a64fddc75a978375f7f33adf1156bea0719b0c02eee",
    ),
    (
      "👩\u200d💻", "427274538f1f24ef137872891551ffb4263f6edd90c80c533534578e8a5a9893",
    ),
  ]
  for (text, expected) in vectors {
    assert_eq(v3_dislock_sha256_pure(text), expected)
    assert_eq(v3_dislock_sha256(text), expected)
  }
}

///|
test "source SHA native and portable paths agree on long Unicode" {
  let builder = StringBuilder()
  for _ in 0..<2048 {
    builder.write_string("source 源🙂e\u0301\r\n")
  }
  let text = builder.to_string()
  assert_eq(v3_dislock_sha256(text), v3_dislock_sha256_pure(text))
}

///|
test "source SHA preserves compression and padding boundaries" {
  for length in [1, 55, 56, 63, 64, 65, 127, 128, 129, 1024, 4096] {
    let builder = StringBuilder()
    for _ in 0..<length {
      builder.write_char('a')
    }
    let text = builder.to_string()
    assert_eq(v3_dislock_sha256(text), v3_dislock_sha256_pure(text))
  }
}
