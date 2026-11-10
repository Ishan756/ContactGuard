export type HealthStatus = "healthy" | "degraded" | "unhealthy";
export type DocumentStatus = "pending" | "processing" | "completed" | "failed" | "needs_ocr";
export type RunStatus = "pending" | "running" | "completed" | "failed";
export type ClauseValidationStatus = "valid" | "corrected" | "rejected" | "needs_review";

export interface ComponentHealth {
  status: HealthStatus;
  details?: string;
  latency_ms?: number;
}

export interface RootHealthResponse {
  status: string;
  service: string;
  version: string;
  docs_url: string;
  timestamp: string;
}

export interface LiveHealthResponse {
  status: string;
  timestamp: string;
  uptime_seconds: number;
}

export interface ReadyHealthResponse {
  status: HealthStatus;
  app: string;
  version: string;
  environment: string;
  timestamp: string;
  components: Record<string, ComponentHealth>;
}

export interface APIErrorDetail {
  code: string;
  message: string;
  details?: unknown;
}

export interface APIErrorResponse {
  error: APIErrorDetail;
  request_id?: string;
  timestamp: string;
}

export interface DocumentChunkResponse {
  id: string;
  document_id: string;
  page_number: number;
  section_heading?: string | null;
  chunk_index: number;
  text: string;
  start_char_offset: number;
  end_char_offset: number;
  source_identifier: string;
}

export interface DocumentMetadataResponse {
  id: string;
  original_filename: string;
  file_size_bytes: number;
  mime_type: string;
  file_hash_sha256: string;
  status: DocumentStatus;
  error_message?: string | null;
  total_pages: number;
  total_characters: number;
  created_at: string;
  updated_at: string;
}

export interface DocumentUploadResponse {
  document: DocumentMetadataResponse;
  chunks_extracted: number;
  message: string;
}

export interface DocumentTextResponse {
  document_id: string;
  total_chunks: number;
  page: number;
  page_size: number;
  has_more: boolean;
  chunks: DocumentChunkResponse[];
}

export interface DocumentListResponse {
  documents: DocumentMetadataResponse[];
  total: number;
}

export type ClauseCategory =
  | "liability"
  | "indemnity"
  | "termination"
  | "renewal"
  | "payment"
  | "confidentiality"
  | "intellectual_property"
  | "data_protection"
  | "warranties"
  | "governing_law"
  | "dispute_resolution"
  | "miscellaneous";

export interface ClauseResponse {
  clause_id: string;
  document_id: string;
  extraction_run_id: string;
  category: ClauseCategory;
  source_text: string;
  normalized_summary: string;
  page_number?: number | null;
  section_heading?: string | null;
  start_char_offset?: number | null;
  end_char_offset?: number | null;
  confidence?: number | null;
  validation_status: ClauseValidationStatus;
  validation_notes?: string | null;
  source_chunk_ids: string[];
  created_at: string;
}

export interface ClauseListResponse {
  document_id: string;
  total: number;
  clauses: ClauseResponse[];
}

export type PolicyStatus = "draft" | "active" | "archived";

export interface PolicyResponse {
  id: string;
  name: string;
  version: string;
  category?: string | null;
  description?: string | null;
  status: PolicyStatus;
  source_document_id?: string | null;
  total_chunks: number;
  created_at: string;
  updated_at: string;
}

export interface PolicyListResponse {
  policies: PolicyResponse[];
  total: number;
}

export interface PolicySearchResultItem {
  chunk_id: string;
  source_identifier: string;
  policy_id: string;
  policy_name: string;
  policy_version: string;
  category?: string | null;
  section_heading?: string | null;
  page_number: number;
  start_char_offset: number;
  end_char_offset: number;
  text: string;
  similarity_score: number;
  factual_confidence_note: string;
}

export interface PolicySearchResponse {
  query: string;
  total_results: number;
  model_used: string;
  dimension: number;
  results: PolicySearchResultItem[];
}

export type RiskPriority = "informational" | "low" | "medium" | "high" | "critical";
export type SeverityBasis =
  | "policy_rule"
  | "configured_requirement"
  | "model_analysis"
  | "retrieval_gap";
export type FindingType =
  | "policy_deviation"
  | "possible_legal_concern"
  | "missing_clause"
  | "missing_evidence";
export type ReviewStatus = "needs_review" | "reviewed" | "dismissed";
export type ValidationStatus =
  | "pending"
  | "verified"
  | "unverified"
  | "needs_review"
  | "missing_evidence"
  | "inconclusive";
