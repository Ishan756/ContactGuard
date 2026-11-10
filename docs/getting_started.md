# ContractGuard — Getting Started Guide

This guide describes how to run and test ContractGuard locally or using Docker Compose.

## Prerequisites
- **Python**: 3.12 or 3.13
- **Node.js**: v20 or v22 (npm v10+)
- **Docker & Docker Compose**: (v29+ or Docker Desktop)

---

## 1. Quick Start with Docker Compose

Run all services (PostgreSQL, Qdrant, FastAPI backend, and React frontend) with a single command:

```bash
# 1. Ensure .env exists (copied from .env.example)
cp .env.example .env

# 2. Start all services
docker compose up -d

# 3. Check service status
docker compose ps
```

Services will be available at:
- **Frontend Dashboard**: [http://localhost:5173](http://localhost:5173)
- **Backend API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Qdrant Vector Dashboard**: [http://localhost:6333/dashboard](http://localhost:6333/dashboard)
- **PostgreSQL**: `localhost:5432`

### Authentication Keys

Protected endpoints require `X-Reviewer-ID` plus `X-Workflow-Key`:

- `WORKFLOW_REVIEW_API_KEY` — owner-scoped reviewer access.
- `ADMIN_API_KEY` — policy management and cross-reviewer access.

The development defaults are intentionally unsafe. Production startup rejects default,
short, or identical keys. Set both keys in `.env`, then enter the reviewer ID and key in
the Settings page (or provide them through your deployment identity layer).

### Request Protections

- Per-IP sliding-window rate limiting is enabled by default (`600` requests per `60`
  seconds). Tune `RATE_LIMIT_REQUESTS_PER_MINUTE` and `RATE_LIMIT_WINDOW_SECONDS`.
- `TRUST_PROXY_HEADERS=true` makes the limiter use `X-Real-IP`. Enable it only when a
  trusted reverse proxy overwrites that header and clients cannot reach the backend
  directly. Compose sets it for the bundled Nginx proxy and binds the backend port to
  `127.0.0.1`.
- Requests exceeding `REQUEST_TIMEOUT_SECONDS` receive `504`.
- Security headers are enabled by default; HSTS is added only in production.
- Readiness returns `503` in production when PostgreSQL or Qdrant is degraded.
- Swagger/ReDoc/OpenAPI routes are disabled when `APP_ENV=production`.

---

## 2. Local Development Without Full Docker

If running databases in Docker and services locally on the host:

### Start Backing Services (PostgreSQL + Qdrant)
```bash
docker compose up -d postgres qdrant
```

### Run Backend
```bash
# In backend directory
cd backend
python -m venv .venv
.\.venv\Scripts\activate   # Windows (or source .venv/bin/activate on Linux/macOS)
pip install -r requirements-dev.txt

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Run Frontend
```bash
# In frontend directory
cd frontend
npm install
npm run dev
```

---

## 3. Production Deployment

The repository includes Docker Compose for a single-host deployment. It has not been
deployed to a cloud account by this project; treat the following as an operator checklist.

### Production Environment Checklist

1. Set `APP_ENV=production` and `APP_DEBUG=false`.
2. Generate unique `SECRET_KEY`, `WORKFLOW_REVIEW_API_KEY`, and `ADMIN_API_KEY` values
   (at least 32 random characters). The keys must differ.
3. Set `DATABASE_URL` to PostgreSQL and change `POSTGRES_PASSWORD` from the development
   default. Never use SQLite fallback in production.
4. Set explicit HTTPS `CORS_ORIGINS`; wildcards are rejected.
5. Keep `SECURITY_HEADERS_ENABLED=true` and `RATE_LIMIT_ENABLED=true`.
6. Set `TRUST_PROXY_HEADERS=true` only behind a trusted reverse proxy that overwrites
   `X-Real-IP`; never expose the backend directly when this is enabled.
7. Provide `GEMINI_API_KEY` for live model analysis, or explicitly configure mock providers
   only for non-production demonstrations.
8. Keep `.env` out of source control and restrict file permissions (`chmod 600 .env`).

### Single-Host / AWS EC2 Outline

1. Use a current Amazon Linux 2023 or Ubuntu LTS instance with Docker Engine and the
   Compose plugin; attach an encrypted EBS volume for Docker data.
2. Restrict the security group to `22` from trusted administration addresses and `80`/`443`
   from users. Do not expose PostgreSQL (`5432`) or Qdrant (`6333`/`6334`) publicly.
3. Clone the repository, create `.env`, and run `docker compose up -d --build`.
4. Terminate TLS at a reverse proxy (Caddy, Nginx, or an AWS load balancer) in front of the
   frontend container. The bundled frontend Nginx already proxies `/api` and `/health` to
   the backend service.
5. Point health checks at `/api/v1/health/live`; use `/api/v1/health/ready` only where a
   dependency-aware `503` should remove an instance from service.
6. Keep `docker compose logs` and structured JSON logs (production mode) in your log
   platform. Each request includes `X-Request-ID`; workflow logs also carry workflow IDs.

### Backup and Retention

- **PostgreSQL**: schedule encrypted `pg_dump` backups (or managed automated backups) and
  test restores. Application data includes documents metadata, findings, decisions, and
  audit events.
- **Qdrant**: back up the `qdrant_storage` volume or use Qdrant snapshots. Re-indexing from
  policies is possible but loses point-level history.
- **Uploads**: back up the backend uploads volume (`/app/data/uploads` in Compose).
- Apply documented retention targets with scheduled jobs: `DATA_RETENTION_DAYS` for
  contract/policy content and `AUDIT_RETENTION_DAYS` for decisions/audit records (or the
  corresponding platform lifecycle rules).
- Store backups separately from the host and restrict access; verify restore procedures
  before accepting production traffic.

### Upgrade and Rollback

```bash
# Build and start the new version
docker compose pull
docker compose up -d --build

# Inspect health and logs
docker compose ps
docker compose logs --tail=100 backend

# Roll back by checking out the previous release and rebuilding
git checkout <previous-release-tag>
docker compose up -d --build
```

Database schema changes use `create_all` for this project and are not a replacement for a
managed migration process. For production schema evolution, introduce reviewed migrations
before upgrading across versions.

---

## 4. Running Test Suites

### Backend Tests (pytest) & Linting (ruff)
```bash
cd backend
.\.venv\Scripts\pytest tests -v
.\.venv\Scripts\ruff check app tests
```

### Frontend Tests (Vitest) & Typechecking (tsc)
```bash
cd frontend
npm run typecheck
npm run test
npm run build
```
