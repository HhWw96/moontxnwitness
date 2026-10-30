///|
/// The three non-mixed input models understood by the structured analysis API.
pub(all) enum DataModelV4 {
  RegisterV4
  AppendListV4
  RelationSetV4
} derive(Eq)

///|
pub extend DataModelV4 with Eq::{equal, not_equal}

///|
priv enum HistoryV4Payload {
  RegisterSnapshot(History?, Json?)
  ListSnapshot(ListV3Parsed)
  RelationSnapshot(RelationV3Parsed)
}

///|
/// A validated, private snapshot. Constructors detach caller-owned collections.
pub struct HistoryV4 {
  priv data_model : DataModelV4
  priv source_text : String
  priv source_document : Json
  priv source_format : String
  priv payload : HistoryV4Payload
}

///|
/// Register defaults are the existing balanced profile; list/relation budgets
/// retain the original bounded interpreter limits. Unused fields grant no work.
/// Register analysis uses the balanced 12-transaction entry point; the legacy
/// `analyze` entry point and its budgets remain unchanged.
pub(all) struct AnalysisOptionsV4 {
  max_attempts : Int32
  max_states : Int32
  max_operation_checks : Int32
  max_cached_states : Int32
} derive(Eq)

///|
pub extend AnalysisOptionsV4 with Eq::{equal, not_equal}

///|
/// An analysis artifact is private so exported JSON cannot modify its history.
pub struct AnalysisV4 {
  priv data_model : DataModelV4
  priv outcome : Outcome
  priv record : Json
}

///|
pub fn analysis_options_v4(
  max_attempts~ : Int32 = 100000,
  max_states~ : Int32 = 100000,
  max_operation_checks~ : Int32 = 1000000,
  max_cached_states~ : Int32 = 50000,
) -> AnalysisOptionsV4 {
  { max_attempts, max_states, max_operation_checks, max_cached_states, }
}

///|
pub fn HistoryV4::data_model(self : HistoryV4) -> DataModelV4 {
  self.data_model
}

///|
/// Original bytes remain observations, never a completed or inferred history.
pub fn HistoryV4::source_text(self : HistoryV4) -> String {
  self.source_text
}

///|
pub fn AnalysisV4::data_model(self : AnalysisV4) -> DataModelV4 {
  self.data_model
}

///|
pub fn AnalysisV4::outcome(self : AnalysisV4) -> Outcome {
  self.outcome
}

///|
/// A source-preserving reduction under the fixed model-refutation predicate.
pub struct ReductionV4 {
  priv history : HistoryV4
  priv analysis : AnalysisV4
  priv record : Json
  priv status : String
  priv checks : Int32
  priv one_minimal : Bool
}

///|
pub fn ReductionV4::history(self : ReductionV4) -> HistoryV4 {
  self.history
}

///|
pub fn ReductionV4::analysis(self : ReductionV4) -> AnalysisV4 {
  self.analysis
}

///|
pub fn ReductionV4::status(self : ReductionV4) -> String {
  self.status
}

///|
pub fn ReductionV4::checks(self : ReductionV4) -> Int32 {
  self.checks
}

///|
pub fn ReductionV4::one_minimal(self : ReductionV4) -> Bool {
  self.one_minimal
}

///|
/// Category checks are distinct from full isolation-model classification.
pub struct ClassificationV4 {
  priv status : String
  priv record : Json
}

///|
pub fn ClassificationV4::status(self : ClassificationV4) -> String {
  self.status
}