export type ValidationErrorCategory =
  | "missing_contract_quote"
  | "contract_quote_not_found"
  | "contract_source_missing"
  | "missing_policy_quote"
  | "policy_quote_not_found"
  | "policy_source_mismatch"
  | "policy_source_not_in_retrieval"
  | "document_id_mismatch"
  | "clause_id_mismatch"
  | "retrieval_run_mismatch"
  | "retrieval_evidence_missing"
  | "policy_id_mismatch"
  | "policy_version_mismatch"
  | "page_number_mismatch"
  | "unsupported_explanation"
  | "severity_mismatch"
  | "malformed_citation"
  | "finding_contradicted_by_document"
  | "evidence_present"
  | "missing_evidence"
  | "inconclusive"
  | "duplicate_finding"
  | "retry_timeout"
  | "retry_failed"
  | "unexpected_finding_type";

export interface RiskFindingResponse {
  finding_id: string;
  document_id: string;
  clause_id?: string | null;
  clause_category?: string | null;
  retrieval_run_id: string;
  analysis_run_id: string;
  finding_type: FindingType;
  risk_category: string;
  severity: RiskPriority;
  severity_basis: SeverityBasis;
  rule_id?: string | null;
  contract_quote?: string | null;
  contract_source_reference?: string | null;
  contract_page_number?: number | null;
  policy_quote?: string | null;
  policy_source_reference?: string | null;
  policy_page_number?: number | null;
  policy_id?: string | null;
  policy_version?: string | null;
  explanation: string;
  confidence?: number | null;
  review_status: ReviewStatus;
  validation_status: ValidationStatus;
  validation_attempts: number;
  validation_error_categories: ValidationErrorCategory[];
  last_validated_at?: string | null;
  suggested_question: string;
  analysis_model: string;
  policy_versions: string[];
  created_at: string;
}

export interface RiskFindingListResponse {
  document_id: string;
  total: number;
  findings: RiskFindingResponse[];
}

export type WorkflowStatus =
  | "pending"
  | "running"
  | "awaiting_review"
  | "revising"
  | "completed"
  | "failed"
  | "cancelled";

export type ReviewDecisionType = "approve" | "dismiss" | "request_revision";
export type RetryTarget = "none" | "analysis" | "retrieval";

export interface WorkflowEventResponse {
  event_id: string;
  event_type: string;
  node?: string | null;
  actor_id?: string | null;
  status_from?: string | null;
  status_to?: string | null;
  message?: string | null;
  payload?: Record<string, unknown> | null;
  created_at: string;
}

export interface ReviewDecisionResponse {
  decision_id: string;
  reviewer_id: string;
  decision: ReviewDecisionType;
  finding_ids: string[];
  notes?: string | null;
  revision_instructions?: string | null;
  revision_target?: RetryTarget | null;
  idempotency_key?: string | null;
  created_at: string;
}

export interface ReviewReportFinding {
  finding_id: string;
  finding_type: FindingType;
  risk_category: string;
  severity: RiskPriority;
  rule_id?: string | null;
  validation_status: ValidationStatus;
  review_status: ReviewStatus;
  validation_attempts?: number;
  validation_error_categories?: ValidationErrorCategory[];
  last_validated_at?: string | null;
  explanation: string;
  suggested_question: string;
}

export interface ReviewReportSummary {
  clauses_extracted: number;
  policy_evidence_retrieved: number;
  findings: number;
  verified: number;
  unverified: number;
  missing_evidence: number;
  inconclusive: number;
  automatic_retries: number;
  human_revisions: number;
}

export interface ValidationSummary {
  status?: string;
  findings_validated?: number;
  verified_count?: number;
  unverified_count?: number;
  needs_review_count?: number;
  missing_evidence_count?: number;
  inconclusive_count?: number;
  max_retries?: number;
  warnings?: string[];
}

export interface WorkflowReviewReport {
  workflow_id: string;
  document_id: string;
  generated_at: string;
  status: string;
  summary: ReviewReportSummary;
  validation?: ValidationSummary;
  findings: ReviewReportFinding[];
  warnings: string[];
  human_review?: Record<string, unknown> | null;
  legal_action_performed: boolean;
  notice: string;
}

export interface WorkflowReviewRequest {
  workflow_id: string;
  document_id: string;
  interrupt: string;
  allowed_decisions: ReviewDecisionType[];
  instructions: string;
  findings: ReviewReportFinding[];
  validation?: ValidationSummary;
  warnings?: string[];
}

