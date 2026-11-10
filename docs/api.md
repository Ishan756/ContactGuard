# ContractGuard — API Specification

The ContractGuard backend exposes RESTful endpoints with automatic OpenAPI documentation available at `/docs` (Swagger UI) and `/redoc` (ReDoc).

## Authentication & Authorization

All contract, clause, policy, risk, comparison, and workflow endpoints require two headers:

| Header | Purpose |
|---|---|
| `X-Reviewer-ID` | Stable reviewer identity (1-120 printable characters) |
| `X-Workflow-Key` | Matches either `WORKFLOW_REVIEW_API_KEY` or `ADMIN_API_KEY` |

- **Reviewer role**: owner-scoped access to documents, clauses, findings, comparisons,
  and workflows created with the same `X-Reviewer-ID`. Reviewer keys cannot manage policies.
- **Admin role**: full read access across reviewer records and permission to create,
  update, upload, and delete policies.
- Missing/invalid credentials return `401`; valid reviewer credentials without ownership
  or admin privileges return `403`.
- Public endpoints: `GET /health`, `GET /api/v1/health/live`,
  `GET /api/v1/health/ready`, and `GET /api/v1/evaluation/summary`.
- Legacy documents with no recorded owner are accessible to administrators only.

Example:
```bash
curl -H "X-Reviewer-ID: reviewer-a" \
     -H "X-Workflow-Key: $WORKFLOW_REVIEW_API_KEY" \
     http://localhost:8000/api/v1/documents
```

## Common Standards

### Request ID Tracing
Every request receives or generates a unique UUID4 request ID:
- **Client Header**: `X-Request-ID` (optional, client-provided)
- **Response Header**: `X-Request-ID` (always returned)
- **Latency Header**: `X-Response-Time-Ms`
- **Rate Limit Headers**: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `Retry-After`
  on `429` responses. Limits are keyed by client IP; set `TRUST_PROXY_HEADERS=true` only
  when a trusted reverse proxy overwrites `X-Real-IP`.
- **Security Headers**: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
  `Permissions-Policy`, `Cross-Origin-Opener-Policy`, and `Cross-Origin-Resource-Policy`.
  HSTS is emitted only when `APP_ENV=production`.
- Requests exceeding `REQUEST_TIMEOUT_SECONDS` (default 300) return `504`.

### Standard Error Schema
All application and validation errors adhere to the following schema:
```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Resource requested does not exist",
    "details": null
  },
  "request_id": "8d39c0f7-d0c7-43cf-a0e2-8b4382502f6a",
  "timestamp": "2026-10-15T22:45:00.000000Z"
}
```

---

## Health & Probe Endpoints

### 1. Service Root Health
- **Endpoint**: `GET /health`
- **Description**: Lightweight health probe returning service metadata and documentation URLs.
- **Response**: `200 OK`
```json
{
  "status": "ok",
  "service": "ContractGuard",
  "version": "0.1.0",
  "docs_url": "/docs",
  "timestamp": "2026-10-15T22:45:00.000000Z"
}
```

### 2. Liveness Probe
- **Endpoint**: `GET /api/v1/health/live`
- **Description**: Container/orchestrator liveness check confirming the FastAPI process event loop is active.
- **Response**: `200 OK`
```json
{
  "status": "ok",
  "timestamp": "2026-10-15T22:45:00.000000Z",
  "uptime_seconds": 128.4
}
```

### 3. Readiness Probe
- **Endpoint**: `GET /api/v1/health/ready`
- **Description**: Comprehensive readiness probe checking connectivity to PostgreSQL and Qdrant.
- **Response**: `200 OK` in development, or `503 Service Unavailable` in production when
  a downstream dependency is degraded.
```json
{
  "status": "healthy",
  "app": "ContractGuard",
  "version": "0.1.0",
  "environment": "development",
  "timestamp": "2026-10-15T22:45:00.000000Z",
  "components": {
    "api": {
      "status": "healthy",
      "details": "FastAPI core processing loop active",
      "latency_ms": 0.1
    },
    "vector_db_qdrant": {
      "status": "healthy",
      "details": "Qdrant cluster responsive",
      "latency_ms": 1.2
    },
    "relational_db_postgres": {
      "status": "healthy",
      "details": "PostgreSQL port reachable",
      "latency_ms": 0.8
    }
  }
}
```

