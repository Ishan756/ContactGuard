# ContractGuard

**ContractGuard** is a production-style, AI-powered multi-agent contract risk auditing platform designed to audit legal agreements (e.g. Master Services Agreements, NDAs, Vendor Contracts, Employment Agreements). It features concurrent legal, financial, and compliance risk analysis with semantic vector indexing.

---

## Monorepo Architecture

```
ContactGuard/
|-- backend/                     # Python 3.12+ FastAPI backend service
|   |-- app/
|   |   |-- api/                 # API routers & versioning (v1 endpoints)
|   |   |   |-- v1/
|   |   |   |   +-- endpoints/
|   |   |   |       +-- health.py# /health, /api/v1/health/live, /ready
|   |   |   |-- router.py
|   |   |-- core/                # Core config, logging, errors, middleware
|   |   |   |-- config.py        # Typed Settings (pydantic-settings)
|   |   |   |-- errors.py        # Centralized exceptions & standard error schema
|   |   |   |-- logging.py       # Contextual structured logging
|   |   |   +-- middleware.py    # RequestContextMiddleware & X-Request-ID
|   |   |-- schemas/             # Pydantic v2 data models & response envelopes
|   |   |   |-- common.py        # Generic APIResponse & standard message
|   |   |   +-- health.py        # Live, Ready, and Component health models
|   |   +-- main.py              # Application factory, CORS, exception handlers
|   |-- tests/                   # Pytest test suite
|   |   |-- conftest.py          # Async httpx client fixture
|   |   |-- test_health.py       # Liveness, readiness, and root probe tests
|   |   +-- test_middleware_and_errors.py # Error handling & Request ID tests
|   |-- Dockerfile               # Production container image definition
|   |-- pyproject.toml           # PEP 518/621 project configuration & Ruff rules
|   |-- requirements.txt         # Runtime pinned dependencies
|   +-- requirements-dev.txt     # Test and linting dependencies
|
|-- frontend/                    # React 18 + TypeScript + Vite dashboard
|   |-- src/
|   |   |-- components/
|   |   |   |-- layout/          # DashboardLayout, Sidebar, Header
|   |   |   +-- ui/              # Badge, Card, Button components
|   |   |-- pages/               # DashboardOverview, AuditQueue, SystemHealth, Settings
|   |   |-- services/
|   |   |   +-- apiClient.ts     # Typed API client with request ID propagation
|   |   |-- types/               # Shared TypeScript schemas
|   |   |-- tests/               # Vitest + Testing Library test suite
|   |   |-- App.tsx              # Router configuration
|   |   |-- main.tsx             # DOM mount
|   |   +-- index.css            # Modern dark-slate aesthetic & design tokens
|   |-- Dockerfile               # Multi-stage production Nginx container
|   |-- package.json             # NPM dependencies and scripts
|   |-- tsconfig.json            # Strict TypeScript configuration
|   +-- vite.config.ts           # Vite bundler, proxy & Vitest config
|
|-- infra/                       # Infrastructure orchestration & Docker
|   |-- docker/
|   |   |-- backend.Dockerfile
|   |   +-- frontend.Dockerfile
|   +-- docker-compose.yml       # Backing infra & container services
|
|-- docs/                        # Architecture, API & setup documentation
|   |-- architecture.md          # Topology, subsystem interactions
|   |-- api.md                   # Endpoint schemas and request tracing
|   |-- getting_started.md       # Local and Docker setup instructions
|   +-- multi_agent_blueprint.md # Planned LangGraph agent graph architecture
|
|-- evaluation/                  # Benchmark datasets and evaluation harnesses
|   |-- benchmarks/
|   |   +-- sample_contracts/    # Benchmark contracts repository
|   |-- runners/
|   |   +-- eval_harness.py      # Automated benchmark precision/recall harness
|   +-- README.md
|
|-- .github/
|   +-- workflows/
|       +-- ci.yml               # Automated CI workflow (lint, test, build)
|-- .env.example                 # Template environment variables (safe defaults)
|-- .env                         # Local development configuration (git-ignored)
|-- .gitignore                   # Comprehensive gitignore for Python, Node, OS
+-- docker-compose.yml           # Root compose for PostgreSQL, Qdrant & apps
```

---

## Technology Stack

- **Backend**: Python 3.12+, FastAPI, Pydantic v2, `pydantic-settings`, Uvicorn
- **Agent Orchestration Foundation**: LangGraph, LangChain Core
- **AI Provider**: Google Gemini API via typed abstraction layer
- **Vector Database**: Qdrant (HTTP `6333`, gRPC `6334`)
- **Relational Database**: PostgreSQL 16
- **Document Parsing Foundation**: PyMuPDF (`fitz`), `python-docx`
- **Frontend**: React 18, TypeScript, Vite, React Router v6, Lucide React
- **Testing**: pytest & pytest-asyncio (backend), Vitest & React Testing Library (frontend)
- **Tooling & Linting**: Ruff (Python), TypeScript compiler `tsc` (Frontend)
- **Infrastructure**: Docker multi-stage builds, Docker Compose, GitHub Actions CI

---

## Quick Start

### 1. Using Docker Compose
```bash
# 1. Copy environment template
cp .env.example .env

# 2. Start PostgreSQL, Qdrant, FastAPI backend, and React frontend
docker compose up -d

# 3. View live services
# Frontend: http://localhost:5173
# API Swagger: http://localhost:8000/docs
# Qdrant Dashboard: http://localhost:6333/dashboard
```

### 2. Running Locally for Development
```bash
# 1. Start backing services (PostgreSQL + Qdrant)
docker compose up -d postgres qdrant

# 2. Run Backend
cd backend
python -m venv .venv
.\.venv\Scripts\activate   # Windows (or source .venv/bin/activate on Linux/macOS)
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 3. Run Frontend
cd ../frontend
npm install
npm run dev
```

---

## Verification & Testing

### Backend Tests & Ruff Linting
```bash
cd backend
.\.venv\Scripts\pytest tests -v
.\.venv\Scripts\ruff check app tests
```

### Frontend Typecheck, Tests & Build
```bash
cd frontend
npm run typecheck
npm run test
npm run build
```

---

## Health & Probe Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Root ping returning version and documentation link |
| `/api/v1/health/live` | GET | Process liveness probe checking FastAPI uptime |
| `/api/v1/health/ready` | GET | Readiness probe checking PostgreSQL and Qdrant connectivity |

---

## Security & Engineering Safeguards
- **Zero Committed Secrets**: Secrets are loaded exclusively via environment variables and `.env` (enforced via `.gitignore` and `pydantic-settings`).
- **Distributed Request Tracing**: Every inbound request receives a unique `X-Request-ID`, which is propagated through log entries, database sessions, and response headers.
- **Strict Error Envelope**: Centralized exception handlers catch and format both domain errors and unhandled exceptions into uniform, client-friendly error structures.