export interface WorkflowRunResponse {
  workflow_id: string;
  thread_id: string;
  document_id: string;
  owner_reviewer_id: string;
  status: WorkflowStatus;
  current_node?: string | null;
  interrupted_node?: string | null;
  step_count: number;
  retry_count: number;
  revision_count: number;
  max_retries: number;
  max_steps: number;
  clause_extraction_run_id?: string | null;
  policy_retrieval_run_id?: string | null;
  risk_analysis_run_id?: string | null;
  validation_run_id?: string | null;
  review_request?: WorkflowReviewRequest | null;
  review_report?: WorkflowReviewReport | null;
  state_snapshot?: Record<string, unknown> | null;
  error_code?: string | null;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  review_requested_at?: string | null;
  completed_at?: string | null;
  events: WorkflowEventResponse[];
  decisions: ReviewDecisionResponse[];
}

export interface WorkflowRunListResponse {
  runs: WorkflowRunResponse[];
  total: number;
}

export interface WorkflowResultsResponse {
  workflow: WorkflowRunResponse;
  report?: WorkflowReviewReport | null;
  findings: RiskFindingResponse[];
  validation_summary?: ValidationSummary | null;
  automatic_verification_complete: boolean;
  human_review_complete: boolean;
  legal_action_performed: boolean;
}

export interface WorkflowStartRequest {
  document_id: string;
  enable_model_analysis?: boolean;
  max_retries?: number;
  max_steps?: number;
}

export interface WorkflowResumeRequest {
  decision: ReviewDecisionType;
  finding_ids?: string[];
  notes?: string;
  revision_instructions?: string;
  revision_target?: RetryTarget;
  command_id?: string;
}

export interface PolicyCreateRequest {
  name: string;
  version?: string;
  category?: string | null;
  description?: string | null;
  text_content?: string | null;
}

export interface PolicyUploadMetadata {
  name: string;
  version?: string;
  category?: string;
  description?: string;
}

export type AuthStatus = "configured" | "missing";

export type ComparisonStatus = "running" | "completed" | "partial" | "failed";
export type ClauseChangeType =
  | "added"
  | "removed"
  | "modified"
  | "unchanged"
  | "reclassified";
export type FindingChangeType = "new" | "resolved" | "persisted" | "severity_changed";

export interface ClauseChangeResponse {
  change_id: string;
  change_type: ClauseChangeType;
  category: string;
  base_clause_id?: string | null;
  target_clause_id?: string | null;
  base_category?: string | null;
  target_category?: string | null;
  base_source_text?: string | null;
  target_source_text?: string | null;
  base_source_reference?: string | null;
  target_source_reference?: string | null;
  similarity: number;
  change_summary: string;
  created_at: string;
}

export interface FindingChangeResponse {
  change_id: string;
  change_type: FindingChangeType;
  finding_type: FindingType;
  risk_category: string;
  rule_id?: string | null;
  base_finding_id?: string | null;
  target_finding_id?: string | null;
  base_severity?: string | null;
  target_severity?: string | null;
  base_validation_status?: string | null;
  target_validation_status?: string | null;
  contract_source_reference?: string | null;
  explanation: string;
  created_at: string;
}

export interface ContractComparisonResponse {
  comparison_id: string;
  base_document_id: string;
  target_document_id: string;
  created_by: string;
  status: ComparisonStatus;
  base_analysis_run_id?: string | null;
  target_analysis_run_id?: string | null;
  clauses_added: number;
  clauses_removed: number;
  clauses_modified: number;
  clauses_unchanged: number;
  clauses_reclassified: number;
  findings_new: number;
  findings_resolved: number;
  findings_persisted: number;
  findings_severity_changed: number;
  affected_clause_ids: string[];
  reanalysis_requested: boolean;
  reanalysis_performed: boolean;
  warnings: string[];
  error_message?: string | null;
  created_at: string;
  completed_at?: string | null;
  clause_changes: ClauseChangeResponse[];
  finding_changes: FindingChangeResponse[];
  notice: string;
}

export interface ContractComparisonListResponse {
  comparisons: ContractComparisonResponse[];
  total: number;
}

export interface ContractComparisonRequest {
  base_document_id: string;
  target_document_id: string;
  reanalyze_target?: boolean;
}

export interface EvaluationAgentSummary {
  model?: string | null;
  mode?: string | null;
  findings: Record<string, unknown>;
  clause_extraction: Record<string, unknown>;
}

export interface EvaluationBenchmarkSummary {
  name?: string | null;
  description?: string | null;
  contracts: number;
  policies: number;
  ground_truth_findings: number;
}

export interface EvaluationSummaryResponse {
  available: boolean;
  reason?: string | null;
  schema_version?: string | null;
  dataset_version?: string | null;
  dataset_sha256?: string | null;
  prompt_version?: string | null;
  model_config_version?: string | null;
  generated_at?: string | null;
  git_commit?: string | null;
  mode?: string | null;
  benchmark: EvaluationBenchmarkSummary;
  agents: Record<string, EvaluationAgentSummary>;
  delta: Record<string, unknown>;
  limitations: string[];
  notice?: string | null;
}
