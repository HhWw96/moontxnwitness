///|
test "draft search write trail admits all 512 live writes at exact operation budget" {
  let operations : Array[Operation] = []
  for i in 1..<513 {
    operations.push(write_op("x", "x" + i.to_string()))
  }
  let h = hist([tx("A", operations)])
  let (info, path, _, _) = search_optimized(
    h,
    Map([]),
    [],
    analysis_options(
      max_attempts=1,
      max_operation_checks=512,
      max_cached_states=0,
    ),
  )
  assert_eq(info.status, "found")
  assert_eq(info.attempts, 1)
  assert_eq(info.operation_checks, 512)
  assert_eq(path, Some(["A"]))
}

///|
test "draft search position trail retains all 512 per-transaction final writes" {
  let initial : Map[String, String] = Map([])
  let transactions : Array[Transaction] = []
  for i in 0..<128 {
    initial["k" + i.to_string()] = "v0"
  }
  for ti in 0..<4 {
    let operations : Array[Operation] = []
    for ki in 0..<128 {
      operations.push(
        write_op("k" + ki.to_string(), "v" + (ti + 1).to_string()),
      )
    }
    transactions.push(tx("T" + ti.to_string(), operations))
  }
  let h : History = {
    model: Serializable,
    initial,
    version_orders: Map([]),
    transactions,
  }
  let (info, path, _, _) = search_optimized(
    h,
    Map([]),
    [],
    analysis_options(
      max_attempts=4,
      max_operation_checks=512,
      max_cached_states=0,
    ),
  )
  assert_eq(info.status, "found")
  assert_eq(info.attempts, 4)
  assert_eq(info.operation_checks, 512)
  assert_eq(path, Some(["T0", "T1", "T2", "T3"]))
}

///|
fn draft_search_large_undo() -> History {
  let operations : Array[Operation] = [read_op("y", "y0")]
  for i in 1..<501 {
    operations.push(write_op("y", "y" + i.to_string()))
  }
  operations.push(read_op("x", "x1"))
  hist([tx("A", operations), tx("B", [write_op("x", "x1")])])
}

///|
test "draft search undo restores a long failed prefix before trying another order" {
  let (info, path, _, _) = search_optimized(
    draft_search_large_undo(),
    Map([]),
    [],
    analysis_options(
      max_attempts=3,
      max_operation_checks=1005,
      max_cached_states=0,
    ),
  )
  assert_eq(info.status, "found")
  assert_eq(info.attempts, 3)
  assert_eq(info.operation_checks, 1005)
  assert_eq(path, Some(["B", "A"]))
}

///|
test "draft search one missing operation cannot become exhausted" {
  let (info, path, _, _) = search_optimized(
    draft_search_large_undo(),
    Map([]),
    [],
    analysis_options(
      max_attempts=3,
      max_operation_checks=1004,
      max_cached_states=0,
    ),
  )
  assert_eq(info.status, "budget")
  assert_eq(info.attempts, 3)
  assert_eq(info.operation_checks, 1004)
  assert_eq(path, None)
}

///|
test "draft search does not raise the 512 operation admission limit" {
  let operations : Array[Operation] = []
  for i in 1..<514 {
    operations.push(write_op("x", "x" + i.to_string()))
  }
  let (info, path, _, _) = search_optimized(
    hist([tx("A", operations)]),
    Map([]),
    [],
    analysis_options(),
  )
  assert_eq(info.status, "skipped")
  assert_eq(info.attempts, 0)
  assert_eq(info.operation_checks, 0)
  assert_eq(path, None)
}
