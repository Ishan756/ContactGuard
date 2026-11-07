# ContractGuard — API Specification

The ContractGuard backend exposes RESTful endpoints with automatic OpenAPI documentation available at `/docs` (Swagger UI) and `/redoc` (ReDoc).

## Common Standards

### Request ID Tracing
Every request receives or generates a unique UUID4 request ID:
- **Client Header**: `X-Request-ID` (optional, client-provided)
- **Response Header**: `X-Request-ID` (always returned)
- **Latency Header**: `X-Response-Time-Ms`

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
- **Response**: `200 OK`
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
- **Content-Type**: `multipart/form-data`
- **Parameters**: `file` (binary PDF or DOCX file)
- **Validation**:
  - Max upload size: 25MB (configurable via `MAX_UPLOAD_SIZE_MB`)
  - Allowed extensions: `.pdf`, `.docx`
  - Magic bytes verification (`%PDF-` for PDF, `PK\x03\x04` for DOCX)
  - Filename sanitization against path traversal
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
- **Response**: `200 OK` (returns `DocumentMetadataResponse`)

### 4. Get Paginated Chunks with Offsets
- **Endpoint**: `GET /api/v1/documents/{document_id}/chunks`
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

---

## Clause Extraction Endpoints

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

## Policy Retrieval & Risk Analysis Endpoints

Retrieval and risk analysis are separate from clause extraction. Retrieval returns active
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

## Limitations of Text Extraction

1. **Scanned & Image-Only Documents**:
   - ContractGuard detects documents where character count is minimal (< 50 chars) but visual content exists. Rather than falsely claiming success, the document is marked with status `"needs_ocr"` with diagnostic guidance.
2. **Encrypted PDFs**:
   - Password-protected documents cannot be decrypted without user-provided credentials. These fail gracefully with status `"failed"` and error `"Encrypted PDF document cannot be parsed without password"`.
3. **Complex Multi-Column Tables & Layouts**:
   - PyMuPDF and python-docx extract layout blocks sequentially. Highly nested or irregular table formats may flatten columns with pipe delimiters (`|`).
4. **Untrusted Input Guarantee**:
   - Ingested text is tagged with `is_trusted_system_instruction = False` and must be processed solely as passive data context, never as system-level execution prompts.
