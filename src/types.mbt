///|
/// The supported workload is a versioned, point-read register workload.
pub(all) enum OpKind {
  Read
  Write
} derive(Eq)

///|
pub(all) enum TxStatus {
  Committed
  Aborted
  Unknown
} derive(Eq)

///|
pub(all) enum Model {
  Serializable
  StrictSerializable
} derive(Eq)

///|
pub(all) struct Operation {
  kind : OpKind
  key : String
  version : String
} derive(Eq)

///|
pub(all) struct Transaction {
  id : String
  status : TxStatus
  ops : Array[Operation]
  start : Int64?
  end : Int64?
} derive(Eq)

///|
/// Version orders contain the initial version followed by all committed final writes.
pub(all) struct History {
  model : Model
  initial : Map[String, String]
  version_orders : Map[String, Array[String]]
  transactions : Array[Transaction]
} derive(Eq)

///|
pub(all) enum Dependency {
  WR
  WW
  RW
  RT
} derive(Eq, Hash)

///|
/// Operation indexes are zero-based. Initial versions have no transaction.
pub(all) struct Edge {
  from : String
  to : String
  kind : Dependency
  key : String?
  from_op : Int32?
  to_op : Int32?
  from_version : String?
  to_version : String?
  reason : String
} derive(Eq, Hash)

///|
pub extend Dependency with Hash::{hash, hash_combine}

///|
pub extend Edge with Hash::{hash, hash_combine}

///|
pub(all) struct Finding {
  code : String
  severity : String
  message : String
  transactions : Array[String]
  key : String?
  ops : Array[Int32]
} derive(Eq)

///|
pub(all) enum Outcome {
  Consistent
  Violation
  Inconclusive
  Invalid
} derive(Eq)

///|
/// Consistent is a claim about the supplied complete history and asserted version orders.
pub(all) struct Report {
  outcome : Outcome
  model : Model
  findings : Array[Finding]
  edges : Array[Edge]
  witness : Array[Edge]
  serial_order : Array[String]
  transaction_count : Int32
  committed_count : Int32
  operation_count : Int32
  inferred_orders : Map[String, Array[String]]
  order_sources : Map[String, String]
  search : SearchInfo
  graph : GraphInfo
  coverage : Array[KeyCoverage]
} derive(Eq)

///|
pub(all) struct GraphInfo {
  analyzed : Bool
  components : Int32
  cyclic_components : Int32
  cyclic_transactions : Int32
  bfs_roots : Int32
  edge_budget_exceeded : Bool
} derive(Eq)

///|
pub(all) struct KeyCoverage {
  key : String
  committed_reads : Int32
  committed_final_writes : Int32
  unresolved_reads : Int32
} derive(Eq)

///|
pub extend GraphInfo with Eq::{equal, not_equal}

///|
pub extend KeyCoverage with Eq::{equal, not_equal}

///|
pub(all) struct SearchInfo {
  status : String
  attempts : Int32
  operation_checks : Int32
  reason : String
  blockers : Array[Finding]
} derive(Eq)

///|
pub extend SearchInfo with Eq::{equal, not_equal}

///|
priv struct WriteRef {
  tx : Int32
  op : Int32
  is_final : Bool
}

///|
pub fn version() -> String {
  "0.3.9"
}

///|
fn op_label(k : OpKind) -> String {
  match k {
    Read => "read"
    Write => "write"
  }
}

///|
fn status_label(s : TxStatus) -> String {
  match s {
    Committed => "committed"
    Aborted => "aborted"
    Unknown => "unknown"
  }
}

///|
fn model_label(m : Model) -> String {
  match m {
    Serializable => "serializable"
    StrictSerializable => "strict-serializable"
  }
}

///|
fn dependency_label(d : Dependency) -> String {
  match d {
    WR => "wr"
    WW => "ww"
    RW => "rw"
    RT => "rt"
  }
}

///|
fn outcome_label(s : Outcome) -> String {
  match s {
    Consistent => "consistent"
    Violation => "violation"
    Inconclusive => "inconclusive"
    Invalid => "invalid"
  }
}

///|
fn issue(
  code : String,
  severity : String,
  message : String,
  txs~ : Array[String] = [],
  key~ : String? = None,
  ops~ : Array[Int32] = [],
) -> Finding {
  { code, severity, message, transactions: txs, key, ops, }
}

///|
pub extend OpKind with Eq::{equal, not_equal}

///|
pub extend TxStatus with Eq::{equal, not_equal}

///|
pub extend Model with Eq::{equal, not_equal}

///|
pub extend Operation with Eq::{equal, not_equal}

///|
pub extend Transaction with Eq::{equal, not_equal}

///|
pub extend History with Eq::{equal, not_equal}

///|
pub extend Dependency with Eq::{equal, not_equal}

///|
pub extend Edge with Eq::{equal, not_equal}

///|
pub extend Finding with Eq::{equal, not_equal}

///|
pub extend Outcome with Eq::{equal, not_equal}

///|
pub extend Report with Eq::{equal, not_equal}
