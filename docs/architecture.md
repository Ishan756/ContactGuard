# ContractGuard — System Architecture

## 1. High-Level Overview

**ContractGuard** is an AI-powered, multi-agent contract risk auditing platform designed to audit legal agreements (e.g. Master Services Agreements, NDAs, Vendor Contracts, Employment Agreements).

```
                      +-----------------------------+
                      | React (Vite + TypeScript)   |
                      | Dashboard & Audit Console   |
                      +--------------+--------------+
                                     |
                                     | REST / JSON (with X-Request-ID)
                                     v
                      +-----------------------------+
                      | FastAPI Backend Core        |
                      | - Request Tracing & Auth    |
                      | - Structured JSON Logging   |
                      | - Centralized Error Handler |
                      +--------------+--------------+
                                     |
            +------------------------+------------------------+
            |                        |                        |
            v                        v                        v
+-----------------------+ +--------------------+ +-----------------------+
| Relational Storage    | | Vector Database    | | AI Orchestration      |
| PostgreSQL            | | Qdrant             | | LangGraph Multi-Agent |
| (Contracts, Audits,   | | (Semantic Clause   | | Engine + Gemini API   |
| Findings, Audit Logs) | | Embeddings)        | | Abstraction Layer     |
+-----------------------+ +--------------------+ +-----------------------+
```

## 2. Core Subsystems

### 2.1 Backend (FastAPI + Pydantic v2)
- **Settings & Config (`app.core.config`)**: Strongly typed settings loaded from environment variables and `.env` with validation.
- **Observability (`app.core.logging`, `app.core.middleware`)**: Injects unique `X-Request-ID` across every incoming request, logs structured operational context, and records execution latency.
- **Error Standard (`app.core.errors`)**: Centralized error responses following `{ "error": { "code", "message", "details" }, "request_id", "timestamp" }`.
- **Probes (`app.api.v1.endpoints.health`)**: Liveness (`/api/v1/health/live`) and readiness (`/api/v1/health/ready`) with non-blocking checks for PostgreSQL and Qdrant.

### 2.2 Frontend (React 18 + TypeScript + Vite)
- **Shell**: Modular layout with responsive Sidebar, status-aware Topbar, and routed page views.
- **Client (`services/apiClient.ts`)**: Type-safe REST client ensuring automatic propagation of `X-Request-ID` and normalized error decoding into typed exceptions.
- **Aesthetic**: Premium dark-slate interface with glassmorphism, glowing telemetry indicators, and clear typography.

### 2.3 Data & Storage Subsystems
- **PostgreSQL**: Stores contract entities, document metadata, policies (`policies`, `policy_chunks`), multi-agent evaluation traces, and audit trails.
- **Qdrant**: High-performance vector database storing dense vector embeddings of policy chunks (`company_policies` collection) for sub-millisecond semantic retrieval against individual contract clauses.
- **Embedding Provider Interface**: Pluggable interface (`EmbeddingProvider`) with Gemini API (`GeminiEmbeddingProvider` using `text-embedding-004`) and zero-cost deterministic mock provider (`DeterministicEmbeddingProvider`) for isolated testing.

### 2.4 Policy Knowledge Base & Retrieval Subsystem
- **Policy Ingestion (`/api/v1/policies`)**: Administrators upload policies via raw text or PDF/DOCX documents (reusing secure document ingestion). Documents are split into semantic chunks preserving source page numbers, headings, and character offsets.
- **Vector Indexing & Collection Validation**: Automatically validates dimension compatibility against the active Qdrant collection (e.g. 768 dims for Gemini `text-embedding-004`). Ensures no mixed dimensions can corrupt index integrity.
- **Stale Vector Cleanup**: When a policy is updated or deleted, all associated vector points are pruned from Qdrant by policy ID filter to prevent stale or orphaned contamination.
- **Semantic Clause Retrieval (`/api/v1/policies/search`)**: Given an individual contract clause, retrieves matching policy passages ranked by cosine similarity with source citations, stable chunk IDs, and a factual confidence disclaimer distinguishing similarity from legal compliance certainty.
