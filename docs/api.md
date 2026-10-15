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

## Limitations of Text Extraction

1. **Scanned & Image-Only Documents**:
   - ContractGuard detects documents where character count is minimal (< 50 chars) but visual content exists. Rather than falsely claiming success, the document is marked with status `"needs_ocr"` with diagnostic guidance.
2. **Encrypted PDFs**:
   - Password-protected documents cannot be decrypted without user-provided credentials. These fail gracefully with status `"failed"` and error `"Encrypted PDF document cannot be parsed without password"`.
3. **Complex Multi-Column Tables & Layouts**:
   - PyMuPDF and python-docx extract layout blocks sequentially. Highly nested or irregular table formats may flatten columns with pipe delimiters (`|`).
4. **Untrusted Input Guarantee**:
   - Ingested text is tagged with `is_trusted_system_instruction = False` and must be processed solely as passive data context, never as system-level execution prompts.