---

## Document Ingestion Endpoints

### 1. Upload & Ingest Contract
- **Endpoint**: `POST /api/v1/documents`
- **Auth**: Reviewer or admin
- **Content-Type**: `multipart/form-data`
- **Parameters**: `file` (binary PDF or DOCX file)
- **Validation**:
  - Max upload size: 25MB (configurable via `MAX_UPLOAD_SIZE_MB`)
  - Allowed extensions: `.pdf`, `.docx`
  - Magic bytes verification (`%PDF-` for PDF, `PK\x03\x04` for DOCX)
  - Filename sanitization and 255-character bound
  - Upload content read is bounded by `MAX_UPLOAD_SIZE_MB`
- **Ownership**: The authenticated reviewer becomes the document owner.
- **Response**: `201 Created`
```json
{
  "document": {
    "id": "e0b82142-992d-45db-9964-6dfbf1e2f75a",
    "original_filename": "master_services_agreement.pdf",
    "file_size_bytes": 1048576,
    "mime_type": "application/pdf",
    "file_hash_sha256": "4a7d1ed414474e4033ac29ccb8653d9b",
    "status": "completed",
    "error_message": null,
    "total_pages": 12,
    "total_characters": 34500,
    "created_at": "2026-10-15T23:00:00Z",
    "updated_at": "2026-10-15T23:00:01Z"
  },
  "chunks_extracted": 48,
  "message": "Document successfully ingested and parsed."
}
```

### 2. List Documents
- **Endpoint**: `GET /api/v1/documents`
- **Auth**: Reviewer or admin; reviewers see only their own documents.
- **Query Parameters**:
  - `limit`: int (default: 20, max: 100)
  - `offset`: int (default: 0)
- **Response**: `200 OK`
```json
{
  "documents": [ ... ],
  "total": 1
}
```

### 3. Get Document Metadata
- **Endpoint**: `GET /api/v1/documents/{document_id}`
- **Auth**: Owner or admin.
- **Response**: `200 OK` (returns `DocumentMetadataResponse`)

### 4. Get Paginated Chunks with Offsets
- **Endpoint**: `GET /api/v1/documents/{document_id}/chunks`
- **Auth**: Owner or admin.
- **Query Parameters**:
  - `page`: int (default: 1)
  - `page_size`: int (default: 20, max: 100)
- **Response**: `200 OK`
```json
{
  "document_id": "e0b82142-992d-45db-9964-6dfbf1e2f75a",
  "total_chunks": 48,
  "page": 1,
  "page_size": 20,
  "has_more": true,
  "chunks": [
    {
      "id": "9df031c2-3e28-444a-939a-5fb1bc0a98fe",
      "document_id": "e0b82142-992d-45db-9964-6dfbf1e2f75a",
      "page_number": 1,
      "section_heading": "ARTICLE 1. CONFIDENTIALITY",
      "chunk_index": 0,
      "text": "Each party agrees to hold the Confidential Information of the other in strict confidence...",
      "start_char_offset": 0,
      "end_char_offset": 312,
      "source_identifier": "doc:e0b82142:p1:c0"
    }
  ]
}
```

### 5. Delete Document
- **Endpoint**: `DELETE /api/v1/documents/{document_id}`
- **Auth**: Owner or admin.
- **Description**: Deletes the document, dependent chunks/runs/findings/workflows, and the
  stored source file. Returns `204 No Content`.

---

## Clause Extraction Endpoints

All clause endpoints require reviewer authentication and enforce document ownership.


Extraction and legal risk assessment are separate stages. These endpoints only extract
and validate clauses; they do not assign risk scores.

### 1. Extract Clauses
- **Endpoint**: `POST /api/v1/documents/{document_id}/extract-clauses`
- **Description**: Runs the Clause Extraction Agent over bounded, overlapping document
  chunks. Each candidate is validated against an exact verbatim source citation,
  deduplicated deterministically, and persisted with the document and extraction run.
