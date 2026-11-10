///|
/// Accelerate the digest primitive only. Verification decisions, input bytes,
/// logical check budgets and the portable implementation remain in MoonBit.
#cfg(target="js")
extern "js" fn source_digest_native(text : String) -> String =
  #| (text) => {
  #|   try {
  #|     const host = globalThis.process;
  #|     if (!host || typeof host.getBuiltinModule !== 'function' ||
  #|         typeof text.isWellFormed !== 'function' || !text.isWellFormed()) return '';
  #|     return host.getBuiltinModule('node:crypto').createHash('sha256').update(text, 'utf8').digest('hex');
  #|   } catch { return ''; }
  #| }

///|
#cfg(not(target="js"))
fn source_digest_native(_text : String) -> String {
  ""
}

///|
fn v3_dislock_sha256(text : String) -> String {
  let native = source_digest_native(text)
  if native.length() == 64 {
    native
  } else {
    v3_dislock_sha256_pure(text)
  }
}
