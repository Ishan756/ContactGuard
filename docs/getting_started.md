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

## 3. Running Test Suites

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
