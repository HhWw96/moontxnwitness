///|
fn safe_markdown(s : String) -> String {
  let b = StringBuilder()
  for c in s.iter() {
    match c {
      '&' => b.write_string("&amp;")
      '<' => b.write_string("&lt;")
      '>' => b.write_string("&gt;")
      '\\' | '`' | '[' | ']' | '*' | '_' | '|' | '#' => {
        b.write_char('\\')
        b.write_char(c)
      }
      '\n' | '\r' => b.write_char(' ')
      _ => b.write_char(c)
    }
  }
  b.to_string()
}

///|
fn outcome_cn(o : Outcome) -> String {
  match o {
    Consistent =>
      "符合所选模型（仅针对提供的历史与版本约束）"
    Violation => "发现确定的事务一致性异常"
    Inconclusive => "信息或分析预算不足，无法判定"
    Invalid => "输入不符合要求，未进行有效分析"
  }
}

///|
/// Render local text, Markdown, JSON or Graphviz DOT. No external renderer is required.
pub fn render_report(r : Report, format : String) -> String {
  if format == "json" {
    return report_string(r) + "\n"
  }
  let b = StringBuilder()
  if format == "dot" {
    b.write_string(
      "digraph MoonTxnWitness {\n  graph [rankdir=LR];\n  node [shape=box];\n",
    )
    for e in r.edges {
      let label = dependency_label(e.kind) +
        (match e.key {
          Some(k) => " · " + k
          None => ""
        })
      b.write_string(
        "  " +
        Json(e.from).stringify() +
        " -> " +
        Json(e.to).stringify() +
        " [label=" +
        Json(label).stringify(),
      )
      if r.witness.contains(e) {
        b.write_string(", color=\"#b42318\", penwidth=3")
      }
      b.write_string("];\n")
    }
    b.write_string("}\n")
    return b.to_string()
  }
  let markdown = format == "markdown"
  b.write_string(
    if markdown {
      "# MoonTxnWitness v"
    } else {
      "MoonTxnWitness v"
    },
  )
  b.write_string(version() + "\n\n" + outcome_cn(r.outcome) + "\n")
  b.write_string("模型：" + model_label(r.model) + "\n")
  b.write_string(
    "事务：" +
    r.transaction_count.to_string() +
    "；已提交：" +
    r.committed_count.to_string() +
    "；操作：" +
    r.operation_count.to_string() +
    "；依赖：" +
    r.edges.length().to_string() +
    "\n",
  )
  if !r.witness.is_empty() {
    b.write_string(
      if markdown {
        "\n## 异常环证据\n\n"
      } else {
        "\n异常环证据：\n"
      },
    )
    for i, e in r.witness {
      let from = if markdown { safe_markdown(e.from) } else { e.from }
      let target = if markdown { safe_markdown(e.to) } else { e.to }
      let key = match e.key {
        Some(k) => if markdown { safe_markdown(k) } else { k }
        None => "共同观察时钟"
      }
      b.write_string(
        (i + 1).to_string() +
        ". " +
        from +
        " → " +
        target +
        " [" +
        dependency_label(e.kind) +
        "，" +
        key +
        "]\n",
      )
      b.write_string("   " + dependency_cn(e.kind) + "\n")
      match (e.from_op, e.to_op, e.from_version, e.to_version) {
        (Some(a), Some(z), Some(v), Some(w)) => {
          let sv = if markdown { safe_markdown(v) } else { v }
          let sw = if markdown { safe_markdown(w) } else { w }
          b.write_string(
            "   操作下标 " +
            a.to_string() +
            " → " +
            z.to_string() +
            "，版本 " +
            sv +
            " → " +
            sw +
            "\n",
          )
        }
        _ => ()
      }
    }
    b.write_string(
      "\n证据包含构建图中事务数量最少的有向环；不声称整份历史已被全局最小化。\n",
    )
  }
  if !r.findings.is_empty() {
    b.write_string(
      if markdown {
        "\n## 发现与缺失信息\n\n"
      } else {
        "\n发现与缺失信息：\n"
      },
    )
    for f in r.findings {
      let message = if markdown {
        safe_markdown(finding_cn(f))
      } else {
        finding_cn(f)
      }
      b.write_string("- [" + f.severity + "] " + f.code + ": " + message)
      if !f.transactions.is_empty() {
        b.write_string(
          "；事务=" +
          (if markdown {
            f.transactions.map(safe_markdown)
          } else {
            f.transactions
          }).join(", "),
        )
      }
      b.write_string("\n")
    }
  }
  if !r.serial_order.is_empty() {
    b.write_string(
      "\n一个可行的串行顺序：" +
      (if markdown {
        r.serial_order.map(safe_markdown)
      } else {
        r.serial_order
      }).join(" → ") +
      "\n",
    )
  }
  if !r.coverage.is_empty() {
    b.write_string(
      if markdown {
        "\n## 版本来源\n\n"
      } else {
        "\n版本来源：\n"
      },
    )
    for i, k in r.coverage {
      if i >= 64 {
        b.write_string("其余键的统计请查看 JSON coverage。\n")
        break
      }
      let key = if markdown { safe_markdown(k.key) } else { k.key }
      b.write_string(
        "- " +
        key +
        "：已提交读 " +
        k.committed_reads.to_string() +
        "，最终写 " +
        k.committed_final_writes.to_string() +
        "，" +
        order_source_cn(r.order_sources.at(k.key), k.committed_final_writes) +
        "，来源未确定读 " +
        k.unresolved_reads.to_string() +
        "\n",
      )
    }
  }
  if r.search.status != "not-needed" {
    let label = match r.search.status {
      "found" => "找到可行串行执行（只证明存在）"
      "exhausted" => "穷尽候选，无法重现所有读取"
      "budget" => "计算预算用尽，无法判定"
      _ => "规模超出补全预算，无法判定"
    }
    b.write_string(
      "\n精确补全：" +
      label +
      "；尝试 " +
      r.search.attempts.to_string() +
      " 次。\n",
    )
  }
  let steps = next_steps(r)
  if !steps.is_empty() {
    b.write_string(
      if markdown {
        "\n## 下一步\n\n"
      } else {
        "\n下一步：\n"
      },
    )
    for step in steps {
      b.write_string("- " + step + "\n")
    }
  }
  b.write_string(
    "\n范围：唯一版本标记的点读写，可跨多个键组成事务。结论针对所提供历史；搜索得到的补全不是实际观测顺序，不能直接证明整个数据库可靠。\n",
  )
  b.to_string()
}

