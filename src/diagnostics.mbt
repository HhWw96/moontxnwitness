///|
fn empty_graph() -> GraphInfo {
  {
    analyzed: false,
    components: 0,
    cyclic_components: 0,
    cyclic_transactions: 0,
    bfs_roots: 0,
    edge_budget_exceeded: false,
  }
}

///|
fn coverage_indexed(
  h : History,
  writes : Map[String, Map[String, WriteRef]],
) -> Array[KeyCoverage] {
  let reads : Map[String, Int] = Map([])
  let unresolved : Map[String, Int] = Map([])
  for tx in h.transactions {
    if tx.status != Committed {
      continue
    }
    for op in tx.ops {
      if op.kind != Read {
        continue
      }
      reads[op.key] = reads.get_or_default(op.key, 0) + 1
      if h.initial.get(op.key) != Some(op.version) {
        let source = writes.get_or_default(op.key, Map([])).get(op.version)
        if source is None ||
          (source is Some(w) && h.transactions[w.tx].status == Unknown) {
          unresolved[op.key] = unresolved.get_or_default(op.key, 0) + 1
        }
      }
    }
  }
  let result : Array[KeyCoverage] = []
  let keys = h.initial.keys().collect()
  keys.sort()
  for key in keys {
    let mut count = 0
    for _, w in writes.get_or_default(key, Map([])) {
      if w.is_final && h.transactions[w.tx].status == Committed {
        count += 1
      }
    }
    result.push({
      key,
      committed_reads: reads.get_or_default(key, 0),
      committed_final_writes: count,
      unresolved_reads: unresolved.get_or_default(key, 0),
    })
  }
  result
}

///|
fn order_source_cn(source : String, writes : Int) -> String {
  match source {
    "asserted" => "采集声明的版本链"
    "searched" => "搜索得到的可行补全（非观测事实）"
    "single-writer" =>
      if writes == 0 {
        "仅初始版本"
      } else {
        "单写者推断"
      }
    _ => "版本顺序缺失"
  }
}

///|
fn finding_cn(f : Finding) -> String {
  match f.code {
    "dependency_cycle" =>
      "这些事务的必要先后关系形成闭环，无法同时满足。"
    "no_serial_execution" =>
      "已穷尽预算范围内全部可行串行前缀，没有执行能重现所有读取和声明的版本顺序。"
    "aborted_read" =>
      "已提交事务读到了已回滚事务写入的版本。"
    "intermediate_read" =>
      "读到了其他事务在提交前已被自身后续写入覆盖的中间版本。"
    "future_read" => "事务读到了自己尚未执行的未来写入版本。"
    "read_your_writes" =>
      "事务没有读到自己最近一次写入的版本。"
    "non_repeatable_read" =>
      "没有自身写入介入，同一事务对同键读到了不同版本。"
    "missing_version_order" =>
      "多个已提交写者的版本先后未被采集，当前不能给出完整判断。"
    "missing_interval" =>
      "严格模型缺少共同观察时钟下的完整开始和结束时间。"
    "unknown_commit" =>
      "事务的提交结果未知，不能将它当作已提交事务。"
    "unknown_writer" =>
      "读取来源存在记录，但写者的提交结果未知。"
    "unobserved_version" =>
      "读取版本没有记录中的写者，可能缺少采集窗口或来源记录。"
    "edge_limit" =>
      "依赖数超出预算，图已截断，不能据此认定符合模型。"
    "search_limit" =>
      "精确补全未完成；查看 search 中的规模或计算预算原因。"
    _ => f.message
  }
}

///|
fn dependency_cn(d : Dependency) -> String {
  match d {
    WR =>
      "目标事务读到了来源事务的最终写入，来源事务必须先执行。"
    WW => "提供的同键版本链要求来源写入先于目标写入。"
    RW =>
      "来源事务读到了较早版本，必须先于写入较晚版本的目标事务。"
    RT =>
      "在共同观察时钟下，来源事务完成时间早于目标事务开始时间。"
  }
}

///|
fn next_steps(r : Report) -> Array[String] {
  let result : Array[String] = []
  for f in r.findings {
    let advice = match f.code {
      "missing_version_order" | "search_limit" =>
        "补采同键已提交最终写入的版本链，或提取预算内的小型复现窗口。"
      "missing_interval" =>
        "使用同一单调观察时钟记录已提交事务的开始和结束。"
      "unknown_commit" | "unknown_writer" =>
        "核对事务最终提交结果，保留未知状态直到有实际证据。"
      "unobserved_version" =>
        "扩大采集窗口并寻找读取版本的写入来源。"
      "edge_limit" =>
        "缩小原始采集窗口后重新分析；截断图不能提供完整的符合模型结论。"
      "dependency_cycle" | "no_serial_execution" =>
        "保留原始日志，使用 shrink 缩减反例，并用 capsule 保存可复现证据。"
      "duplicate_write_version" | "initial_version_reused" =>
        "重新采集，为每次同键写入分配唯一版本标记。"
      _ =>
        if f.severity == "error" {
          "按输入格式核对初始状态、事务标识、版本顺序和时间字段。"
        } else {
          "核对对应事务的操作下标和版本来源，保留原始采集记录。"
        }
    }
    if !result.contains(advice) && result.length() < 32 {
      result.push(advice)
    }
  }
  result
}