- **Response**: `201 Created`
```json
{
  "document_id": "e0b82142-992d-45db-9964-6dfbf1e2f75a",
  "run": {
    "run_id": "a4a2c3f8-a442-4233-a7e2-f25640d76631",
    "document_id": "e0b82142-992d-45db-9964-6dfbf1e2f75a",
    "status": "completed",
    "provider": "gemini",
    "model_name": "gemini-1.5-pro",
    "total_chunks": 3,
    "candidates_received": 14,
    "clauses_persisted": 12,
    "duplicates_merged": 2,
    "candidates_rejected": 0,
    "warnings": [],
    "error_message": null,
    "created_at": "2026-11-06T14:38:07Z",
    "completed_at": "2026-11-06T14:38:12Z"
  },
  "clauses": [
    {
      "clause_id": "15c9a4aa-1f0d-5f54-9f7a-cd84d3a83992",
      "document_id": "e0b82142-992d-45db-9964-6dfbf1e2f75a",
      "extraction_run_id": "a4a2c3f8-a442-4233-a7e2-f25640d76631",
      "category": "confidentiality",
      "source_text": "Each party shall hold the other party's Confidential Information in strict confidence...",
      "normalized_summary": "Mutual confidentiality obligation lasting five years.",
      "page_number": 1,
      "section_heading": "ARTICLE 1. CONFIDENTIALITY",
      "start_char_offset": 0,
      "end_char_offset": 162,
      "confidence": 0.94,
      "validation_status": "valid",
      "validation_notes": null,
      "source_chunk_ids": ["a1ea4bb8-48f1-42aa-990b-3ff151383b32"],
      "created_at": "2026-11-06T14:38:12Z"
    }
  ]
}
```
- **Provider configuration**: See [Clause Extraction Agent](clause_extraction.md). Missing
  Gemini credentials return `CONFIGURATION_ERROR` (HTTP 503); timeouts return
  `LLM_TIMEOUT` (HTTP 504).

### 2. List Extracted Clauses
- **Endpoint**: `GET /api/v1/documents/{document_id}/clauses`
- **Query Parameters**:
  - `category`: optional canonical category filter
  - `extraction_run_id`: optional run filter
  - `limit`: int (default: 100, max: 500)
  - `offset`: int (default: 0)
- **Response**: `200 OK` (`ClauseListResponse`)

### 3. Get a Single Clause
- **Endpoint**: `GET /api/v1/documents/{document_id}/clauses/{clause_id}`
- **Response**: `200 OK` (`ClauseResponse`)

### 4. List Extraction Runs
- **Endpoint**: `GET /api/v1/documents/{document_id}/extraction-runs`
- **Response**: `200 OK` (`ExtractionRunListResponse`)

---

## Policy Library Endpoints

- `GET /api/v1/policies` and `POST /api/v1/policies/search` require any valid reviewer key.
- `POST /api/v1/policies`, `POST /api/v1/policies/upload`, `PUT /api/v1/policies/{id}`,
  and `DELETE /api/v1/policies/{id}` require the administrative key.

## Policy Retrieval & Risk Analysis Endpoints

All retrieval, analysis, finding, and validation endpoints require reviewer authentication
and enforce ownership of the target document. Retrieval and risk analysis are separate from clause extraction. Retrieval returns active
policy evidence and explicit coverage gaps. Risk analysis persists review findings with
verbatim contract and policy citations. An independent Evidence Validation Agent then
re-checks citations, provenance, page numbers, explanations, and severity, with bounded
correction retries. Unresolved findings remain unverified. See
[Risk Analysis Agents](risk_analysis.md) for rule definitions, validation lifecycle,
severity configuration, and example findings.

### 1. Retrieve Policy Evidence
- **Endpoint**: `POST /api/v1/documents/{document_id}/retrieve-policies`
- **Body** (optional):
```json
{
  "policy_versions": ["1.0.0"],
  "policy_statuses": ["active"]
}
```
- **Behavior**: Draft/archived policies are excluded by default. Clauses with no matching
  evidence are marked `coverage_status: "missing"`.