///|
fn exit_code(o : Outcome) -> Int32 {
  match o {
    Consistent => 0
    Violation => 1
    Invalid => 2
    Inconclusive => 3
  }
}

///|
/// Host transport combines a structured result and its MoonBit-rendered presentation.
pub fn run_json(text : String, format : String) -> String {
  let r = match parse_history(text) {
    Ok(h) => analyze(h)
    Err(message) => {
      let empty : History = {
        model: Serializable,
        initial: Map([]),
        version_orders: Map([]),
        transactions: [],
      }
      base_report(
        empty,
        Invalid,
        [issue("invalid_input", "error", message)],
        Map([]),
      )
    }
  }
  report_transport_string(r, format)
}

///|
/// Explicit history export is useful to library consumers and retains all recorded operations.
pub fn history_json(h : History) -> Json {
  let transactions = h.transactions.map(tx => {
    let ops = tx.ops.map(op => {
      (
        {
          "type": Json(op_label(op.kind)),
          "key": Json(op.key),
          "version": Json(op.version),
        } : Json)
    })
    let start = match tx.start {
      Some(v) => Json(v.to_double())
      None => Json::null()
    }
    let end = match tx.end {
      Some(v) => Json(v.to_double())
      None => Json::null()
    }
    (
      {
        "id": Json(tx.id),
        "status": Json(status_label(tx.status)),
        "ops": Json(ops),
        "start": start,
        "end": end,
      } : Json)
  })
  {
    "schemaVersion": 1,
    "model": Json(model_label(h.model)),
    "initial": Json(h.initial),
    "versionOrders": Json(h.version_orders),
    "transactions": Json(transactions),
  }
}
