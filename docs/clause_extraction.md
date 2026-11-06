# Clause Extraction Agent

The Clause Extraction Agent converts an ingested contract into validated, structured
clauses with exact source citations. It performs **extraction only**; legal risk scoring
is intentionally a separate downstream stage.

## Architecture

```
Document chunks (page/section/offset aware)
        |
        v
DocumentTextMap (reconstructed, offset-addressable contract text)
        |
        v
ContractChunker (bounded windows + overlap)
        |
        v
LLMProvider.generate_structured (Gemini or explicit mock)
        |
        v
ClauseCandidate validation -> exact citation lookup -> deduplication
        |
        v
clause_extraction_runs + clauses tables
```

Key modules:

- `app/core/llm/` — provider abstraction, Gemini implementation, mock provider, factory.
- `app/schemas/clause.py` — typed clause schema, categories, and API response models.
- `app/services/clause/chunker.py` — long-contract splitting with overlap and source mapping.
- `app/services/clause/service.py` — prompt construction, validation, deduplication, persistence.
- `app/api/v1/endpoints/clauses.py` — extraction and inspection endpoints.

## Supported Categories

`liability`, `indemnity`, `termination`, `renewal`, `payment`, `confidentiality`,
`intellectual_property`, `data_protection`, `warranties`, `governing_law`,
`dispute_resolution`, `miscellaneous`.

Unknown model values are mapped to `miscellaneous` and flagged `needs_review`.

## Provider Configuration

All provider settings come from environment variables. Credentials are never hardcoded.

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | `gemini` or `mock` |
| `GEMINI_API_KEY` | unset | Required when `LLM_PROVIDER=gemini` |
| `LLM_MODEL` | `GEMINI_DEFAULT_MODEL` | Model name override |
| `LLM_TIMEOUT_SECONDS` | `45` | Per-request timeout |
| `LLM_MAX_RETRIES` | `2` | Retries after the initial failed attempt |
| `LLM_MAX_OUTPUT_TOKENS` | `8192` | Maximum structured output tokens |
| `CLAUSE_CHUNK_SIZE` | `6000` | Target characters per extraction window |
| `CLAUSE_CHUNK_OVERLAP` | `600` | Character overlap between windows |
| `CLAUSE_MIN_CONFIDENCE` | `0.5` | Below this value a clause is flagged for review |

### Production (Gemini)

```bash
export LLM_PROVIDER=gemini
export GEMINI_API_KEY="<your-key>"
export LLM_MODEL="gemini-1.5-pro"
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

If `GEMINI_API_KEY` is missing, the provider factory raises a clear
`CONFIGURATION_ERROR` (HTTP 503) instead of silently using a fake model.

### Offline / CI (mock)

```bash
export LLM_PROVIDER=mock
```

The mock provider is only selected when explicitly enabled. Ordinary CI tests inject
scripted mock responses; no network access or credentials are required.

## API

### Extract clauses

```http
POST /api/v1/documents/{document_id}/extract-clauses
```

Returns `201 Created` with the extraction run and validated clauses. Re-extracting a
document replaces its previous run and clauses so stale duplicates cannot accumulate.

### Inspect clauses

```http
GET /api/v1/documents/{document_id}/clauses
GET /api/v1/documents/{document_id}/clauses?category=confidentiality&limit=50
GET /api/v1/documents/{document_id}/clauses/{clause_id}
GET /api/v1/documents/{document_id}/extraction-runs
```

## Validation and Safety

- **Exact wording is preserved** in `source_text`; the model summary lives separately in
  `normalized_summary`.
- Every citation is located in the reconstructed document text. Quotes that cannot be
  found verbatim (or after whitespace normalization) are rejected.
- Character offsets, page numbers, and section headings are computed from the source
  document rather than trusted blindly from the model.
- Duplicate candidates are merged deterministically by category + normalized source text,
  keeping the earliest citation and highest confidence.
- Contract text is sent as untrusted data inside escaped `<contract_chunk>` delimiters.
  The system instruction forbids following in-text instructions, calling tools, or
  revealing prompts. Ingested text is already tagged `is_trusted_system_instruction=False`.
- Malformed or incomplete model output is handled safely: invalid JSON or schema-invalid
  candidates are counted, warned about, and skipped; the run is marked `partial` instead
  of crashing.
- Provider timeouts mark the run `failed` and return `LLM_TIMEOUT` (HTTP 504).
- No legal risk scores, severity ratings, or recommendations are assigned at this stage.

## Example Structured Output

Synthetic input contract:

```text
ARTICLE 1. CONFIDENTIALITY
Each party shall hold the other party's Confidential Information in strict confidence
for a period of five (5) years and shall not disclose it to any third party.

ARTICLE 2. LIMITATION OF LIABILITY
In no event shall either party's aggregate liability exceed the total fees paid under
this Agreement during the twelve (12) months preceding the claim.
```

Extraction response (identifiers and timestamps abbreviated):

```json
{
  "document_id": "fd2be890-407d-4d68-93f2-c3ad721ef4f9",
  "run": {
    "run_id": "a4a2c3f8-a442-4233-a7e2-f25640d76631",
    "status": "completed",
    "provider": "mock",
    "model_name": "mock-clause-extractor",
    "total_chunks": 1,
    "candidates_received": 2,
    "clauses_persisted": 2,
    "duplicates_merged": 0,
    "candidates_rejected": 0,
    "warnings": []
  },
  "clauses": [
    {
      "clause_id": "15c9a4aa-1f0d-5f54-9f7a-cd84d3a83992",
      "document_id": "fd2be890-407d-4d68-93f2-c3ad721ef4f9",
      "extraction_run_id": "a4a2c3f8-a442-4233-a7e2-f25640d76631",
      "category": "confidentiality",
      "source_text": "Each party shall hold the other party's Confidential Information in strict confidence for a period of five (5) years and shall not disclose it to any third party.",
      "normalized_summary": "Mutual confidentiality obligation lasting five years.",
      "page_number": 1,
      "section_heading": "ARTICLE 1. CONFIDENTIALITY",
      "start_char_offset": 0,
      "end_char_offset": 162,
      "confidence": 0.94,
      "validation_status": "valid",
      "validation_notes": null,
      "source_chunk_ids": ["a1ea4bb8-48f1-42aa-990b-3ff151383b32"]
    },
    {
      "clause_id": "06a8a3c0-1da5-5ba5-966c-57fc3355dc21",
      "document_id": "fd2be890-407d-4d68-93f2-c3ad721ef4f9",
      "extraction_run_id": "a4a2c3f8-a442-4233-a7e2-f25640d76631",
      "category": "liability",
      "source_text": "In no event shall either party's aggregate liability exceed the total fees paid under this Agreement during the twelve (12) months preceding the claim.",
      "normalized_summary": "Liability is capped at fees paid in the preceding twelve months.",
      "page_number": 1,
      "section_heading": "ARTICLE 2. LIMITATION OF LIABILITY",
      "start_char_offset": 164,
      "end_char_offset": 315,
      "confidence": 0.91,
      "validation_status": "valid",
      "validation_notes": null,
      "source_chunk_ids": ["16a003cc-da71-49d3-a9ca-51b6db4ab290"]
    }
  ]
}
```

## Tests

`backend/tests/test_clause_extraction.py` covers:

- valid extraction with exact source citation and offset verification
- malformed JSON / schema output
- missing or hallucinated citations
- duplicate candidate merging
- long documents split across overlapping chunks
- provider timeouts
- missing Gemini credentials
- full category coverage

Run:

```bash
cd backend
pytest tests/test_clause_extraction.py -v
```