- **Response**: `201 Created` (`PolicyRetrievalResponse`)

### 2. List Retrieval Runs
- **Endpoint**: `GET /api/v1/documents/{document_id}/retrieval-runs`
- **Response**: `200 OK` (`PolicyRetrievalRunListResponse`)

### 3. Analyze Risk
- **Endpoint**: `POST /api/v1/documents/{document_id}/analyze-risk`
- **Body** (optional):
```json
{
  "retrieval_run_id": "optional-run-id",
  "enable_model_analysis": true,
  "enable_validation": true,
  "validation_max_retries": 2
}
```
- **Behavior**: Deterministic rules run first. Model analysis is only used when no rule
  fires, policy evidence exists, and model analysis is enabled. Severity comes from policy
  rules/configuration, not model confidence. Evidence validation runs automatically and
  stores per-finding `validation_status`, error categories, attempt counts, and timestamps.
- **Response**: `201 Created`
```json
{
  "document_id": "e0b82142-992d-45db-9964-6dfbf1e2f75a",
  "run": {
    "run_id": "b63f...",
    "document_id": "e0b82142-992d-45db-9964-6dfbf1e2f75a",
    "retrieval_run_id": "4618...",
    "status": "completed",
    "provider": "gemini",
    "model_name": "gemini-1.5-pro",
    "clauses_analyzed": 12,
    "findings_count": 4,
    "model_analysis_enabled": true,
    "policy_versions": ["1.0.0"],
    "warnings": [],
    "error_message": null,
    "created_at": "2026-11-06T14:40:00Z",
    "completed_at": "2026-11-06T14:40:02Z"
  },
  "findings": [
    {
      "finding_id": "b5b3b99f-5d29-4f3e-93ec-9d8805f9ec1d",
      "document_id": "e0b82142-992d-45db-9964-6dfbf1e2f75a",
      "clause_id": "15c9a4aa-1f0d-5f54-9f7a-cd84d3a83992",
      "clause_category": "liability",
      "retrieval_run_id": "4618...",
      "analysis_run_id": "b63f...",
      "finding_type": "policy_deviation",
      "risk_category": "liability",
      "severity": "critical",
      "severity_basis": "policy_rule",
      "rule_id": "liability_unlimited",
      "contract_quote": "The vendor's aggregate liability under this Agreement shall be unlimited.",
      "contract_source_reference": "clause:15c9a4aa-1f0d-5f54-9f7a-cd84d3a83992",
      "contract_page_number": 1,
      "policy_quote": "Company requires all vendor contracts to cap aggregate liability at twelve (12) months of fees paid.",
      "policy_source_reference": "pol:ac72...:p1:c0",
      "policy_page_number": 1,
      "policy_id": "ac72...",
      "policy_version": "1.0.0",
      "explanation": "The contract contains unlimited liability while the active policy requires a cap of 12 months of fees.",
      "confidence": null,
      "review_status": "needs_review",
      "validation_status": "verified",
      "validation_attempts": 1,
      "validation_error_categories": [],
      "last_validated_at": "2026-11-06T14:40:03Z",
      "suggested_question": "Can liability be capped in line with the active policy before signature?",
      "analysis_model": "policy-rule-engine",
      "policy_versions": ["1.0.0"],
      "created_at": "2026-11-06T14:40:02Z"
    }
  ]
}
```

### 4. List Findings
- **Endpoint**: `GET /api/v1/documents/{document_id}/findings`
- **Query Parameters**:
  - `analysis_run_id`: optional run filter (defaults to latest run)
  - `severity`: optional review priority filter
  - `category`: optional risk category filter
  - `limit`: int (default: 100, max: 500)
  - `offset`: int (default: 0)
- **Response**: `200 OK` (`RiskFindingListResponse`)

### 5. Get a Single Finding
- **Endpoint**: `GET /api/v1/documents/{document_id}/findings/{finding_id}`
- **Response**: `200 OK` (`RiskFindingResponse`)

