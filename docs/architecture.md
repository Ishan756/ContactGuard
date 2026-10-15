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
- **PostgreSQL**: Stores contract entities, clause metadata, multi-agent evaluation traces, audit trails, and user permissions.
- **Qdrant**: High-performance vector database storing dense vector embeddings of contract clauses for fast similarity searches and precedent comparison.
- **Gemini API Abstraction**: Clean provider interface allowing model swapping, prompt template management, and retry handling.
