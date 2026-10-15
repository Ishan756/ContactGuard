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