### 6. List Risk Analysis Runs
- **Endpoint**: `GET /api/v1/documents/{document_id}/analysis-runs`
- **Response**: `200 OK` (`RiskAnalysisRunListResponse`)

### 7. Validate Findings
- **Endpoint**: `POST /api/v1/documents/{document_id}/validate-findings`
- **Body** (optional):
```json
{
  "analysis_run_id": "optional-run-id",
  "finding_ids": ["optional-finding-id"],
  "max_retries": 2,
  "enable_retries": true
}
```
- **Behavior**: Independently verifies contract/policy quotes, referential IDs, page
  numbers, retrieval evidence, explanation support, and configured severity. Invalid
  findings are routed to analysis/retrieval correction with bounded retries. Exhausted
  findings remain `unverified` or `needs_review`.
- **Response**: `201 Created` (`EvidenceValidationResponse`)

### 8. List Validation Runs
- **Endpoint**: `GET /api/v1/documents/{document_id}/validation-runs`
- **Response**: `200 OK` (`EvidenceValidationRunListResponse`)

### 9. Get a Validation Run
- **Endpoint**: `GET /api/v1/documents/{document_id}/validation-runs/{validation_run_id}`
- **Response**: `200 OK` (`EvidenceValidationResponse` with every persisted attempt)

---

## LangGraph Workflow & Human Review Endpoints

All workflow endpoints require `X-Reviewer-ID` and `X-Workflow-Key`. Reviewers may only
inspect or resume workflows they started. Administrative keys may inspect all workflows. Start and resume support the
`Idempotency-Key` header. See [workflow.md](workflow.md) for the full state machine,
Mermaid diagram, checkpoint lifecycle, and decision semantics.

### 1. List Workflows
- **Endpoint**: `GET /api/v1/workflows`
- **Headers**: `X-Reviewer-ID`, `X-Workflow-Key`
- **Query parameters**: optional `document_id`, `limit` (default `50`), `offset` (default `0`)
- **Response**: `200 OK` (`WorkflowRunListResponse`) containing only workflows owned by
the authenticated reviewer (or all workflows for admins), newest first, with `runs` and
`total`.

### 2. Start Workflow
- **Endpoint**: `POST /api/v1/workflows`
- **Headers**: `X-Reviewer-ID`, `X-Workflow-Key`, optional `Idempotency-Key`
- **Body**:
```json
{
  "document_id": "document-uuid",
  "enable_model_analysis": false,
  "max_retries": 2,
  "max_steps": 30
}
```
- **Behavior**: Runs clause extraction, policy retrieval, risk analysis, and automatic
evidence validation. Conditional edges rerun analysis/retrieval up to the configured
retry limit. When findings exist, the graph persists an interrupt and returns
`awaiting_review`; no legal or contractual action is executed.
- **Response**: `201 Created` (`WorkflowRunResponse`)

### 3. Inspect Workflow Status
- **Endpoint**: `GET /api/v1/workflows/{workflow_id}`
- **Response**: `200 OK` (`WorkflowRunResponse`) including status, current/interrupted
node, step/retry/revision counts, review interrupt payload, events, and decisions.

### 4. Retrieve Workflow Results
- **Endpoint**: `GET /api/v1/workflows/{workflow_id}/results`
- **Response**: `200 OK` (`WorkflowResultsResponse`) with the review report, persisted
findings, validation summary, verification/review completion flags, and
`legal_action_performed: false`.

### 5. Resume Human Review
- **Endpoint**: `POST /api/v1/workflows/{workflow_id}/resume`
- **Headers**: `X-Reviewer-ID`, `X-Workflow-Key`, optional `Idempotency-Key`
- **Body**:
```json
{
  "decision": "approve",
  "finding_ids": ["optional-finding-id"],
  "notes": "Reviewed the liability deviation.",
  "revision_instructions": null,
  "revision_target": "analysis",
  "command_id": "optional-command-id"
}
```
- **Decisions**: `approve`, `dismiss`, or `request_revision`. Revision requests require
`revision_instructions` or `notes`, rerun analysis/retrieval, and then pause for review
again. Decisions are append-only; prior decisions are never rewritten.
- **Response**: `200 OK` (`WorkflowRunResponse`), typically `awaiting_review` after a
revision or `completed` after approval/dismissal.

---

## Limitations of Text Extraction

1. **Scanned & Image-Only Documents**:
   - ContractGuard detects documents where character count is minimal (< 50 chars) but visual content exists. Rather than falsely claiming success, the document is marked with status `"needs_ocr"` with diagnostic guidance.
2. **Encrypted PDFs**:
   - Password-protected documents cannot be decrypted without user-provided credentials. These fail gracefully with status `"failed"` and error `"Encrypted PDF document cannot be parsed without password"`.
3. **Complex Multi-Column Tables & Layouts**:
   - PyMuPDF and python-docx extract layout blocks sequentially. Highly nested or irregular table formats may flatten columns with pipe delimiters (`|`).
4. **Untrusted Input Guarantee**:
   - Ingested text is tagged with `is_trusted_system_instruction = False` and must be processed solely as passive data context, never as system-level execution prompts.

---

## Contract Version Comparison Endpoints

Comparison endpoints identify textual, classification, and finding-level changes between
two contract versions. They do not provide legal advice or determine enforceability.
Reviewers may compare and inspect only documents/comparisons they own; admins may access all.

### 1. Create Comparison
- **Endpoint**: `POST /api/v1/comparisons`
- **Headers**: `X-Reviewer-ID`, `X-Workflow-Key`
- **Body**:
```json
{
  "base_document_id": "earlier-document-uuid",
  "target_document_id": "newer-document-uuid",
  "reanalyze_target": false
}
```
- **Behavior**: Deterministically matches clauses by category and sequence similarity,
classifies `added`, `removed`, `modified`, `unchanged`, and `reclassified` changes,
compares the latest findings as `new`, `resolved`, `persisted`, or `severity_changed`,
and records affected clause IDs. When `reanalyze_target` is true, risk analysis reruns
only for changed target clauses and creates a new analysis run without rewriting history.
- **Response**: `201 Created` (`ContractComparisonResponse`)

### 2. List Comparisons
- **Endpoint**: `GET /api/v1/comparisons`
- **Query parameters**: optional `document_id`, `limit` (default `20`, max `100`),
  `offset` (default `0`)
- **Response**: `200 OK` (`ContractComparisonListResponse`)

### 3. Get Comparison
- **Endpoint**: `GET /api/v1/comparisons/{comparison_id}`
- **Response**: `200 OK` (`ContractComparisonResponse`) including every clause and finding
change, warnings, re-analysis status, and a non-legal-advice notice.

---

## Evaluation Benchmark Endpoint

### Get Latest Evaluation Summary
- **Endpoint**: `GET /api/v1/evaluation/summary`
- **Description**: Reads the versioned report generated by
`evaluation/runners/benchmark.py` (default `evaluation/reports/latest.json`, configurable
with `EVALUATION_REPORT_PATH`). Returns metadata, per-agent computed metrics, deltas,
limitations, and a notice. If the report is missing or malformed, returns `200 OK` with
`available: false` and a reason so the dashboard degrades gracefully.
- **Response**: `200 OK` (`EvaluationSummaryResponse`)

```json
{
  "available": true,
  "dataset_version": "v1",
  "generated_at": "2026-11-10T00:00:00+00:00",
  "mode": "mock",
  "benchmark": {
    "contracts": 3,
    "policies": 4,
    "ground_truth_findings": 9
  },
  "agents": {
    "baseline": {"findings": {"precision": 0.7143, "recall": 0.5556}},
    "multi_agent": {"findings": {"precision": 1.0, "recall": 1.0}}
  },
  "delta": {"findings": {"precision": 0.2857, "recall": 0.4444}},
  "limitations": ["The dataset is synthetic and small."],
  "notice": "Benchmark results compare synthetic annotations. They do not establish legal correctness."
}
```
